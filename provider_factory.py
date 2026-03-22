from __future__ import annotations

from functools import lru_cache

from config_loader import load_app_config
from aws.bedrock_client import BedrockClient
from aws.analytics_store import AnalyticsStore
from aws.cache_manager import DynamoDBCacheManager
from aws.dynamodb_store import (
    ConversationAuditStore,
    DynamoDBChatMessageHistory,
    DynamoDBDocumentCategoryStore,
    DynamoDBDocStore,
    DynamoDBFeedbackStore,
    DynamoDBFilenameIndex,
    DynamoDBIngestJobStore,
)
from aws.metrics import MetricsCollector
from aws.rate_limiter import DynamoDBRateLimiter
from aws.s3_vector_store import S3VectorStore


@lru_cache(maxsize=1)
def get_config():
    return load_app_config()


@lru_cache(maxsize=1)
def get_bedrock_client() -> BedrockClient:
    config = get_config()
    return BedrockClient(
        region_name=config["aws_region"],
        llm_model=config["llm_model"],
        fallback_llm_model=config["bedrock_fallback_model"],
        embedding_model=config["embedding_model"],
        metrics_collector=get_metrics_collector(),
    )


@lru_cache(maxsize=1)
def get_cache_manager() -> DynamoDBCacheManager:
    config = get_config()
    return DynamoDBCacheManager(
        table_name=config["dynamodb_query_cache_table"],
        region_name=config["aws_region"],
        ttl_seconds=int(config["cache_ttl_seconds"]),
        metrics_collector=get_metrics_collector(),
    )


@lru_cache(maxsize=1)
def get_doc_store() -> DynamoDBDocStore:
    config = get_config()
    return DynamoDBDocStore(
        table_name=config["dynamodb_doc_store_table"],
        region_name=config["aws_region"],
    )


@lru_cache(maxsize=1)
def get_filename_index() -> DynamoDBFilenameIndex:
    config = get_config()
    return DynamoDBFilenameIndex(
        table_name=config["dynamodb_filename_index_table"],
        region_name=config["aws_region"],
    )


@lru_cache(maxsize=1)
def get_document_category_store() -> DynamoDBDocumentCategoryStore:
    config = get_config()
    return DynamoDBDocumentCategoryStore(
        table_name=config["dynamodb_document_categories_table"],
        region_name=config["aws_region"],
    )


@lru_cache(maxsize=1)
def get_ingest_job_store() -> DynamoDBIngestJobStore:
    config = get_config()
    return DynamoDBIngestJobStore(
        table_name=config["dynamodb_ingest_jobs_table"],
        region_name=config["aws_region"],
    )


@lru_cache(maxsize=1)
def get_feedback_store() -> DynamoDBFeedbackStore:
    config = get_config()
    return DynamoDBFeedbackStore(
        table_name=config["dynamodb_feedback_table"],
        region_name=config["aws_region"],
    )


@lru_cache(maxsize=1)
def get_analytics_store() -> AnalyticsStore:
    config = get_config()
    return AnalyticsStore(
        region_name=config["aws_region"],
        bucket_name=config["s3_bucket_analytics"],
        glue_database=config["glue_analytics_database"],
        athena_workgroup=config.get("athena_workgroup", "primary"),
        metrics_ttl_seconds=int(config.get("analytics_cache_ttl_seconds", 3600)),
    )


def build_chat_history(session_id: str) -> DynamoDBChatMessageHistory:
    config = get_config()
    return DynamoDBChatMessageHistory(
        table_name=config["dynamodb_chat_history_table"],
        session_id=session_id,
        region_name=config["aws_region"],
    )


@lru_cache(maxsize=32)
def get_s3_vector_store(index_name: str) -> S3VectorStore:
    config = get_config()
    return S3VectorStore(
        bucket_name=config["s3_bucket_vectors"],
        index_name=index_name,
        embedding_client=get_bedrock_client(),
        metrics_collector=get_metrics_collector(),
    )


@lru_cache(maxsize=1)
def get_conversation_audit_store() -> ConversationAuditStore:
    config = get_config()
    return ConversationAuditStore(
        table_name=config["dynamodb_chat_history_table"],
        region_name=config["aws_region"],
    )


@lru_cache(maxsize=1)
def get_metrics_collector() -> MetricsCollector:
    return MetricsCollector()


@lru_cache(maxsize=1)
def get_rate_limiter() -> DynamoDBRateLimiter:
    config = get_config()
    return DynamoDBRateLimiter(
        table_name=config["dynamodb_rate_limit_table"],
        region_name=config["aws_region"],
        limit_per_minute=int(config["rate_limit_requests_per_minute"]),
    )
