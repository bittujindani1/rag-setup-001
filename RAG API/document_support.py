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
    extension = normalize_extension(filename)
    scoring_rules = {
        "support_tickets": {
            "keywords": (
                "ticket",
                "incident",
                "servicenow",
                "outage",
                "resolution",
                "short description",
                "assignment group",
                "opened by",
                "caller",
                "priority",
                "severity",
                "sla",
            ),
            "bonus": 0,
        },
        "medical_insurance": {
            "keywords": ("medical", "health", "hospital", "doctor", "patient", "clinic", "prescription"),
            "bonus": 0,
        },
        "auto_insurance": {
            "keywords": ("auto", "vehicle", "car", "driver", "collision", "accident", "garage"),
            "bonus": 0,
        },
        "travel_insurance": {
            "keywords": ("travel", "trip", "baggage", "flight", "journey", "passport", "hotel"),
            "bonus": 0,
        },
        "home_insurance": {
            "keywords": ("home", "property", "house", "dwelling", "contents", "fire", "theft"),
            "bonus": 0,
        },
        "insurance": {
            "keywords": ("insurance", "policy", "coverage", "claim", "premium", "insured", "benefit"),
            "bonus": 0,
        },
    }

    scores = {}
    for category, rule in scoring_rules.items():
        score = sum(1 for keyword in rule["keywords"] if keyword in lowered) + int(rule.get("bonus", 0))
        scores[category] = score

    insurance_categories = ("medical_insurance", "auto_insurance", "travel_insurance", "home_insurance", "insurance")
    insurance_signal = any(scores[category] > 0 for category in insurance_categories)

    if extension == ".pdf":
        scores["insurance"] += 2
    if any(token in lowered for token in ("policy", "insurance", "coverage", "claim")):
        scores["insurance"] += 3
    if any(token in lowered for token in ("ticket", "servicenow", "assignment group", "short description")):
        scores["support_tickets"] += 3
    if insurance_signal and extension == ".pdf":
        scores["support_tickets"] = max(0, scores["support_tickets"] - 3)

    best_category = max(scores, key=scores.get)
    if scores[best_category] > 0:
        return best_category
    if extension == ".pdf":
        return "insurance"
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
