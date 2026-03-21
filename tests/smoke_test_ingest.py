import os
import sys
from pathlib import Path

import requests


BASE_URL = os.getenv("RAG_API_URL", "http://localhost:8000")
INDEX_NAME = os.getenv("TEST_INDEX_NAME", "smoke-test-index")
TEST_PDF_PATH = os.getenv("TEST_PDF_PATH", "")


def get_test_pdf() -> Path:
    if TEST_PDF_PATH:
        pdf_path = Path(TEST_PDF_PATH)
        if not pdf_path.exists():
            raise FileNotFoundError(f"TEST_PDF_PATH not found: {pdf_path}")
        return pdf_path

    bundled = Path(__file__).resolve().parent / "sample_docs" / "test_insurance.pdf"
    if not bundled.exists():
        raise FileNotFoundError(f"Bundled sample PDF not found: {bundled}")
    return bundled


def main() -> int:
    try:
        health_response = requests.get(f"{BASE_URL}/health", timeout=30)
        health_response.raise_for_status()
        assert health_response.json() == {"status": "ok"}, health_response.text

        pdf_path = get_test_pdf()
        with pdf_path.open("rb") as handle:
            response = requests.post(
                f"{BASE_URL}/SFRAG/ingest",
                data={"index_name": INDEX_NAME},
                files={"file": (pdf_path.name, handle, "application/pdf")},
                timeout=180,
            )

        response.raise_for_status()
        payload = response.json()
        assert payload.get("status") == "Index ingested successfully", payload
        assert payload.get("index_name") == INDEX_NAME, payload
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
        print("Ingest smoke test passed")
        print(payload)
        return 0
    except Exception as exc:
        print(f"Ingest smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
