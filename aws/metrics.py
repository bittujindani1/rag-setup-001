from __future__ import annotations

import logging
from threading import Lock


LOGGER = logging.getLogger(__name__)


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = Lock()
        self._cache_hits = 0
        self._cache_misses = 0
        self._embedding_samples: list[float] = []
        self._vector_samples: list[float] = []
        self._llm_samples: list[float] = []
        self._documents_indexed = 0

    def record_cache_hit(self) -> None:
        with self._lock:
            self._cache_hits += 1
        LOGGER.info("CACHE_HIT")

    def record_cache_miss(self) -> None:
        with self._lock:
            self._cache_misses += 1
        LOGGER.info("CACHE_MISS")

    def record_embedding_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._embedding_samples.append(latency_ms)
        LOGGER.info("BEDROCK_LATENCY type=embedding latency_ms=%.2f", latency_ms)

    def record_vector_search_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._vector_samples.append(latency_ms)
        LOGGER.info("VECTOR_SEARCH_LATENCY latency_ms=%.2f", latency_ms)

    def record_llm_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._llm_samples.append(latency_ms)
        LOGGER.info("BEDROCK_LATENCY type=llm latency_ms=%.2f", latency_ms)

    def increment_documents_indexed(self, count: int) -> None:
        if count <= 0:
            return
        with self._lock:
            self._documents_indexed += count
            total = self._documents_indexed
        LOGGER.info("TOTAL_CHUNKS_INDEXED=%s", total)
        if total > 100000:
            LOGGER.warning(
                "TOTAL_CHUNKS_INDEXED=%s exceeds 100000; consider OpenSearch Serverless for lower query latency",
                total,
            )

    @staticmethod
    def _avg(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            total_cache = self._cache_hits + self._cache_misses
            cache_hit_rate = (self._cache_hits / total_cache) if total_cache else 0.0
            return {
                "cache_hit_rate": round(cache_hit_rate, 2),
                "avg_embedding_latency_ms": self._avg(self._embedding_samples),
                "avg_vector_search_latency_ms": self._avg(self._vector_samples),
                "avg_llm_latency_ms": self._avg(self._llm_samples),
                "documents_indexed": self._documents_indexed,
            }
