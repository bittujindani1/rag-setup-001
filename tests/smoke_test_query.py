import os
import sys

import requests


BASE_URL = os.getenv("RAG_API_URL", "http://localhost:8000")
INDEX_NAME = os.getenv("TEST_INDEX_NAME", "smoke-test-index")
TEST_QUERY = os.getenv("TEST_QUERY", "What does this document describe?")
RATE_LIMIT_SESSION_ID = "smoke-test-rate-limit"


def main() -> int:
    try:
        health_response = requests.get(f"{BASE_URL}/health", timeout=30)
        health_response.raise_for_status()
        assert health_response.json() == {"status": "ok"}, health_response.text

        response = requests.post(
            f"{BASE_URL}/SFRAG/retrieval",
            json={
                "user_query": TEST_QUERY,
                "index_name": INDEX_NAME,
                "session_id": "smoke-test-session",
            },
            timeout=180,
        )
        response.raise_for_status()
        payload = response.json()

        assert isinstance(payload, dict), payload
        assert "response" in payload and isinstance(payload["response"], dict), payload
        assert "content" in payload["response"], payload
        assert isinstance(payload["response"]["content"], str), payload
        assert "citation" in payload and isinstance(payload["citation"], list), payload

        for citation in payload["citation"]:
            assert isinstance(citation, dict), payload
            assert "filename" in citation, citation
            assert "page_numbers" in citation, citation
            assert "url" in citation, citation
            assert "pdf_url" in citation, citation

        metrics_response = requests.get(f"{BASE_URL}/metrics", timeout=30)
        metrics_response.raise_for_status()
        metrics_payload = metrics_response.json()
        for key in (
            "cache_hit_rate",
            "avg_embedding_latency_ms",
            "avg_vector_search_latency_ms",
            "avg_llm_latency_ms",
            "documents_indexed",
        ):
            assert key in metrics_payload, metrics_payload

        rate_limit_status = None
        for _ in range(16):
            rate_response = requests.post(
                f"{BASE_URL}/SFRAG/retrieval",
                json={
                    "user_query": TEST_QUERY,
                    "index_name": INDEX_NAME,
                    "session_id": RATE_LIMIT_SESSION_ID,
                },
                timeout=180,
            )
            rate_limit_status = rate_response.status_code
            if rate_limit_status == 429:
                break
        assert rate_limit_status == 429, f"Expected 429 after repeated requests, got {rate_limit_status}"

        print("Query smoke test passed")
        print(payload)
        return 0
    except Exception as exc:
        print(f"Query smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
