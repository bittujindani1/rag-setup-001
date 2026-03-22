from __future__ import annotations

import re
from typing import Any


def _quoted(column: str) -> str:
    return f'"{column}"'


def _extract_filters(question: str, *, dataset_id: str, schema_profile: dict[str, Any]) -> list[str]:
    lowered = (question or "").strip().lower()
    filters = [f"dataset_id = '{dataset_id}'"]
    columns = {str(item.get("name", "")).lower(): item for item in schema_profile.get("columns", [])}

    for column_name, column in columns.items():
        if column.get("kind") == "categorical" and column_name in lowered:
            filters.append(f"{_quoted(column_name)} = '{column_name}'")
        for value in column.get("sample_values", [])[:20]:
            normalized_value = str(value).strip().lower()
            if normalized_value and normalized_value in lowered:
                escaped_value = str(value).replace("'", "''")
                filters.append(f"{_quoted(column_name)} = '{escaped_value}'")

    return list(dict.fromkeys(filters))


def _context_columns(schema_profile: dict[str, Any]) -> list[str]:
    available = [str(item.get("name", "")) for item in schema_profile.get("columns", [])]
    preferred = [
        "summary",
        "issue",
        "resolution",
        "category",
        "priority",
        "status",
        "assignment_group",
        "source",
        "service_name",
        "owner_team",
        "environment",
        "optimization_hint",
        "region",
        "metric_name",
        "description",
        "ticket_id",
    ]
    selected = [column for column in preferred if column in available]
    if selected:
        return selected[:6]
    return available[:6]


def build_context_sql(
    question: str,
    *,
    dataset_id: str,
    table_name: str,
    schema_profile: dict[str, Any],
    primary_sql: str,
    primary_result: dict[str, Any],
) -> str:
    filters = _extract_filters(question, dataset_id=dataset_id, schema_profile=schema_profile)

    group_match = re.search(r'SELECT\s+"([^"]+)"\s+AS\s+label', primary_sql, re.IGNORECASE)
    top_label = None
    if primary_result.get("rows"):
        top_label = primary_result["rows"][0].get("label")
    if group_match and top_label is not None:
        group_column = group_match.group(1)
        escaped_label = str(top_label).replace("'", "''")
        filters.append(f'{_quoted(group_column)} = \'{escaped_label}\'')

    columns = ", ".join(_quoted(column) for column in _context_columns(schema_profile))
    where_clause = " AND ".join(dict.fromkeys(filters))
    return f'SELECT {columns} FROM "{table_name}" WHERE {where_clause} LIMIT 5'


def generate_sql_for_question(question: str, *, dataset_id: str, table_name: str, schema_profile: dict[str, Any]) -> tuple[str, str]:
    lowered = (question or "").strip().lower()
    columns = {str(item.get("name", "")).lower(): item for item in schema_profile.get("columns", [])}

    if "how many" in lowered or ("count" in lowered and "by" not in lowered):
        filters = _extract_filters(question, dataset_id=dataset_id, schema_profile=schema_profile)
        where_clause = " AND ".join(dict.fromkeys(filters))
        return (
            f'SELECT COUNT(*) AS total_rows FROM "{table_name}" WHERE {where_clause}',
            "number",
        )

    for column_name, column in columns.items():
        if column.get("kind") == "categorical" and (
            f"by {column_name}" in lowered
            or column_name in lowered
            or column_name.replace("_", " ") in lowered
        ):
            sql = (
                f'SELECT "{column_name}" AS label, COUNT(*) AS value '
                f'FROM "{table_name}" WHERE dataset_id = \'{dataset_id}\' '
                f'GROUP BY 1 ORDER BY 2 DESC LIMIT 25'
            )
            return sql, "bar"

    datetime_columns = [item["name"] for item in schema_profile.get("columns", []) if item.get("kind") == "datetime"]
    if datetime_columns and any(term in lowered for term in ("trend", "daily", "over time")):
        column_name = datetime_columns[0]
        sql = (
            f'SELECT date_trunc(\'day\', CAST("{column_name}" AS timestamp)) AS period, COUNT(*) AS value '
            f'FROM "{table_name}" WHERE dataset_id = \'{dataset_id}\' '
            f'GROUP BY 1 ORDER BY 1 ASC LIMIT 180'
        )
        return sql, "line"

    return (
        f'SELECT * FROM "{table_name}" WHERE dataset_id = \'{dataset_id}\' LIMIT 25',
        "table",
    )
