from __future__ import annotations

from typing import Any


def _quoted(column: str) -> str:
    return f'"{column}"'


def generate_sql_for_question(question: str, *, dataset_id: str, table_name: str, schema_profile: dict[str, Any]) -> tuple[str, str]:
    lowered = (question or "").strip().lower()
    columns = {str(item.get("name", "")).lower(): item for item in schema_profile.get("columns", [])}

    if "how many" in lowered or ("count" in lowered and "by" not in lowered):
        filters = [f"dataset_id = '{dataset_id}'"]
        for column_name, column in columns.items():
            if column.get("kind") == "categorical" and column_name in lowered:
                filters.append(f"{_quoted(column_name)} = '{column_name}'")
            for value in column.get("sample_values", [])[:10]:
                normalized_value = str(value).strip().lower()
                if normalized_value and normalized_value in lowered:
                    escaped_value = str(value).replace("'", "''")
                    filters.append(f"{_quoted(column_name)} = '{escaped_value}'")
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
