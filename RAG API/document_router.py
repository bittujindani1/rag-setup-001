from __future__ import annotations

from collections import Counter
from typing import Iterable


def build_disambiguation_payload(
    *,
    query: str,
    categories: list[dict],
    documents: Iterable[dict],
    selected_category: str | None,
    document_filter: str | None,
) -> dict | None:
    if selected_category or document_filter:
        return None

    document_list = list(documents)
    category_names = [item.get("category") for item in categories if item.get("category")]
    if len(category_names) < 2:
        return None

    lowered_query = (query or "").lower()
    explicit_compare = any(term in lowered_query for term in ("compare", "difference", "all categories", "across"))
    if explicit_compare:
        return None

    filename_counts = Counter(item.get("filename") for item in document_list if item.get("filename"))
    return {
        "mode": "clarify",
        "response": {
            "content": "I found multiple document categories for this question. Which category should I use?"
        },
        "citation": [],
        "categories": categories,
        "documents": [
            {"filename": filename, "count": count}
            for filename, count in filename_counts.most_common(5)
        ],
    }
