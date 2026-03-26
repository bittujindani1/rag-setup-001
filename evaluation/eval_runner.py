from __future__ import annotations

import json
import os
from pathlib import Path
from statistics import mean

import requests


ROOT_DIR = Path(__file__).resolve().parent
TEST_QUERY_PATH = ROOT_DIR / "test_queries.json"
BASE_URL = os.getenv("RAG_API_URL", "http://localhost:8000")
INDEX_NAME = os.getenv("RAG_EVAL_INDEX", "test")
SESSION_ID = os.getenv("RAG_EVAL_SESSION_ID", "eval-session")


def _load_cases() -> list[dict]:
    with TEST_QUERY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _run_query(question: str) -> dict:
    response = requests.post(
        f"{BASE_URL}/SFRAG/retrieval",
        json={
            "user_query": question,
            "index_name": INDEX_NAME,
            "session_id": SESSION_ID,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _recall_at_k(expected_docs: list[str], citations: list[dict]) -> float:
    cited_docs = {str(item.get("filename", "")).strip() for item in citations if item.get("filename")}
    if not expected_docs:
        return 1.0
    matched = sum(1 for document in expected_docs if document in cited_docs)
    return matched / len(expected_docs)


def _mrr(expected_docs: list[str], citations: list[dict]) -> float:
    cited_docs = [str(item.get("filename", "")).strip() for item in citations if item.get("filename")]
    for rank, document in enumerate(cited_docs, start=1):
        if document in expected_docs:
            return 1.0 / rank
    return 0.0


def main() -> None:
    cases = _load_cases()
    recall_scores: list[float] = []
    mrr_scores: list[float] = []

    for case in cases:
        payload = _run_query(case["query"])
        citations = payload.get("citation", [])
        recall = _recall_at_k(case.get("expected_documents", []), citations)
        reciprocal_rank = _mrr(case.get("expected_documents", []), citations)
        recall_scores.append(recall)
        mrr_scores.append(reciprocal_rank)
        print(
            json.dumps(
                {
                    "query": case["query"],
                    "recall_at_k": round(recall, 3),
                    "mrr": round(reciprocal_rank, 3),
                    "citations": [item.get("filename") for item in citations],
                },
                ensure_ascii=False,
            )
        )

    summary = {
        "cases": len(cases),
        "avg_recall_at_k": round(mean(recall_scores), 3) if recall_scores else 0.0,
        "avg_mrr": round(mean(mrr_scores), 3) if mrr_scores else 0.0,
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
