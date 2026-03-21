from __future__ import annotations

import os
import csv
import json
from pathlib import Path
from typing import Iterable, List

from docx import Document as DocxDocument
from openpyxl import load_workbook
from langchain_text_splitters import RecursiveCharacterTextSplitter


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    },
}
TICKET_CONTENT_TYPES = {
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel"},
    ".json": {"application/json", "text/json"},
}
GENERIC_AMBIGUOUS_TERMS = {
    "coverage",
    "claim",
    "claims",
    "policy",
    "benefit",
    "benefits",
    "premium",
    "resolution",
    "issue",
    "incident",
    "deductible",
}


def normalize_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def validate_upload(filename: str, content_type: str, size_bytes: int) -> None:
    extension = normalize_extension(filename)
    if extension not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"Unsupported file type '{extension or 'unknown'}'. Allowed: pdf, txt, docx, xlsx.")
    if size_bytes > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds 5 MB limit.")
    allowed_content_types = ALLOWED_CONTENT_TYPES[extension]
    if content_type and content_type not in allowed_content_types:
        raise ValueError(f"Unexpected content type '{content_type}' for '{extension}'.")


def infer_category(filename: str, sample_texts: Iterable[str]) -> str:
    combined = f"{filename}\n" + "\n".join(text for text in sample_texts if text)
    lowered = combined.lower()
    rules = [
        ("support_tickets", ("ticket", "incident", "servicenow", "outage", "resolution")),
        ("medical_insurance", ("medical", "health", "hospital", "doctor", "patient")),
        ("auto_insurance", ("auto", "vehicle", "car", "driver", "collision")),
        ("travel_insurance", ("travel", "trip", "baggage", "flight", "journey")),
        ("home_insurance", ("home", "property", "house", "dwelling")),
        ("insurance", ("insurance", "policy", "coverage", "claim", "premium")),
    ]
    for category, keywords in rules:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "uncategorized"


def query_needs_clarification(query: str) -> bool:
    lowered = (query or "").lower()
    return any(term in lowered for term in GENERIC_AMBIGUOUS_TERMS)


def extract_text_chunks(file_path: str) -> List[str]:
    extension = normalize_extension(file_path)
    if extension == ".txt":
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        return _split_text(text)
    if extension == ".docx":
        document = DocxDocument(file_path)
        text = "\n".join(paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip())
        return _split_text(text)
    if extension == ".xlsx":
        workbook = load_workbook(file_path, read_only=True, data_only=True)
        chunks: List[str] = []
        for worksheet in workbook.worksheets:
            rows = []
            for row in worksheet.iter_rows(values_only=True):
                values = [str(cell).strip() for cell in row if cell not in (None, "")]
                if values:
                    rows.append(" | ".join(values))
            if rows:
                chunks.extend(_split_text(f"Sheet: {worksheet.title}\n" + "\n".join(rows)))
        return chunks
    raise ValueError(f"Text extraction not supported for '{extension}'.")


def build_text_result(chunks: List[str]) -> dict:
    return {
        str(index + 1): {
            "output": chunk,
            "page_numbers": ["1"],
            "url": [],
            "type": "TEXT",
        }
        for index, chunk in enumerate(chunks)
    }


def validate_ticket_upload(filename: str, content_type: str, size_bytes: int) -> None:
    extension = normalize_extension(filename)
    if extension not in TICKET_CONTENT_TYPES:
        raise ValueError("Unsupported ticket file type. Allowed: csv, json.")
    if size_bytes > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds 5 MB limit.")
    allowed_content_types = TICKET_CONTENT_TYPES[extension]
    if content_type and content_type not in allowed_content_types:
        raise ValueError(f"Unexpected content type '{content_type}' for '{extension}'.")


def extract_ticket_chunks(file_path: str) -> List[str]:
    extension = normalize_extension(file_path)
    if extension == ".csv":
        with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle)
            return [
                "\n".join(
                    f"{key}: {value}"
                    for key, value in row.items()
                    if value not in (None, "")
                )
                for row in reader
            ]
    if extension == ".json":
        payload = json.loads(Path(file_path).read_text(encoding="utf-8", errors="ignore"))
        if isinstance(payload, dict):
            payload = payload.get("tickets", [payload])
        chunks: List[str] = []
        for row in payload:
            if isinstance(row, dict):
                chunks.append(
                    "\n".join(f"{key}: {value}" for key, value in row.items() if value not in (None, ""))
                )
        return chunks
    raise ValueError(f"Ticket extraction not supported for '{extension}'.")


def _split_text(text: str) -> List[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [chunk.strip() for chunk in splitter.split_text(cleaned) if chunk.strip()]
