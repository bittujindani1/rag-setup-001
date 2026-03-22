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
    "highest",
    "lowest",
    "most",
    "least",
)

KNOWLEDGE_HINTS = (
    "why",
    "how was",
    "explain",
    "explanation",
    "explain the",
    "summarize",
    "summarise",
    "summary",
    "summarized",
    "summarised",
    "resolution",
    "policy",
    "what does",
    "meaning",
    "procedure",
    "root cause",
    "what is driving",
    "what drives",
)


def classify_query_route(question: str, schema_profile: dict[str, Any] | None = None) -> dict[str, str]:
    lowered = (question or "").strip().lower()
    has_analytics_hint = any(term in lowered for term in ANALYTICS_HINTS)
    has_knowledge_hint = any(term in lowered for term in KNOWLEDGE_HINTS)

    if has_analytics_hint and has_knowledge_hint:
        return {"route": "hybrid", "reason": "deterministic_hybrid_keyword"}
    if has_analytics_hint:
        return {"route": "analytics", "reason": "deterministic_analytics_keyword"}
    if has_knowledge_hint:
        return {"route": "knowledge", "reason": "deterministic_knowledge_keyword"}

    available_columns = {str(item.get("name", "")).lower() for item in (schema_profile or {}).get("columns", [])}
    if any(column and column in lowered for column in available_columns):
        return {"route": "analytics", "reason": "schema_column_reference"}

    return {"route": "analytics", "reason": "default_analytics_for_structured_dataset"}
