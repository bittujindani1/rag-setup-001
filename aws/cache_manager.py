from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Optional

import boto3
from aws.metrics import MetricsCollector


LOGGER = logging.getLogger(__name__)
_PUNCTUATION_RE = re.compile(r"[^\w\s]")


class DynamoDBCacheManager:
    def __init__(
        self,
        table_name: str,
        region_name: str,
        ttl_seconds: int = 86400,
        metrics_collector: MetricsCollector | None = None,
    ) -> None:
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)
        self.ttl_seconds = ttl_seconds
        self.metrics = metrics_collector

    @staticmethod
    def _normalize_query(query: str) -> str:
        normalized = _PUNCTUATION_RE.sub(" ", query.lower())
        return " ".join(normalized.split())

    @classmethod
    def build_cache_key(
        cls,
        query: str,
        retrieval_k: int,
        index_name: str,
        model_name: str,
        corpus_version: str = "",
    ) -> str:
        normalized_query = cls._normalize_query(query)
        raw = f"{normalized_query}:{retrieval_k}:{index_name}:{model_name}:{corpus_version}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get(self, cache_key: str) -> Optional[Any]:
        item = self.table.get_item(Key={"query_hash": cache_key}).get("Item")
        if not item:
            if self.metrics:
                self.metrics.record_cache_miss()
            LOGGER.info("Cache miss key=%s", cache_key)
            return None
        expires_at = int(item.get("expires_at", "0"))
        if expires_at and expires_at < int(time.time()):
            if self.metrics:
                self.metrics.record_cache_miss()
            LOGGER.info("Cache expired key=%s", cache_key)
            return None
        payload = item.get("response")
        if self.metrics:
            self.metrics.record_cache_hit()
        LOGGER.info("Cache hit key=%s", cache_key)
        return json.loads(payload) if isinstance(payload, str) else payload

    def set(self, cache_key: str, response: Any) -> None:
        self.table.put_item(
            Item={
                "query_hash": cache_key,
                "response": json.dumps(response),
                "expires_at": int(time.time()) + self.ttl_seconds,
            }
        )
        LOGGER.info("Cache write key=%s ttl_seconds=%s", cache_key, self.ttl_seconds)
