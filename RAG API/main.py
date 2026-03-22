import base64
import io
import json
import logging
import os
import re
import shutil
import asyncio
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from metadata import create_image_metadata, create_table_metadata, create_text_metadata, preprocess_metadata
from PIL import Image
from pydantic import BaseModel
from requests_aws4auth import AWS4Auth

from citations import get_citations
from customchain import multi_modal_rag_chain_with_history
from customretriever import create_ensemble_retriever, create_retriever
from document_router import build_disambiguation_payload
from metric_discovery import discover_metrics
from query_classifier import classify_query_route
from sql_validator import validate_sql
from document_support import (
    build_text_result,
    extract_text_chunks,
    extract_ticket_chunks,
    get_max_upload_bytes,
    get_pdf_page_count,
    get_upload_policy,
    infer_category,
    is_limit_exempt_workspace,
    normalize_extension,
    query_needs_clarification,
    validate_ticket_upload,
    validate_upload,
)
from text_to_sql import generate_sql_for_question
from external_utils import download_blob, get_presigned_url, upload_pdf_and_download_json, upload_to_blob
from extraction import extract_imageresult, extract_tableresult, extract_textresult
from ingest_doc import create_multi_vector_retriever
from summary import generate_img_summaries, generate_text_summaries
from vectordb_utils import (
    create_index_if_not_exists,
    delete_documents_by_filename,
    get_vectorstore,
    list_all_filenames_in_index,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from aws.thread_store import DynamoDBThreadStore
from env_bootstrap import bootstrap_env
from provider_factory import (
    build_chat_history,
    get_bedrock_client,
    get_cache_manager,
    get_config,
    get_analytics_store,
    get_document_category_store,
    get_doc_store,
    get_feedback_store,
    get_filename_index,
    get_ingest_job_store,
    get_metrics_collector,
    get_rate_limiter,
)

bootstrap_env(Path(__file__).resolve().with_name(".env"))
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

import warnings
warnings.filterwarnings('ignore')

LOGGER = logging.getLogger(__name__)
MAX_QUERY_LENGTH = 2000
INDEX_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
CHAT_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}
MAX_CHAT_IMAGE_BYTES = 5 * 1024 * 1024
THREAD_TABLE_NAME = os.getenv("DYNAMODB_THREAD_TABLE", "rag_chat_threads")
thread_store = DynamoDBThreadStore(table_name=THREAD_TABLE_NAME, region_name=os.getenv("AWS_REGION", "ap-south-1"))
TEMP_ROOT = Path(tempfile.gettempdir()) / "rag_serverless"


def _ensure_temp_dir(*parts: str) -> Path:
    path = TEMP_ROOT.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path

 
prefix1 = "SFRAG"
 
app = FastAPI(
    title="Insura-RAG(HTCNXT)",
    openapi_url=f"/{prefix1}/docs/openapi.json",
    docs_url=f"/{prefix1}/docs/",
    redoc_url=f"/{prefix1}/docs/redoc",
)


STORAGE_ACCOUNT_NAME = os.getenv("STORAGE_ACCOUNT_NAME")
BASE_CONTAINER_NAME = os.getenv("BASE_CONTAINER_NAME")


AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_SERVICE = os.getenv("AWS_SERVICE")

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL")

AZURE_CONN_STRING = os.getenv("AZURE_CONN_STRING")
AZURE_CONTAINER_NAME  = os.getenv("AZURE_CONTAINER_NAME")

# api_key = os.getenv("AZURE_OPENAI_API_KEY_EMBEDDINGS")
# azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
# api_version = os.getenv("AZURE_API_VERSION")

awsauth = None
if AWS_ACCESS_KEY and AWS_SECRET_KEY and AWS_REGION and AWS_SERVICE:
    awsauth = AWS4Auth(AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, AWS_SERVICE)

# Initialize OpenAI embeddings
embedding_function = None


def _serialize_thread(thread: dict) -> dict:
    return {
        "id": thread.get("id"),
        "name": thread.get("name"),
        "createdAt": thread.get("createdAt"),
        "metadata": thread.get("metadata") or {},
        "steps": thread.get("steps", []),
    }


def _validate_index_name(index_name: str) -> str:
    normalized = (index_name or "").strip().lower()
    if not INDEX_NAME_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail="index_name must be 3-64 chars and contain only lowercase letters, numbers, hyphens, or underscores.",
        )
    return normalized


def _thread_workspace(thread: dict | None) -> str | None:
    if not thread:
        return None
    metadata = thread.get("metadata") or {}
    return metadata.get("workspace_id") or metadata.get("index_name")


def _clear_thread_history(thread_id: str) -> None:
    thread = thread_store.load_thread(thread_id)
    if not thread:
        return
    metadata = thread.get("metadata") or {}
    session_id = metadata.get("session_id")
    if session_id:
        build_chat_history(session_id).clear()
    thread_store.delete_thread(thread_id)


def _detect_requested_category(index_name: str, query: str, selected_category: str | None) -> str | None:
    available_categories = {
        item["category"]
        for item in get_document_category_store().list_categories(index_name)
        if item.get("category")
    }
    if selected_category:
        return selected_category
    lowered_query = (query or "").lower()
    for category in available_categories:
        if category.lower().replace("_", " ") in lowered_query or category.lower() in lowered_query:
            return category
    return None


def _filter_docs_by_category(index_name: str, docs: list, category: str | None) -> list:
    if not category:
        return docs
    documents = get_document_category_store().list_documents(index_name)
    allowed_filenames = {
        item.get("filename")
        for item in documents
        if item.get("category") == category
    }
    filtered = [doc for doc in docs if doc.metadata.get("filename") in allowed_filenames]
    return filtered or docs


def _filter_docs_by_filename(docs: list, filename: str | None) -> list:
    if not filename:
        return docs
    filtered = [doc for doc in docs if doc.metadata.get("filename") == filename]
    return filtered or docs


