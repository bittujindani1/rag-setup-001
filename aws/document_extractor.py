from __future__ import annotations

import io
import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

import boto3
import fitz
from PIL import Image
from docx import Document as DocxDocument

from config_loader import load_app_config


LOGGER = logging.getLogger(__name__)
MAX_PAGES = 50
MAX_FILE_SIZE_MB = 10


class AWSDocumentExtractor:
    def __init__(self) -> None:
        self.config = load_app_config()
        self.region_name = self.config["aws_region"]
        self.extracted_bucket = self.config["s3_bucket_extracted"]
        self.s3_client = boto3.client("s3", region_name=self.region_name)
        self.textract_client = boto3.client("textract", region_name=self.region_name)

    def extract_document(self, file_path: str, document_name: str | None = None) -> List[Dict[str, Any]]:
        path = Path(file_path)
        suffix = path.suffix.lower()
        document_name = document_name or path.name
        self._validate_file(path, suffix)

        if suffix == ".pdf":
            return self._extract_pdf(path, document_name)
        if suffix == ".docx":
            return self._extract_docx(path, document_name)
        if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
            return self._extract_image(path, document_name)
        raise ValueError(f"Unsupported document type: {suffix}")

    def _extract_pdf(self, pdf_path: Path, document_name: str) -> List[Dict[str, Any]]:
        doc = fitz.open(pdf_path)
        if doc.page_count > MAX_PAGES:
            raise ValueError(f"PDF exceeds max page limit of {MAX_PAGES}")
        asset_prefix = self._asset_prefix(document_name)
        pages: List[Dict[str, Any]] = []

        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            page_number = page_index + 1
            page_text = page.get_text("text").strip()
            page_png = self._render_page_png(page)
            page_image_url = self._upload_bytes(
                page_png,
                f"{asset_prefix}/pages/page_{page_number}.png",
                "image/png",
            )

            figure_urls = self._extract_pdf_images(page, asset_prefix, page_number)
            tables = self._extract_pdf_tables(page_png, asset_prefix, page_number)

            pages.append(
                {
                    "page_number": page_number,
                    "text": page_text,
                    "images": figure_urls,
                    "tables": tables,
                    "page_image_url": page_image_url,
                }
            )

        return pages

    @staticmethod
    def _validate_file(path: Path, suffix: str) -> None:
        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            raise ValueError(f"File exceeds max size limit of {MAX_FILE_SIZE_MB} MB")
        if suffix == ".pdf":
            with fitz.open(path) as doc:
                if doc.page_count > MAX_PAGES:
                    raise ValueError(f"PDF exceeds max page limit of {MAX_PAGES}")

    def _extract_docx(self, docx_path: Path, document_name: str) -> List[Dict[str, Any]]:
        doc = DocxDocument(str(docx_path))
        paragraphs = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
        return [
            {
                "page_number": 1,
                "text": "\n".join(paragraphs),
                "images": [],
                "tables": [],
                "page_image_url": "",
            }
        ]

    def _extract_image(self, image_path: Path, document_name: str) -> List[Dict[str, Any]]:
        image_bytes = image_path.read_bytes()
        text = self._extract_text_from_image(image_bytes)
        asset_prefix = self._asset_prefix(document_name)
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        image_url = self._upload_bytes(
            image_bytes,
            f"{asset_prefix}/images/{image_path.name}",
            mime_type,
        )
        return [
            {
                "page_number": 1,
                "text": text,
                "images": [image_url],
                "tables": [],
                "page_image_url": image_url,
            }
        ]

    def _extract_pdf_images(self, page: fitz.Page, asset_prefix: str, page_number: int) -> List[str]:
        figure_urls: List[str] = []
        page_dict = page.get_text("dict")
        image_counter = 0

        for block in page_dict.get("blocks", []):
            if block.get("type") != 1:
                continue
            image_bytes = block.get("image")
            if not image_bytes:
                continue
            image_counter += 1
            ext = block.get("ext", "png")
            key = f"{asset_prefix}/figures/page_{page_number}_figure_{image_counter}.{ext}"
            content_type = mimetypes.guess_type(f"figure.{ext}")[0] or "image/png"
            figure_urls.append(self._upload_bytes(image_bytes, key, content_type))

        return figure_urls

    def _extract_pdf_tables(self, page_png: bytes, asset_prefix: str, page_number: int) -> List[Dict[str, str]]:
        response = self.textract_client.analyze_document(
            Document={"Bytes": page_png},
            FeatureTypes=["TABLES"],
        )
        blocks = response.get("Blocks", [])
        block_map = {block["Id"]: block for block in blocks if "Id" in block}

        page_image = Image.open(io.BytesIO(page_png))
        tables: List[Dict[str, str]] = []
        table_counter = 0

        for block in blocks:
            if block.get("BlockType") != "TABLE":
                continue
            table_counter += 1
            table_text = self._table_block_to_text(block, block_map)
            table_image_url = self._upload_table_crop(
                page_image,
                block,
                asset_prefix,
                page_number,
                table_counter,
            )
            tables.append(
                {
                    "text": table_text,
                    "image_url": table_image_url,
                }
            )

        return tables

    def _extract_text_from_image(self, image_bytes: bytes) -> str:
        response = self.textract_client.detect_document_text(Document={"Bytes": image_bytes})
        lines = [
            block.get("Text", "").strip()
            for block in response.get("Blocks", [])
            if block.get("BlockType") == "LINE" and block.get("Text")
        ]
        return "\n".join(lines)

    def _table_block_to_text(self, table_block: Dict[str, Any], block_map: Dict[str, Dict[str, Any]]) -> str:
        cells: Dict[tuple[int, int], str] = {}
        max_row = 0
        max_col = 0

        for relationship in table_block.get("Relationships", []):
            if relationship.get("Type") != "CHILD":
                continue
            for child_id in relationship.get("Ids", []):
                cell = block_map.get(child_id, {})
                if cell.get("BlockType") != "CELL":
                    continue
                row = int(cell.get("RowIndex", 1))
                col = int(cell.get("ColumnIndex", 1))
                max_row = max(max_row, row)
                max_col = max(max_col, col)
                cells[(row, col)] = self._cell_text(cell, block_map)

        rows: List[str] = []
        for row_idx in range(1, max_row + 1):
            row_values = [cells.get((row_idx, col_idx), "") for col_idx in range(1, max_col + 1)]
            rows.append(" | ".join(value.strip() for value in row_values).strip())
        return "\n".join(row for row in rows if row)

    def _cell_text(self, cell_block: Dict[str, Any], block_map: Dict[str, Dict[str, Any]]) -> str:
        words: List[str] = []
        for relationship in cell_block.get("Relationships", []):
            if relationship.get("Type") != "CHILD":
                continue
            for child_id in relationship.get("Ids", []):
                child = block_map.get(child_id, {})
                if child.get("BlockType") == "WORD" and child.get("Text"):
                    words.append(child["Text"])
                elif child.get("BlockType") == "SELECTION_ELEMENT" and child.get("SelectionStatus") == "SELECTED":
                    words.append("X")
        return " ".join(words).strip()

    def _upload_table_crop(
        self,
        page_image: Image.Image,
        table_block: Dict[str, Any],
        asset_prefix: str,
        page_number: int,
        table_counter: int,
    ) -> str:
        bbox = table_block.get("Geometry", {}).get("BoundingBox", {})
        width, height = page_image.size
        left = max(0, int(bbox.get("Left", 0.0) * width))
        top = max(0, int(bbox.get("Top", 0.0) * height))
        right = min(width, int((bbox.get("Left", 0.0) + bbox.get("Width", 0.0)) * width))
        bottom = min(height, int((bbox.get("Top", 0.0) + bbox.get("Height", 0.0)) * height))

        if right <= left or bottom <= top:
            crop = page_image.copy()
        else:
            crop = page_image.crop((left, top, right, bottom))

        buffer = io.BytesIO()
        crop.save(buffer, format="PNG")
        key = f"{asset_prefix}/tables/page_{page_number}_table_{table_counter}.png"
        return self._upload_bytes(buffer.getvalue(), key, "image/png")

    @staticmethod
    def _render_page_png(page: fitz.Page) -> bytes:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        return pix.tobytes("png")

    def _upload_bytes(self, body: bytes, key: str, content_type: str) -> str:
        self.s3_client.put_object(
            Bucket=self.extracted_bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        return f"https://{self.extracted_bucket}.s3.{self.region_name}.amazonaws.com/{key}"

    @staticmethod
    def _asset_prefix(document_name: str) -> str:
        stem = Path(document_name).stem.replace(" ", "_")
        return f"extracted/{stem}-{uuid.uuid4().hex[:8]}"
