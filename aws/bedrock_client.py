from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Iterable, Iterator, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


LOGGER = logging.getLogger(__name__)
EMBEDDING_BATCH_SIZE = 20


class BedrockClient:
    def __init__(
        self,
        region_name: str,
        llm_model: str,
        fallback_llm_model: str,
        embedding_model: str,
        metrics_collector=None,
    ) -> None:
        self.region_name = region_name
        self.llm_model = llm_model
        self.fallback_llm_model = fallback_llm_model
        self.embedding_model = embedding_model
        self.metrics = metrics_collector
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region_name,
            config=Config(
                connect_timeout=10,
                read_timeout=120,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        self.agent_runtime_client = boto3.client(
            "bedrock-agent-runtime",
            region_name=region_name,
            config=Config(
                connect_timeout=10,
                read_timeout=120,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        self.rerank_model_arn = os.getenv("BEDROCK_RERANK_MODEL_ARN", "").strip()
        self.rerank_model_id = os.getenv("BEDROCK_RERANK_MODEL_ID", "amazon.rerank-v1:0").strip()
        if not self.rerank_model_arn and self.rerank_model_id:
            self.rerank_model_arn = f"arn:aws:bedrock:{region_name}::foundation-model/{self.rerank_model_id}"
            LOGGER.info("Using derived Bedrock rerank model ARN for model_id=%s", self.rerank_model_id)

    def _invoke_json(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.invoke_model(
                modelId=model_id,
                body=json.dumps(payload),
                contentType="application/json",
                accept="application/json",
            )
            raw_body = response["body"].read()
            if not raw_body:
                LOGGER.warning("Bedrock returned an empty body for model %s", model_id)
                return {}
            try:
                return json.loads(raw_body)
            except json.JSONDecodeError:
                LOGGER.exception("Bedrock returned invalid JSON for model %s", model_id)
                return {}
        except (BotoCoreError, ClientError, TimeoutError):
            LOGGER.exception("Bedrock invocation failed for model %s", model_id)
            return {}

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        content = data.get("content", [])
        if isinstance(content, list):
            parts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
            text = "".join(parts).strip()
            if text:
                return text

        completion = data.get("completion")
        if isinstance(completion, str) and completion.strip():
            return completion.strip()

        output_text = data.get("outputText")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        results = data.get("results")
        if isinstance(results, list):
            parts = [item.get("outputText", "") for item in results if isinstance(item, dict)]
            text = "".join(parts).strip()
            if text:
                return text

        LOGGER.warning("Bedrock response did not contain expected text fields: %s", list(data.keys()))
        return ""

    def embed_text(self, text: str) -> List[float]:
        start = time.perf_counter()
        payload = {"inputText": text}
        data = self._invoke_json(self.embedding_model, payload)
        embedding = data.get("embedding", [])
        latency_ms = (time.perf_counter() - start) * 1000
        if self.metrics:
            self.metrics.record_embedding_latency(latency_ms)
        LOGGER.info("Embedding latency_ms=%.2f model=%s vector_size=%s", latency_ms, self.embedding_model, len(embedding))
        if not isinstance(embedding, list):
            LOGGER.warning("Unexpected embedding format from Bedrock model %s", self.embedding_model)
            return []
        return embedding

    def _embed_batch_once(self, texts: List[str]) -> List[List[float]] | None:
        if not texts:
            return []

        batch_payloads = (
            {"inputTexts": texts},
            {"texts": texts},
        )
        for payload in batch_payloads:
            data = self._invoke_json(self.embedding_model, payload)
            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list):
                continue
            normalized: List[List[float]] = []
            valid = True
            for embedding in embeddings:
                if not isinstance(embedding, list):
                    valid = False
                    break
                normalized.append(embedding)
            if valid and len(normalized) == len(texts):
                return normalized
        return None

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        text_list = list(texts)
        if not text_list:
            return []

        embeddings: List[List[float]] = []
        for index in range(0, len(text_list), EMBEDDING_BATCH_SIZE):
            batch = text_list[index : index + EMBEDDING_BATCH_SIZE]
            start = time.perf_counter()
            batch_embeddings = self._embed_batch_once(batch)
            latency_ms = (time.perf_counter() - start) * 1000

            if batch_embeddings is None:
                LOGGER.warning(
                    "Batch embeddings unavailable for model=%s batch_size=%s; falling back to single requests",
                    self.embedding_model,
                    len(batch),
                )
                embeddings.extend(self.embed_text(text) for text in batch)
                continue

            if self.metrics:
                self.metrics.record_embedding_latency(latency_ms)
            LOGGER.info(
                "Embedding batch latency_ms=%.2f model=%s batch_size=%s",
                latency_ms,
                self.embedding_model,
                len(batch),
            )
            embeddings.extend(batch_embeddings)

        return embeddings

    def _invoke_with_fallback(
        self,
        payload: dict[str, Any],
        multimodal: bool = False,
    ) -> tuple[str, str]:
        start = time.perf_counter()
        data = self._invoke_json(self.llm_model, payload)
        text = self._extract_text(data)
        if text:
            latency_ms = (time.perf_counter() - start) * 1000
            if self.metrics:
                self.metrics.record_llm_latency(latency_ms)
            LOGGER.info("Using Bedrock primary model=%s", self.llm_model)
            return text, self.llm_model

        fallback_start = time.perf_counter()
        LOGGER.warning("Primary Bedrock model failed or returned unusable output; falling back from %s to %s", self.llm_model, self.fallback_llm_model)
        fallback_data = self._invoke_json(self.fallback_llm_model, payload)
        fallback_text = self._extract_text(fallback_data)
        fallback_latency_ms = (time.perf_counter() - fallback_start) * 1000
        if self.metrics:
            self.metrics.record_llm_latency(fallback_latency_ms)
        LOGGER.info("Using Bedrock fallback model=%s", self.fallback_llm_model)
        return fallback_text, self.fallback_llm_model

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        text, used_model = self._invoke_with_fallback(payload)
        LOGGER.info("LLM response model=%s chars=%s", used_model, len(text))
        return text

    def generate_multimodal_text(
        self,
        text_prompt: str,
        images_base64: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        content = [{"type": "text", "text": text_prompt}]
        for image in images_base64 or []:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image,
                    },
                }
            )

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": content}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        text, used_model = self._invoke_with_fallback(payload, multimodal=True)
        LOGGER.info("LLM multimodal response model=%s images=%s chars=%s", used_model, len(images_base64 or []), len(text))
        return text

    def stream_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> Iterator[str]:
        text = self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        chunk_size = 120
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]

    def rerank_texts(self, query: str, documents: List[str], top_n: int = 10) -> List[dict[str, Any]] | None:
        if not self.rerank_model_arn or not documents:
            return None
        try:
            response = self.agent_runtime_client.rerank(
                queries=[
                    {
                        "type": "TEXT",
                        "textQuery": {"text": query},
                    }
                ],
                rerankingConfiguration={
                    "type": "BEDROCK_RERANKING_MODEL",
                    "bedrockRerankingConfiguration": {
                        "modelConfiguration": {
                            "modelArn": self.rerank_model_arn,
                        },
                        "numberOfResults": top_n,
                    },
                },
                sources=[
                    {
                        "type": "INLINE",
                        "inlineDocumentSource": {
                            "type": "TEXT",
                            "textDocument": {"text": document},
                        },
                    }
                    for document in documents
                ],
            )
            results = response.get("results", [])
            normalized = [
                {
                    "index": item.get("index"),
                    "relevance_score": item.get("relevanceScore"),
                }
                for item in results
                if item.get("index") is not None and item.get("relevanceScore") is not None
            ]
            LOGGER.info("Bedrock rerank returned results=%s", len(normalized))
            return normalized
        except (BotoCoreError, ClientError, TimeoutError):
            LOGGER.exception("Bedrock rerank failed; falling back to heuristic reranking.")
            return None