def _download_s3_object_to_temp(index_name: str, s3_key: str, content_type: str | None) -> tuple[str, bytes, str, str]:
    config = get_config()
    filename = os.path.basename(s3_key)
    temp_dir = _ensure_temp_dir("s3_ingest_tmp", uuid.uuid4().hex)
    local_path = temp_dir / filename
    s3_client = boto3.client("s3", region_name=config["aws_region"])
    s3_client.download_file(config["s3_bucket_documents"], s3_key, str(local_path))
    file_bytes = local_path.read_bytes()
    presigned_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": config["s3_bucket_documents"], "Key": s3_key},
        ExpiresIn=3600,
    )
    inferred_content_type = content_type or {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(normalize_extension(filename), "application/octet-stream")
    return str(local_path), file_bytes, inferred_content_type, presigned_url


# 3. Import necessary modules
class QueryRequest(BaseModel):
    user_query: str
    index_name: str
    session_id: str
    thread_id: str | None = None
    selected_category: str | None = None
    document_filter: str | None = None


class ThreadCreateRequest(BaseModel):
    name: str | None = None
    user_id: str = "demo"
    user_identifier: str = "demo"
    workspace_id: str


class PresignUploadRequest(BaseModel):
    index_name: str
    filename: str
    content_type: str


class S3IngestRequest(BaseModel):
    index_name: str
    s3_key: str
    content_type: str | None = None


class TicketIngestRequest(BaseModel):
    index_name: str
    filename: str
    content_type: str


class FeedbackRequest(BaseModel):
    user_id: str
    workspace_id: str
    feedback: str


class AnalyticsQueryRequest(BaseModel):
    dataset_id: str
    question: str


class AnalyticsDatasetCreateRequest(BaseModel):
    dataset_id: str


def _match_direct_intent(query: str) -> str | None:
    lowered = (query or "").strip().lower()
    if not lowered:
        return "Please type a question about your uploaded documents or tickets."
    if lowered in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}:
        return "Hello. Ask about your uploaded documents, insurance content, or ServiceNow tickets and I will help."
    if lowered in {"thanks", "thank you", "ok thanks", "great thanks", "got it", "understood"}:
        return "You’re welcome. Ask another question whenever you’re ready."
    if lowered in {"bye", "goodbye", "see you", "thanks bye", "exit"}:
        return "Session closed on my side. You can come back with another document or ticket question anytime."
    return None


def _json_from_text(raw_text: str) -> dict | None:
    if not raw_text:
        return None
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _image_to_png_base64(file_bytes: bytes) -> str:
    with Image.open(io.BytesIO(file_bytes)) as image:
        converted = image.convert("RGB")
        buffer = io.BytesIO()
        converted.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _extract_query_from_image(file_bytes: bytes, prompt_hint: str | None = None) -> dict[str, str]:
    encoded_image = _image_to_png_base64(file_bytes)
    system_prompt = (
        "You are extracting a user question from an uploaded screenshot or image for a RAG assistant.\n"
        "Return only JSON with keys: extracted_text, intent, retrieval_query.\n"
        "intent must be one of greeting, acknowledgement, farewell, retrieval.\n"
        "retrieval_query should be the cleanest searchable version of the user’s actual question.\n"
        "If the image is mostly tabular or ticket data and the user is asking for counts, categories, or trends, keep that analytic request explicit.\n"
        "If the image contains no clear question, infer the most likely question from visible text.\n"
    )
    text_prompt = "Extract the question from this image and return only JSON."
    if prompt_hint:
        text_prompt += f"\nUser note: {prompt_hint}"
    model_output = get_bedrock_client().generate_multimodal_text(
        text_prompt=text_prompt,
        images_base64=[encoded_image],
        system_prompt=system_prompt,
        max_tokens=400,
        temperature=0.0,
    )
    payload = _json_from_text(model_output) or {}
    extracted_text = str(payload.get("extracted_text") or "").strip()
    intent = str(payload.get("intent") or "retrieval").strip().lower()
    retrieval_query = str(payload.get("retrieval_query") or extracted_text or prompt_hint or "").strip()
    return {
        "extracted_text": extracted_text,
        "intent": intent if intent in {"greeting", "acknowledgement", "farewell", "retrieval"} else "retrieval",
        "retrieval_query": retrieval_query,
    }


def _workspace_document_count(index_name: str) -> int:
    return len(get_document_category_store().list_documents(index_name))


def _normalize_model_category(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_ -]+", "", (value or "").strip().lower())
    normalized = normalized.replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        return "general_document"
    return normalized[:48]


def _smart_infer_category(file_name: str, text_samples: list[str]) -> str:
    heuristic = infer_category(file_name, text_samples[:3])
    if heuristic != "uncategorized":
        return heuristic

    excerpt = "\n\n".join((sample or "").strip()[:1200] for sample in text_samples[:3] if sample).strip()
    if not excerpt:
        return "general_document"

    prompt = (
        "You are classifying an uploaded business document for a demo RAG portal.\n"
        "Return only one short snake_case category label.\n"
        "Make it specific but stable, like cloud_costing, contract, invoice, architecture, legal, finance, hr, insurance, support_tickets, operations, roadmap, procurement.\n"
        "Do not return explanations.\n\n"
        f"Filename: {file_name}\n\n"
        f"Excerpt:\n{excerpt}\n"
    )
    model_output = get_bedrock_client().generate_text(prompt=prompt, max_tokens=20, temperature=0.0)
    category = _normalize_model_category(model_output.splitlines()[0] if model_output else "")
    return category or "general_document"


