from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


_BLOCKED_LOCAL_KEYS = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "AWS_PROFILE",
    "S3_BUCKET_DOCUMENTS",
    "S3_BUCKET_VECTORS",
    "S3_BUCKET_EXTRACTED",
    "DYNAMODB_CHAT_HISTORY_TABLE",
    "DYNAMODB_QUERY_CACHE_TABLE",
    "DYNAMODB_DOC_STORE_TABLE",
    "DYNAMODB_FILENAME_INDEX_TABLE",
    "DYNAMODB_RATE_LIMIT_TABLE",
    "VECTOR_STORE",
    "DOC_STORE",
    "CHAT_HISTORY_STORE",
    "CACHE_STORE",
    "LLM_PROVIDER",
    "BEDROCK_MODEL",
    "LLM_MODEL",
    "BEDROCK_FALLBACK_MODEL",
    "EMBEDDING_MODEL",
}


def bootstrap_env(local_env_path: str | os.PathLike[str] | None = None) -> None:
    root_dir = Path(__file__).resolve().parent
    root_env = root_dir / ".env"

    if root_env.exists():
        load_dotenv(root_env, override=False)

    if not local_env_path:
        return

    local_path = Path(local_env_path)
    if not local_path.exists():
        return

    for key, value in dotenv_values(local_path).items():
        if not key or value is None:
            continue
        if key in _BLOCKED_LOCAL_KEYS or key.startswith("AWS_"):
            continue
        os.environ.setdefault(key, value)
