from __future__ import annotations

import re


BLOCKED_TOKENS = ("drop ", "delete ", "insert ", "update ", "alter ", "truncate ", "grant ", "revoke ")


def validate_sql(sql: str, *, allowed_tables: set[str], max_limit: int = 1000) -> str:
    normalized = (sql or "").strip().rstrip(";")
    lowered = normalized.lower()
    if not lowered.startswith("select"):
        raise ValueError("Only SELECT statements are allowed.")
    if any(token in lowered for token in BLOCKED_TOKENS):
        raise ValueError("Mutating SQL statements are not allowed.")
    if not any(table.lower() in lowered for table in allowed_tables):
        raise ValueError("SQL must reference an allowed analytics table.")

    limit_match = re.search(r"\blimit\s+(\d+)\b", lowered)
    if limit_match and int(limit_match.group(1)) > max_limit:
        raise ValueError(f"LIMIT cannot exceed {max_limit}.")

    if "select *" in lowered and " where " not in lowered:
        raise ValueError("Unbounded SELECT * queries are not allowed.")

    return normalized
