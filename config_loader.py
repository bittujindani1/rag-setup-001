from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


_DEFAULTS: Dict[str, Any] = {
    "vector_store": "s3",
    "doc_store": "dynamodb",
    "chat_history": "dynamodb",
    "cache": "dynamodb",
    "llm": "bedrock",
    "embedding_model": "amazon.titan-embed-text-v2:0",
    "llm_model": "anthropic.claude-3-haiku-20240307-v1:0",
    "bedrock_fallback_model": "anthropic.claude-3-sonnet-20240229-v1:0",
    "aws_region": os.getenv("AWS_REGION", "ap-south-1"),
    "retrieval_k": 5,
    "cache_ttl_seconds": 86400,
    "dynamodb_rate_limit_table": "rag_rate_limits",
    "dynamodb_thread_table": "rag_chat_threads",
    "dynamodb_document_categories_table": "rag_document_categories",
    "dynamodb_ingest_jobs_table": "rag_ingest_jobs",
    "dynamodb_feedback_table": "rag_user_feedback",
    "s3_bucket_analytics": "rag-serverless-analytics",
    "glue_analytics_database": "rag_serverless_analytics",
    "athena_workgroup": "primary",
    "analytics_cache_ttl_seconds": 3600,
    "rate_limit_requests_per_minute": 15,
    "reranker": {
        "enabled": True,
        "initial_k": 20,
        "final_k": 4,
    },
}


def _config_path() -> Path:
    env_path = os.getenv("APP_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parent / "config" / "aws_config.yaml"


def load_app_config() -> Dict[str, Any]:
    path = _config_path()
    data: Dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                data = loaded

    merged = {**_DEFAULTS, **data}

    env_overrides = {
        "vector_store": os.getenv("VECTOR_STORE"),
        "doc_store": os.getenv("DOC_STORE"),
        "chat_history": os.getenv("CHAT_HISTORY_STORE"),
        "cache": os.getenv("CACHE_STORE"),
        "llm": os.getenv("LLM_PROVIDER"),
        "embedding_model": os.getenv("EMBEDDING_MODEL"),
        "llm_model": os.getenv("LLM_MODEL") or os.getenv("BEDROCK_MODEL"),
        "bedrock_fallback_model": os.getenv("BEDROCK_FALLBACK_MODEL"),
        "aws_region": os.getenv("AWS_REGION"),
        "s3_bucket_documents": os.getenv("S3_BUCKET_DOCUMENTS"),
        "s3_bucket_vectors": os.getenv("S3_BUCKET_VECTORS"),
        "s3_bucket_extracted": os.getenv("S3_BUCKET_EXTRACTED"),
        "s3_bucket_analytics": os.getenv("S3_BUCKET_ANALYTICS"),
        "dynamodb_chat_history_table": os.getenv("DYNAMODB_CHAT_HISTORY_TABLE"),
        "dynamodb_query_cache_table": os.getenv("DYNAMODB_QUERY_CACHE_TABLE"),
        "dynamodb_doc_store_table": os.getenv("DYNAMODB_DOC_STORE_TABLE"),
        "dynamodb_filename_index_table": os.getenv("DYNAMODB_FILENAME_INDEX_TABLE"),
        "dynamodb_rate_limit_table": os.getenv("DYNAMODB_RATE_LIMIT_TABLE"),
        "dynamodb_thread_table": os.getenv("DYNAMODB_THREAD_TABLE"),
        "dynamodb_document_categories_table": os.getenv("DYNAMODB_DOCUMENT_CATEGORIES_TABLE"),
        "dynamodb_ingest_jobs_table": os.getenv("DYNAMODB_INGEST_JOBS_TABLE"),
        "dynamodb_feedback_table": os.getenv("DYNAMODB_FEEDBACK_TABLE"),
        "glue_analytics_database": os.getenv("GLUE_ANALYTICS_DATABASE"),
        "athena_workgroup": os.getenv("ATHENA_WORKGROUP"),
        "frontend_url": os.getenv("FRONTEND_URL"),
    }
    for key, value in env_overrides.items():
        if value:
            merged[key] = value

    if os.getenv("RETRIEVAL_K"):
        merged["retrieval_k"] = int(os.getenv("RETRIEVAL_K", "5"))
    if os.getenv("CACHE_TTL_SECONDS"):
        merged["cache_ttl_seconds"] = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
    if os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE"):
        merged["rate_limit_requests_per_minute"] = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "15"))
    if os.getenv("ANALYTICS_CACHE_TTL_SECONDS"):
        merged["analytics_cache_ttl_seconds"] = int(os.getenv("ANALYTICS_CACHE_TTL_SECONDS", "3600"))

    return merged
