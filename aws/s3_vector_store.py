from __future__ import annotations

import gzip
import json
import logging
import time
import uuid
from typing import Dict, Iterable, List

import boto3
import numpy as np
from botocore.exceptions import ClientError
from langchain.schema import Document
from aws.metrics import MetricsCollector


LOGGER = logging.getLogger(__name__)


class S3VectorStore:
    def __init__(self, bucket_name: str, index_name: str, embedding_client, metrics_collector: MetricsCollector | None = None) -> None:
        self.bucket_name = bucket_name
        self.index_name = index_name
        self.embedding_client = embedding_client
        self.metrics = metrics_collector
        self.s3 = boto3.client("s3", region_name=embedding_client.region_name)
        self._index_cache: List[Dict] | None = None

    def _prefix(self) -> str:
        return f"indices/{self.index_name}/vectors/"

    def _key(self, doc_id: str) -> str:
        return f"{self._prefix()}{doc_id}.json.gz"

    def _index_key(self) -> str:
        return f"{self._prefix()}embeddings_index.json"

    def _read_json(self, key: str, compressed: bool = False) -> Dict:
        data = self.s3.get_object(Bucket=self.bucket_name, Key=key)
        body = data["Body"].read()
        if compressed:
            body = gzip.decompress(body)
        return json.loads(body)

    def _write_index(self, index_entries: List[Dict]) -> None:
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=self._index_key(),
            Body=json.dumps(index_entries).encode("utf-8"),
            ContentType="application/json",
        )
        self._index_cache = index_entries

    def _load_index(self) -> List[Dict]:
        if self._index_cache is not None:
            return self._index_cache
        try:
            payload = self._read_json(self._index_key())
            self._index_cache = payload if isinstance(payload, list) else []
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code not in {"NoSuchKey", "404"}:
                LOGGER.exception("Failed to load embeddings index for %s", self.index_name)
            self._index_cache = []
        return self._index_cache

    def add_documents(self, documents: Iterable[Document]) -> None:
        index_entries = self._load_index().copy()
        document_list = list(documents)
        embeddings = self.embedding_client.embed_texts(
            [document.page_content for document in document_list]
        )
        if len(embeddings) != len(document_list):
            LOGGER.warning(
                "Embedding batch size mismatch expected=%s actual=%s; retrying per document",
                len(document_list),
                len(embeddings),
            )
            embeddings = [self.embedding_client.embed_text(document.page_content) for document in document_list]
        for document, embedding in zip(document_list, embeddings):
            doc_id = document.metadata.get("doc_id") or str(uuid.uuid4())
            payload = {
                "doc_id": doc_id,
                "page_content": document.page_content,
                "embedding": embedding,
                "metadata": document.metadata,
            }
            compressed = gzip.compress(json.dumps(payload).encode("utf-8"))
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=self._key(doc_id),
                Body=compressed,
                ContentType="application/json",
                ContentEncoding="gzip",
            )
            index_entries = [entry for entry in index_entries if entry.get("doc_id") != doc_id]
            index_entries.append(
                {
                    "doc_id": doc_id,
                    "key": self._key(doc_id),
                    "embedding": embedding,
                    "page_content": document.page_content,
                    "metadata": document.metadata,
                }
            )
        self._write_index(index_entries)
        LOGGER.info("TOTAL_CHUNKS_INDEXED=%s index=%s", len(index_entries), self.index_name)
        if len(index_entries) > 100000:
            LOGGER.warning(
                "TOTAL_CHUNKS_INDEXED=%s for index=%s exceeds 100000; consider OpenSearch Serverless",
                len(index_entries),
                self.index_name,
            )

    def similarity_search(self, query: str, k: int = 20) -> List[Document]:
        start = time.perf_counter()
        query_embedding = self.embedding_client.embed_text(query)
        index_entries = self._load_index()
        if not query_embedding or not index_entries:
            return []

        valid_entries = [
            entry
            for entry in index_entries
            if isinstance(entry.get("embedding"), list) and entry.get("embedding")
        ]
        if not valid_entries:
            return []

        matrix = np.array([entry["embedding"] for entry in valid_entries], dtype=float)
        query_vector = np.array(query_embedding, dtype=float)
        matrix_norms = np.linalg.norm(matrix, axis=1)
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            return []
        safe_norms = np.where(matrix_norms == 0, 1.0, matrix_norms)
        scores = np.dot(matrix, query_vector) / (safe_norms * query_norm)
        top_indices = np.argsort(scores)[::-1][:k]

        documents: List[Document] = []
        for entry_index in top_indices:
            entry = valid_entries[int(entry_index)]
            score = float(scores[int(entry_index)])
            page_content = entry.get("page_content", "")
            metadata = dict(entry.get("metadata", {}))
            metadata.update(
                {
                    "text": page_content,
                    "score": score,
                    "vector_score": score,
                    "page_number": metadata.get("page_number", metadata.get("page_num")),
                    "filename": metadata.get("filename"),
                }
            )
            documents.append(
                Document(
                    page_content=page_content,
                    metadata=metadata,
                )
            )
        latency_ms = (time.perf_counter() - start) * 1000
        LOGGER.info(
            "Vector search latency_ms=%.2f index=%s candidates=%s returned=%s",
            latency_ms,
            self.index_name,
            len(index_entries),
            len(documents),
        )
        if self.metrics:
            self.metrics.record_vector_search_latency(latency_ms)
        return documents

    def list_all_filenames(self) -> List[str]:
        filenames = {
            entry.get("metadata", {}).get("filename")
            for entry in self._load_index()
            if entry.get("metadata", {}).get("filename")
        }
        return sorted(filenames)

    def delete_documents_by_filename(self, filename: str) -> None:
        index_entries = self._load_index().copy()
        to_delete = [entry for entry in index_entries if entry.get("metadata", {}).get("filename") == filename]
        if to_delete:
            self.s3.delete_objects(
                Bucket=self.bucket_name,
                Delete={"Objects": [{"Key": entry["key"]} for entry in to_delete]},
            )
        remaining = [entry for entry in index_entries if entry.get("metadata", {}).get("filename") != filename]
        self._write_index(remaining)
