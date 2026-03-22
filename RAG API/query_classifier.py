from __future__ import annotations

from typing import Any


ANALYTICS_HINTS = (
    "count",
    "top",
    "trend",
    "compare",
    "how many",
    "group by",
    "chart",
    "table",
    "breakdown",
    "distribution",
    "kpi",
    "average",
    "sum",
    "total",
)

KNOWLEDGE_HINTS = (
    "why",
    "how was",
    "explain",
    "resolution",
    "policy",
    "what does",
    "meaning",
    "procedure",
)


def classify_query_route(question: str, schema_profile: dict[str, Any] | None = None) -> dict[str, str]:
    lowered = (question or "").strip().lower()
    if any(term in lowered for term in ANALYTICS_HINTS):
        return {"route": "analytics", "reason": "deterministic_analytics_keyword"}
    if any(term in lowered for term in KNOWLEDGE_HINTS):
        return {"route": "knowledge", "reason": "deterministic_knowledge_keyword"}

    available_columns = {str(item.get("name", "")).lower() for item in (schema_profile or {}).get("columns", [])}
    if any(column and column in lowered for column in available_columns):
        return {"route": "analytics", "reason": "schema_column_reference"}

    return {"route": "analytics", "reason": "default_analytics_for_structured_dataset"}