def _load_ticket_rows(index_name: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for document in get_document_category_store().list_documents(index_name):
        if document.get("source_type") != "support_tickets":
            continue
        filename = document.get("filename")
        if not filename:
            continue
        doc_ids = get_filename_index().get_doc_ids(index_name, filename)
        for offset in range(0, len(doc_ids), 100):
            contents = get_doc_store().mget(doc_ids[offset : offset + 100])
            for content in contents:
                if not content or "ticket_id:" not in content:
                    continue
                parsed: dict[str, str] = {}
                for line in content.splitlines():
                    if ": " not in line:
                        continue
                    key, value = line.split(": ", 1)
                    parsed[key.strip()] = value.strip()
                if parsed.get("ticket_id"):
                    rows.append(parsed)
    return rows


def _markdown_count_table(title: str, counts: dict[str, int]) -> str:
    lines = [title, "", "| Value | Ticket Count |", "| --- | ---: |"]
    for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {key} | {count} |")
    return "\n".join(lines)


def _markdown_two_column_table(title: str, left_label: str, right_label: str, rows: list[tuple[str, int]]) -> str:
    lines = [title, "", f"| {left_label} | {right_label} |", "| --- | ---: |"]
    for key, count in rows:
        lines.append(f"| {key} | {count} |")
    return "\n".join(lines)


def _ticket_analytics_response(query: str, index_name: str) -> str | None:
    if index_name != "snow_idx":
        return None
    lowered = (query or "").lower()
    rows = _load_ticket_rows(index_name)
    if not rows:
        return None

    if "assignment group" in lowered and any(term in lowered for term in ("most", "top", "handled")):
        counts: dict[str, int] = {}
        for row in rows:
            group = row.get("assignment_group", "unknown")
            counts[group] = counts.get(group, 0) + 1
        return _markdown_count_table("Assignment groups by ticket volume", counts)

    if "categor" in lowered and any(term in lowered for term in ("all", "show", "list", "most", "top", "incident")):
        counts: dict[str, int] = {}
        for row in rows:
            category = row.get("category", "unknown")
            counts[category] = counts.get(category, 0) + 1
        return _markdown_count_table("Incident categories in the ServiceNow dataset", counts)

    if "identity" in lowered and any(term in lowered for term in ("common", "issues", "issue", "problem", "patterns")):
        identity_rows = [row for row in rows if (row.get("category") or "").strip().lower() == "identity"]
        if not identity_rows:
            return None
        summary_counts: dict[str, int] = {}
        for row in identity_rows:
            summary = row.get("summary", "unknown")
            summary_counts[summary] = summary_counts.get(summary, 0) + 1
        common_rows = sorted(summary_counts.items(), key=lambda item: (-item[1], item[0]))
        return _markdown_two_column_table(
            "Common identity-related issues",
            "Issue Summary",
            "Ticket Count",
            common_rows,
        )

    if "priority" in lowered and any(term in lowered for term in ("most", "top")):
        counts: dict[str, int] = {}
        for row in rows:
            priority = row.get("priority", "unknown")
            counts[priority] = counts.get(priority, 0) + 1
        return _markdown_count_table("Ticket priorities by volume", counts)

    if "source" in lowered and any(term in lowered for term in ("most", "top", "compare")):
        counts: dict[str, int] = {}
        for row in rows:
            source = row.get("source", "unknown")
            counts[source] = counts.get(source, 0) + 1
        return _markdown_count_table("Ticket sources by volume", counts)

    if "summar" in lowered and any(term in lowered for term in ("top", "recurring", "common", "most")):
        summary_counts: dict[str, int] = {}
        for row in rows:
            summary = row.get("summary", "unknown")
            summary_counts[summary] = summary_counts.get(summary, 0) + 1
        recurring_rows = sorted(summary_counts.items(), key=lambda item: (-item[1], item[0]))
        return _markdown_two_column_table(
            "Top recurring ticket summaries",
            "Summary",
            "Ticket Count",
            recurring_rows,
        )

    if any(phrase in lowered for phrase in ("ticket sample", "sample tickets", "show sample tickets")) or (
        ("table format" in lowered or "show a table" in lowered)
        and not any(
            keyword in lowered
            for keyword in ("assignment group", "categor", "priority", "source", "identity", "summar")
        )
    ):
        selected = rows[:10]
        lines = [
            "Ticket sample",
            "",
            "| Ticket ID | Category | Priority | Assignment Group | Status | Summary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in selected:
            lines.append(
                f"| {row.get('ticket_id', '')} | {row.get('category', '')} | {row.get('priority', '')} | {row.get('assignment_group', '')} | {row.get('status', '')} | {row.get('summary', '')} |"
            )
        return "\n".join(lines)

    return None


def _index_text_document(
    *,
    index_name: str,
    file_name: str,
    input_file_url: str,
    content_type: str,
    file_size: int,
    text_chunks: list[str],
):
    create_index_if_not_exists(index_name)
    textresult = build_text_result(text_chunks)
    texts_list = [textresult[key]["output"] for key in sorted(textresult.keys(), key=int)]
    text_summaries, table_summaries = generate_text_summaries(texts_list, [], summarize_texts=True)
    text_metadata = create_text_metadata(textresult, file_name, input_file_url)
    vectorstore = get_vectorstore(index_name)
    _, indexed_chunks = create_multi_vector_retriever(
        vectorstore,
        text_summaries,
        texts_list,
        text_metadata,
        table_summaries,
        [],
        [],
        [],
        [],
        [],
        file_name,
        index_name,
    )
    category = _smart_infer_category(file_name, texts_list[:3])
    get_document_category_store().upsert_document(
        index_name=index_name,
        filename=file_name,
        category=category,
        source_type="support_tickets" if category == "support_tickets" else "document",
        content_type=content_type,
        size_bytes=file_size,
        storage_url=input_file_url,
    )
    get_metrics_collector().increment_documents_indexed(indexed_chunks)
    return {
        "status": "Index ingested successfully",
        "index_name": index_name,
        "imagecount": 0,
        "tablecount": 0,
        "category": category,
        "content_type": content_type,
        "warnings": [],
        "processing_mode": "text_only",
    }


def _analytics_summary_text(question: str, result: dict, chart_type: str) -> str:
    rows = result.get("rows", [])
    if not rows:
        return "No matching rows were found in the analytics dataset."
    if chart_type == "number" and rows and len(rows[0]) == 1:
        value = next(iter(rows[0].values()))
        return f"{question.strip().rstrip('?')}: {value}"
    if chart_type in {"bar", "line"} and len(rows[0]) >= 2:
        preview = ", ".join(
            f"{list(row.values())[0]} = {list(row.values())[1]}"
            for row in rows[:5]
        )
        return f"Executed analytics query successfully. Top results: {preview}"
    return "Executed analytics query successfully. Review the returned rows for the exact result set."


def _normalize_metric_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower()).strip()


def _match_cached_metric(question: str, cached_metrics: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_question = _normalize_metric_key(question)
    if not normalized_question:
        return None

    for metric in cached_metrics:
        metric_id = _normalize_metric_key(str(metric.get("metric_id", "")))
        metric_title = _normalize_metric_key(str(metric.get("title", "")))
        if normalized_question in {metric_id, metric_title}:
            return metric
        if metric_title and (normalized_question.startswith(metric_title) or metric_title in normalized_question):
            return metric
    return None


def _dataset_metrics_response(dataset_id: str, metrics: list[dict], summary: dict, source: str) -> dict:
    return {
        "dataset_id": dataset_id,
        "source": source,
        "summary": summary,
        "metrics": metrics,
    }


def _ingest_local_file(
    *,
    index_name: str,
    file_name: str,
    content_type: str,
    file_bytes: bytes,
    local_path: str,
    input_file_url: str,
):
    image_summaries = []
    text_summaries = []
    table_summaries = []
    base_output_dir = _ensure_temp_dir("image_files")
    temp_dir_root = _ensure_temp_dir("pdf_files")

    dynamic_output_dir = None
    temp_pdf_pathbase = None
    json_path = None

    try:
        unique_id = str(uuid.uuid4())
        dynamic_output_dir = str(_ensure_temp_dir("image_files", unique_id))
        temp_pdf_pathbase = str(_ensure_temp_dir("pdf_files", unique_id))

        extension = normalize_extension(file_name)
        file_size = len(file_bytes)
        page_count = get_pdf_page_count(local_path) if extension == ".pdf" else None
        existing_documents_count = _workspace_document_count(index_name)
        warnings = validate_upload(
            file_name,
            content_type,
            file_size,
            index_name=index_name,
            existing_documents_count=existing_documents_count,
            pdf_page_count=page_count,
        )

        filenames_in_index = list_all_filenames_in_index(index_name)
        if file_name in filenames_in_index:
            delete_documents_by_filename(index_name, file_name)
            get_document_category_store().delete_document(index_name, file_name)

        force_text_only_pdf = extension == ".pdf" and not is_limit_exempt_workspace(index_name) and page_count is not None and page_count > 20

        if extension != ".pdf" or force_text_only_pdf:
            text_chunks = extract_text_chunks(local_path)
            if not text_chunks:
                raise HTTPException(status_code=400, detail="Could not extract usable text from the uploaded document.")
            response = _index_text_document(
                index_name=index_name,
                file_name=file_name,
                input_file_url=input_file_url,
                content_type=content_type,
                file_size=file_size,
                text_chunks=text_chunks,
            )
            response["warnings"] = warnings
            response["processing_mode"] = "text_only" if extension == ".pdf" else "standard"
            response["page_count"] = page_count
            return response

        LOGGER.info("Preparing ingest temp_pdf_path=%s index_name=%s", local_path, index_name)
        json_path = upload_pdf_and_download_json(local_path, 30, temp_pdf_pathbase, file_name, input_file_url)
        create_index_if_not_exists(index_name)

        with open(json_path, "r") as handle:
            data = json.load(handle)
        imageresult = extract_imageresult(data)
        tableresult = extract_tableresult(data)
        textresult = extract_textresult(data)

        sorted_keys = sorted(imageresult.keys(), key=int)
        imageurl_list = [imageresult[key]["url"] for key in sorted_keys if "url" in imageresult[key]]
        for idx, blob_url in enumerate(imageurl_list, start=1):
            output_file_path = os.path.join(dynamic_output_dir, f"{idx}.png")
            download_blob(AZURE_CONN_STRING, AZURE_CONTAINER_NAME, blob_url, output_file_path)

        img_base64_list, image_summaries = generate_img_summaries(dynamic_output_dir)
        imageno = len(image_summaries)

        texts_list = [textresult[key]["output"] for key in sorted(textresult.keys(), key=int) if "output" in textresult[key]]
        table_list = [tableresult[key]["output"] for key in sorted(tableresult.keys(), key=int) if "output" in tableresult[key]]
        text_summaries, table_summaries = generate_text_summaries(texts_list, table_list, summarize_texts=True)
        tableno = len(table_summaries)

        image_metadata = create_image_metadata(imageresult, file_name, input_file_url)
        table_metadata = create_table_metadata(tableresult, file_name, input_file_url)
        text_metadata = create_text_metadata(textresult, file_name, input_file_url)

        vectorstore = get_vectorstore(index_name)
        _, indexed_chunks = create_multi_vector_retriever(
            vectorstore,
            text_summaries,
            texts_list,
            text_metadata,
            table_summaries,
            table_list,
            table_metadata,
            image_summaries,
            img_base64_list,
            image_metadata,
            file_name,
            index_name,
        )
        get_metrics_collector().increment_documents_indexed(indexed_chunks)
        category = _smart_infer_category(file_name, texts_list[:3])
        get_document_category_store().upsert_document(
            index_name=index_name,
            filename=file_name,
            category=category,
            source_type="support_tickets" if category == "support_tickets" else "document",
            content_type=content_type,
            size_bytes=file_size,
            storage_url=input_file_url,
        )
        return {
            "status": "Index ingested successfully",
            "index_name": index_name,
            "imagecount": imageno,
            "tablecount": tableno,
            "category": category,
            "content_type": content_type,
            "warnings": warnings,
            "processing_mode": "full_pdf",
            "page_count": page_count,
        }
    finally:
        if dynamic_output_dir and os.path.exists(dynamic_output_dir):
            shutil.rmtree(dynamic_output_dir)
        if temp_pdf_pathbase and os.path.exists(temp_pdf_pathbase):
            shutil.rmtree(temp_pdf_pathbase)
        if json_path and os.path.exists(json_path):
            os.remove(json_path)


@app.get("/health")
async def health():
    config = get_config()
    services = {
        "s3": "error",
        "dynamodb": "error",
        "bedrock": "error",
    }
    overall_status = "ok"

    try:
        boto3.client("s3", region_name=config["aws_region"]).list_objects_v2(
            Bucket=config["s3_bucket_documents"],
            MaxKeys=1,
        )
        services["s3"] = "ok"
    except (BotoCoreError, ClientError):
        LOGGER.exception("Health check failed for S3")
        overall_status = "degraded"

    try:
        boto3.client("dynamodb", region_name=config["aws_region"]).describe_table(
            TableName=config["dynamodb_query_cache_table"]
        )
        services["dynamodb"] = "ok"
    except (BotoCoreError, ClientError):
        LOGGER.exception("Health check failed for DynamoDB")
        overall_status = "degraded"

    try:
        boto3.client("bedrock", region_name=config["aws_region"]).list_foundation_models(byOutputModality="TEXT")
        services["bedrock"] = "ok"
    except (BotoCoreError, ClientError):
        LOGGER.exception("Health check failed for Bedrock")
        overall_status = "degraded"

    return {"status": overall_status, "services": services}


@app.get("/metrics")
async def metrics():
    return get_metrics_collector().snapshot()


@app.get("/SFRAG/threads")
async def list_threads(limit: int = 50, workspace_id: str | None = None):
    normalized_workspace = _validate_index_name(workspace_id) if workspace_id else None
    threads = thread_store.list_threads(limit=limit)
    if normalized_workspace:
        threads = [thread for thread in threads if _thread_workspace(thread) == normalized_workspace]
    return {"threads": [_serialize_thread(thread) for thread in threads]}


@app.get("/SFRAG/threads/{thread_id}")
async def get_thread(thread_id: str, workspace_id: str | None = None):
    normalized_workspace = _validate_index_name(workspace_id) if workspace_id else None
    thread = thread_store.load_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if normalized_workspace and _thread_workspace(thread) != normalized_workspace:
        raise HTTPException(status_code=404, detail="Thread not found")
    return _serialize_thread(thread)


@app.post("/SFRAG/threads")
async def create_thread(request: ThreadCreateRequest):
    workspace_id = _validate_index_name(request.workspace_id)
    thread_id = str(uuid.uuid4())
    session_id = uuid.uuid4().hex
    thread_store.ensure_thread(
        thread_id=thread_id,
        user_id=request.user_id,
        user_identifier=request.user_identifier,
        name=request.name or "New chat",
        metadata={"session_id": session_id, "workspace_id": workspace_id, "index_name": workspace_id},
    )
    return {"thread_id": thread_id, "session_id": session_id, "name": request.name or "New chat"}


@app.delete("/SFRAG/threads/{thread_id}")
async def delete_thread(thread_id: str, workspace_id: str | None = None):
    normalized_workspace = _validate_index_name(workspace_id) if workspace_id else None
    thread = thread_store.load_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if normalized_workspace and _thread_workspace(thread) != normalized_workspace:
        raise HTTPException(status_code=404, detail="Thread not found")
    _clear_thread_history(thread_id)
    return {"status": "deleted", "thread_id": thread_id}


@app.get("/SFRAG/documents/{index_name}")
async def list_documents(index_name: str):
    documents = get_document_category_store().list_documents(_validate_index_name(index_name))
    return {"documents": documents}


@app.get("/SFRAG/categories/{index_name}")
async def list_categories(index_name: str):
    return {"categories": get_document_category_store().list_categories(_validate_index_name(index_name))}


@app.get("/SFRAG/upload-policy/{index_name}")
async def upload_policy(index_name: str):
    normalized = _validate_index_name(index_name)
    return get_upload_policy(normalized, _workspace_document_count(normalized))


@app.delete("/SFRAG/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    normalized_workspace = _validate_index_name(workspace_id)
    if normalized_workspace == "demo-shared":
        raise HTTPException(status_code=400, detail="Shared demo workspace cannot be deleted.")

    threads = [
        thread for thread in thread_store.list_threads(limit=500)
        if _thread_workspace(thread) == normalized_workspace
    ]
    for thread in threads:
        thread_id = thread.get("id")
        if thread_id:
            _clear_thread_history(thread_id)

    for document in get_document_category_store().list_documents(normalized_workspace):
        filename = document.get("filename")
        if not filename:
            continue
        delete_documents_by_filename(normalized_workspace, filename)
        get_document_category_store().delete_document(normalized_workspace, filename)

    return {
        "status": "deleted",
        "workspace_id": normalized_workspace,
        "threads_deleted": len(threads),
    }


@app.post("/SFRAG/uploads/presign")
async def create_presigned_upload(request: PresignUploadRequest):
    request.index_name = _validate_index_name(request.index_name)
    try:
        validate_upload(
            request.filename,
            request.content_type,
            0,
            index_name=request.index_name,
            existing_documents_count=_workspace_document_count(request.index_name),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    config = get_config()
    object_key = f"{request.index_name}/{uuid.uuid4().hex}-{request.filename}"
    s3_client = boto3.client("s3", region_name=config["aws_region"])
    max_upload_bytes = get_max_upload_bytes(request.index_name)
    try:
        presigned = s3_client.generate_presigned_post(
            config["s3_bucket_documents"],
            object_key,
            Fields={"Content-Type": request.content_type},
            Conditions=[["content-length-range", 1, max_upload_bytes], {"Content-Type": request.content_type}],
            ExpiresIn=3600,
        )
    except Exception as exc:
        LOGGER.exception("Failed to generate presigned upload")
        raise HTTPException(status_code=500, detail="Could not create presigned upload") from exc
    return {
        "url": presigned["url"],
        "fields": presigned["fields"],
        "bucket": config["s3_bucket_documents"],
        "object_key": object_key,
    }


@app.get("/SFRAG/ingest-status/{job_id}")
async def ingest_status(job_id: str):
    job = get_ingest_job_store().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingest job not found")
    return job


@app.post("/SFRAG/feedback")
async def submit_feedback(request: FeedbackRequest):
    workspace_id = _validate_index_name(request.workspace_id)
    user_id = (request.user_id or "").strip()
    feedback = (request.feedback or "").strip()
    if len(user_id) < 2:
        raise HTTPException(status_code=400, detail="user_id is required.")
    if len(feedback) < 5:
        raise HTTPException(status_code=400, detail="feedback must be at least 5 characters.")
    item = get_feedback_store().create_feedback(
        user_id=user_id[:120],
        workspace_id=workspace_id,
        feedback=feedback[:4000],
    )
    return {"status": "submitted", "item": item}


# class QueryRequest(BaseModel):
#     assistant_id: str
#     project_id: str
#     chat_id: str
#     project_name: str
#     user_query: str
#     role_level: str
#     multimodal_url_list: List[str] = []


@app.post("/SFRAG/retrieval")
async def multi_modal_query(query_request: QueryRequest, request: Request):
    query_request.index_name = _validate_index_name(query_request.index_name)
    time_of_query = datetime.now()
    start_time = time.time()
    if len(query_request.user_query) > MAX_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"user_query exceeds maximum length of {MAX_QUERY_LENGTH} characters",
        )
    config = get_config()
    if query_request.thread_id:
        thread_store.ensure_thread(
            thread_id=query_request.thread_id,
            user_id="demo",
            user_identifier="demo",
            name=(query_request.user_query or "New chat")[:80],
            metadata={
                "session_id": query_request.session_id,
                "workspace_id": query_request.index_name,
                "index_name": query_request.index_name,
            },
        )

    direct_intent_answer = _match_direct_intent(query_request.user_query)
    if direct_intent_answer:
        full_response = {
            "mode": "answer",
            "response": {
                "content": direct_intent_answer,
            },
            "citation": [],
            "selected_category": None,
        }
        if query_request.thread_id:
            thread_store.save_message(
                thread_id=query_request.thread_id,
                role="user",
                content=query_request.user_query,
                user_id="demo",
                user_identifier="demo",
                thread_name=(query_request.user_query or "New chat")[:80],
            )
            thread_store.save_message(
                thread_id=query_request.thread_id,
                role="assistant",
                content=direct_intent_answer,
                user_id="demo",
                user_identifier="demo",
                thread_name=(query_request.user_query or "New chat")[:80],
            )
        return JSONResponse(content=full_response)

    rate_limiter = get_rate_limiter()
    allowed, _ = rate_limiter.check_and_record(query_request.session_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                "Rate limit exceeded for this session. The current limit is "
                f"{config.get('rate_limit_requests_per_minute', 15)} requests per minute. "
                "Please wait before retrying or increase the query limit."
            ),
        )
    cache_manager = get_cache_manager() if config.get("cache") == "dynamodb" else None
    cache_key = None
    ticket_analytics_answer = _ticket_analytics_response(
        query_request.user_query,
        query_request.index_name,
    )
    if ticket_analytics_answer:
        direct_response = {
            "mode": "answer",
            "response": {
                "content": ticket_analytics_answer,
            },
            "citation": [
                {
                    "type": "TEXT",
                    "filename": "servicenow_tickets.csv",
                    "document_id": "servicenow_tickets.csv",
                    "section_id": "servicenow_tickets.csv:summary",
                    "page_numbers": ["1"],
                    "url": ["N/A"],
                    "pdf_url": "servicenow_tickets.csv",
                    "text": "ServiceNow dataset analytics generated from all indexed ticket rows in snow_idx.",
                }
            ],
            "selected_category": None,
        }
        if query_request.thread_id:
            thread_store.save_message(
                thread_id=query_request.thread_id,
                role="user",
                content=query_request.user_query,
                user_id="demo",
                user_identifier="demo",
                thread_name=(query_request.user_query or "New chat")[:80],
            )
            thread_store.save_message(
                thread_id=query_request.thread_id,
                role="assistant",
                content=ticket_analytics_answer,
                user_id="demo",
                user_identifier="demo",
                thread_name=(query_request.user_query or "New chat")[:80],
            )
        return JSONResponse(content=direct_response)

    if cache_manager:
        cache_key = cache_manager.build_cache_key(
            query=f"{query_request.user_query}|selected_category={query_request.selected_category or ''}",
            retrieval_k=int(config.get("retrieval_k", 5)),
            index_name=query_request.index_name,
            model_name=config.get("llm_model", ""),
        )
        cached_response = cache_manager.get(cache_key)
        if cached_response:
            return JSONResponse(content=cached_response)

    categories = get_document_category_store().list_categories(query_request.index_name)
    requested_category = _detect_requested_category(
        query_request.index_name,
        query_request.user_query,
        query_request.selected_category,
    )
    if not requested_category and len(categories) > 1 and query_needs_clarification(query_request.user_query):
        disambiguation = build_disambiguation_payload(
            query=query_request.user_query,
            categories=categories,
            documents=get_document_category_store().list_documents(query_request.index_name),
            selected_category=query_request.selected_category,
            document_filter=query_request.document_filter,
        )
    else:
        disambiguation = None
    if disambiguation:
        if query_request.thread_id:
            thread_store.save_message(
                thread_id=query_request.thread_id,
                role="user",
                content=query_request.user_query,
                user_id="demo",
                user_identifier="demo",
                thread_name=(query_request.user_query or "New chat")[:80],
            )
            thread_store.save_message(
                thread_id=query_request.thread_id,
                role="assistant",
                content="I found multiple document categories for this question. Which category should I use?",
                user_id="demo",
                user_identifier="demo",
                thread_name=(query_request.user_query or "New chat")[:80],
            )
        clarification = disambiguation
        if cache_manager and cache_key:
            cache_manager.set(cache_key, clarification)
        return JSONResponse(content=clarification)
    
    retriever = create_retriever(query_request.index_name)

    ensemble = create_ensemble_retriever(retriever, query_request.user_query)
    LOGGER.info("Created ensemble retriever index_name=%s", query_request.index_name)
    chain = multi_modal_rag_chain_with_history(ensemble)
    LOGGER.info("Built multimodal chain for session_id=%s", query_request.session_id)
    prepared_context = await chain.prepare_context(query_request.user_query, query_request.session_id)
    retrieved_docs = _filter_docs_by_category(
        query_request.index_name,
        prepared_context["docs"],
        requested_category,
    )
    retrieved_docs = _filter_docs_by_filename(retrieved_docs, query_request.document_filter)
    prepared_context["docs"] = retrieved_docs
    processed_metadata = preprocess_metadata(retrieved_docs)
    citations_task = asyncio.create_task(
        get_citations(query_request.user_query, retrieved_docs, processed_metadata)
    )

    async def generate_response():
        buffer = ""
        try:
            async for response_chunk in chain.astream(
                {"input": query_request.user_query, "prepared_context": prepared_context},
                config={"configurable": {"session_id": query_request.session_id}}

            ):
                chunk = response_chunk.content
                buffer += chunk

                if len(buffer) > 70 or '\n' in buffer:
                    yield buffer
                    buffer = ""
            if buffer:
                yield buffer
        except Exception as e:
            LOGGER.exception("Error during response streaming")
            yield f"Error during processing: {e}"

        citations = await citations_task
        yield f"\n<<CITATIONS_START>>{json.dumps(citations)}<<CITATIONS_END>>\n"


    accept_header = request.headers.get('accept', '')
    user_agent = request.headers.get('user-agent', '').lower() if request else ''
    if 'text/event-stream' in accept_header or 'curl' in user_agent:

        return StreamingResponse(generate_response(), media_type="text/plain")
    else:
        response_chunks = []
        async for chunk in generate_response():
            response_chunks.append(chunk)
        response_text = "".join(response_chunks)



        end_time = time.time()
        if "<<CITATIONS_START>>" in response_text and "<<CITATIONS_END>>" in response_text:
            response_body, citations_part = response_text.split("<<CITATIONS_START>>", 1)
            citations_json, _ = citations_part.split("<<CITATIONS_END>>", 1)
            citations_json = citations_json.strip()
            try:
                citations = json.loads(citations_json)
            except json.JSONDecodeError:
                citations = []
        else:
            response_body = response_text
            citations = []


        query = query_request.user_query
        response_content = response_body.strip()

        time_of_query_str = time_of_query.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        response_time_seconds = end_time - start_time

        response_time_str = f"{response_time_seconds:.2f}"

        response_time_str = response_time_str[:10]

        citation_url_json = json.dumps(citations)

        conversation_data = {
            'chat_id': query_request.session_id,
            'query': query,
            'response': response_content,
            'citation_url': citation_url_json,
            'time_of_query': time_of_query_str,
            'response_time': response_time_str,  
        }
        LOGGER.info("Conversation turn completed metadata=%s", conversation_data)

        full_response = {
            "mode": "answer",
            "response": {
                "content": response_body.strip()
            },
            "citation": citations,
            "selected_category": requested_category,
        }
        if query_request.thread_id:
            thread_store.save_message(
                thread_id=query_request.thread_id,
                role="user",
                content=query_request.user_query,
                user_id="demo",
                user_identifier="demo",
                thread_name=(query_request.user_query or "New chat")[:80],
            )
            thread_store.save_message(
                thread_id=query_request.thread_id,
                role="assistant",
                content=response_body.strip(),
                user_id="demo",
                user_identifier="demo",
                thread_name=(query_request.user_query or "New chat")[:80],
            )
        if cache_manager and cache_key:
            cache_manager.set(cache_key, full_response)
        return JSONResponse(content=full_response)



@app.post("/SFRAG/ingest")
def ingest_document(
    index_name: str = Form(...),
    s3_key: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    index_name = _validate_index_name(index_name)
    if not file and not s3_key:
        raise HTTPException(status_code=400, detail="Either file or s3_key is required.")

    local_path = None
    temp_dir = None
    file_name = getattr(file, "filename", None) or os.path.basename(s3_key or "")

    try:
        if s3_key:
            local_path, file_bytes, content_type, input_file_url = _download_s3_object_to_temp(index_name, s3_key, None)
        else:
            assert file is not None
            file_bytes = file.file.read()
            content_type = file.content_type or ""
            temp_dir = _ensure_temp_dir("direct_ingest_tmp", uuid.uuid4().hex)
            local_path = str(temp_dir / file.filename)
            Path(local_path).write_bytes(file_bytes)
            if normalize_extension(file.filename) == ".pdf":
                container_name = f"{BASE_CONTAINER_NAME}/Project/{index_name}"
                upload_to_blob(file, STORAGE_ACCOUNT_NAME, container_name, local_file_path=local_path)
                input_file_url = get_presigned_url(file.filename, STORAGE_ACCOUNT_NAME, container_name)
            else:
                input_file_url = file.filename

        return _ingest_local_file(
            index_name=index_name,
            file_name=file_name,
            content_type=content_type,
            file_bytes=file_bytes,
            local_path=local_path,
            input_file_url=input_file_url,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("Error during ingest processing index_name=%s file_name=%s", index_name, file_name)
        return {"status": "Error", "message": str(exc)}
    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if s3_key and local_path:
            temp_path = Path(local_path).parent
            if temp_path.exists():
                shutil.rmtree(temp_path, ignore_errors=True)


@app.post("/SFRAG/ingest-async")
async def ingest_document_async(request: S3IngestRequest):
    request.index_name = _validate_index_name(request.index_name)
    job_id = uuid.uuid4().hex
    get_ingest_job_store().create_job(job_id, request.index_name, os.path.basename(request.s3_key), "document")
    try:
        get_ingest_job_store().update_job(job_id, status="running")
        result = ingest_document(index_name=request.index_name, s3_key=request.s3_key, file=None)
        get_ingest_job_store().update_job(job_id, status="completed", result=result)
    except Exception as exc:
        get_ingest_job_store().update_job(job_id, status="failed", error=str(exc))
    return {"job_id": job_id, "status": "queued"}


@app.post("/SFRAG/ingest-tickets")
def ingest_tickets(index_name: str = Form(...), file: UploadFile = File(...)):
    index_name = _validate_index_name(index_name)
    file_bytes = file.file.read()
    try:
        validate_ticket_upload(file.filename, file.content_type or "", len(file_bytes))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    temp_dir = _ensure_temp_dir("ticket_ingest_tmp", uuid.uuid4().hex)
    local_path = temp_dir / file.filename
    local_path.write_bytes(file_bytes)

    try:
        ticket_chunks = extract_ticket_chunks(str(local_path))
        result = _index_text_document(
            index_name=index_name,
            file_name=file.filename,
            input_file_url=file.filename,
            content_type=file.content_type or "",
            file_size=len(file_bytes),
            text_chunks=ticket_chunks,
        )
        get_document_category_store().upsert_document(
            index_name=index_name,
            filename=file.filename,
            category="support_tickets",
            source_type="support_tickets",
            content_type=file.content_type or "",
            size_bytes=len(file_bytes),
            storage_url=file.filename,
        )
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/SFRAG/retrieval-image")
async def retrieval_from_image(
    index_name: str = Form(...),
    session_id: str = Form(...),
    thread_id: str | None = Form(None),
    prompt: str | None = Form(None),
    file: UploadFile = File(...),
):
    index_name = _validate_index_name(index_name)
    content_type = (file.content_type or "").lower()
    file_bytes = await file.read()
    if content_type not in CHAT_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type. Allowed: PNG, JPG, JPEG, WEBP.")
    if len(file_bytes) > MAX_CHAT_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 5 MB limit.")

    extracted = _extract_query_from_image(file_bytes, prompt_hint=prompt)
    query_text = extracted["retrieval_query"] or (prompt or "").strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Could not determine a usable question from the image.")

    request_scope = {"type": "http", "method": "POST", "headers": []}
    synthetic_request = Request(request_scope)
    response = await multi_modal_query(
        QueryRequest(
            user_query=query_text,
            index_name=index_name,
            session_id=session_id,
            thread_id=thread_id,
        ),
        synthetic_request,
    )

    if isinstance(response, JSONResponse):
        payload = json.loads(response.body.decode("utf-8"))
    else:
        payload = {"mode": "answer", "response": {"content": ""}, "citation": []}

    payload["image_query"] = {
        "extracted_text": extracted["extracted_text"],
        "intent": extracted["intent"],
        "retrieval_query": query_text,
        "filename": file.filename,
    }
    return JSONResponse(content=payload)


@app.get("/SFRAG/analytics/datasets")
async def list_analytics_datasets():
    return {"datasets": get_analytics_store().list_datasets()}


@app.get("/SFRAG/analytics/schema/{dataset_id}")
async def get_analytics_schema(dataset_id: str):
    normalized = _validate_index_name(dataset_id)
    schema = get_analytics_store().get_schema(normalized)
    if not schema:
        raise HTTPException(status_code=404, detail="Analytics dataset not found")
    return {"dataset_id": normalized, "schema": schema}


@app.get("/SFRAG/analytics/summary/{dataset_id}")
async def get_analytics_summary(dataset_id: str):
    normalized = _validate_index_name(dataset_id)
    cached = get_analytics_store().load_metrics_cache(normalized)
    if not cached:
        raise HTTPException(status_code=404, detail="Analytics summary not found")
    return cached


@app.get("/SFRAG/analytics/metrics/{dataset_id}")
async def get_analytics_metrics(dataset_id: str):
    normalized = _validate_index_name(dataset_id)
    cached = get_analytics_store().load_metrics_cache(normalized)
    if not cached:
        raise HTTPException(status_code=404, detail="Analytics metrics not found")
    return _dataset_metrics_response(
        normalized,
        cached.get("metrics", []),
        cached.get("summary", {}),
        cached.get("source", "cache"),
    )


@app.post("/SFRAG/analytics/upload")
async def upload_analytics_dataset(dataset_id: str = Form(...), file: UploadFile = File(...)):
    normalized = _validate_index_name(dataset_id)
    file_bytes = await file.read()
    analytics_store = get_analytics_store()
    rows = analytics_store.parse_structured_file(file.filename, file_bytes)
    if not rows:
        raise HTTPException(status_code=400, detail="No structured rows found in the uploaded dataset.")

    schema_profile = analytics_store.profile_schema(rows)
    storage_info = analytics_store.store_dataset(
        dataset_id=normalized,
        source_name=file.filename,
        file_bytes=file_bytes,
        rows=rows,
        schema_profile=schema_profile,
    )
    metrics = discover_metrics(normalized, schema_profile, storage_info["table_name"])
    summary = analytics_store.build_summary_metrics(rows, schema_profile)
    analytics_store.cache_metrics(normalized, summary, metrics)
    return {
        "status": "dataset_uploaded",
        "dataset_id": normalized,
        "table_name": storage_info["table_name"],
        "row_count": len(rows),
        "schema": schema_profile,
        "metrics": metrics,
        "summary": summary,
        "source": "s3",
    }


@app.post("/SFRAG/analytics/query")
async def query_analytics(request: AnalyticsQueryRequest):
    dataset_id = _validate_index_name(request.dataset_id)
    analytics_store = get_analytics_store()
    schema = analytics_store.get_schema(dataset_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Analytics dataset not found")

    classification = classify_query_route(request.question, schema)
    table_name = analytics_store.get_table_name(dataset_id)
    cached_bundle = analytics_store.load_metrics_cache(dataset_id) or {}
    cached_metric = _match_cached_metric(request.question, cached_bundle.get("metrics", []))

    if cached_metric:
        metric_id = str(cached_metric.get("metric_id", ""))
        cached_metric_result = analytics_store.load_metric_result(dataset_id, metric_id) if metric_id else None
        if cached_metric_result:
            cached_metric_result["source"] = "cache"
            cached_metric_result["route"] = classification["route"]
            cached_metric_result["reason"] = classification["reason"]
            return cached_metric_result
        sql = str(cached_metric.get("sql", "")).strip()
        chart_type = str(cached_metric.get("chart_type", "table"))
    else:
        sql, chart_type = generate_sql_for_question(
            request.question,
            dataset_id=dataset_id,
            table_name=table_name,
            schema_profile=schema,
        )
    validated_sql = validate_sql(sql, allowed_tables={table_name})
    result = analytics_store.execute_query(dataset_id=dataset_id, sql=validated_sql)
    response_payload = {
        "dataset_id": dataset_id,
        "route": classification["route"],
        "reason": classification["reason"],
        "sql": validated_sql,
        "result": result,
        "chart_type": chart_type,
        "answer": _analytics_summary_text(request.question, result, chart_type),
        "source": result.get("source", "athena"),
    }
    if cached_metric:
        analytics_store.cache_metric_result(dataset_id, str(cached_metric.get("metric_id", "adhoc_metric")), response_payload)
    return response_payload


@app.post("/SFRAG/analytics/chat")
async def chat_analytics(request: AnalyticsQueryRequest):
    return await query_analytics(request)

