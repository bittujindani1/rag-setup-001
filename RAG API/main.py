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
from pydantic import BaseModel
from requests_aws4auth import AWS4Auth

from citations import get_citations
from customchain import multi_modal_rag_chain_with_history
from customretriever import create_ensemble_retriever, create_retriever
from document_router import build_disambiguation_payload
from document_support import (
    MAX_UPLOAD_BYTES,
    build_text_result,
    extract_text_chunks,
    extract_ticket_chunks,
    infer_category,
    normalize_extension,
    query_needs_clarification,
    validate_ticket_upload,
    validate_upload,
)
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
    get_document_category_store,
    get_feedback_store,
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
    category = infer_category(file_name, texts_list[:3])
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
        validate_upload(file_name, content_type, file_size)

        filenames_in_index = list_all_filenames_in_index(index_name)
        if file_name in filenames_in_index:
            delete_documents_by_filename(index_name, file_name)
            get_document_category_store().delete_document(index_name, file_name)

        if extension != ".pdf":
            text_chunks = extract_text_chunks(local_path)
            if not text_chunks:
                raise HTTPException(status_code=400, detail="Could not extract usable text from the uploaded document.")
            return _index_text_document(
                index_name=index_name,
                file_name=file_name,
                input_file_url=input_file_url,
                content_type=content_type,
                file_size=file_size,
                text_chunks=text_chunks,
            )

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
        category = infer_category(file_name, texts_list[:3])
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


@app.post("/SFRAG/uploads/presign")
async def create_presigned_upload(request: PresignUploadRequest):
    request.index_name = _validate_index_name(request.index_name)
    try:
        validate_upload(request.filename, request.content_type, 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    config = get_config()
    object_key = f"{request.index_name}/{uuid.uuid4().hex}-{request.filename}"
    s3_client = boto3.client("s3", region_name=config["aws_region"])
    try:
        presigned = s3_client.generate_presigned_post(
            config["s3_bucket_documents"],
            object_key,
            Fields={"Content-Type": request.content_type},
            Conditions=[["content-length-range", 1, MAX_UPLOAD_BYTES], {"Content-Type": request.content_type}],
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

