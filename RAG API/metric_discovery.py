from __future__ import annotations

from typing import Any, Dict, List


def discover_metrics(dataset_id: str, schema_profile: dict[str, Any], table_name: str) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = [
        {
            "metric_id": "row_count",
            "title": "Total rows",
            "description": "Total records in the dataset.",
            "type": "kpi",
            "chart_type": "number",
            "sql": f'SELECT COUNT(*) AS total_rows FROM "{table_name}" WHERE dataset_id = \'{dataset_id}\'',
        }
    ]

    columns: List[Dict[str, Any]] = schema_profile.get("columns", [])
    for column in columns:
        name = column.get("name")
        kind = column.get("kind")
        if not name or name == "dataset_id":
            continue

        if kind == "categorical":
            metrics.append(
                {
                    "metric_id": f"by_{name}",
                    "title": f"By {name.replace('_', ' ').title()}",
                    "description": f"Breakdown of records by {name}.",
                    "type": "breakdown",
                    "chart_type": "bar",
                    "sql": (
                        f'SELECT "{name}" AS label, COUNT(*) AS value '
                        f'FROM "{table_name}" WHERE dataset_id = \'{dataset_id}\' '
                        f'GROUP BY 1 ORDER BY 2 DESC LIMIT 25'
                    ),
                }
            )

        elif kind == "numeric":
            metrics.append(
                {
                    "metric_id": f"stats_{name}",
                    "title": f"{name.replace('_', ' ').title()} stats",
                    "description": f"Minimum, average, and maximum for {name}.",
                    "type": "summary",
                    "chart_type": "table",
                    "sql": (
                        f'SELECT MIN("{name}") AS min_value, AVG("{name}") AS avg_value, MAX("{name}") AS max_value '
                        f'FROM "{table_name}" WHERE dataset_id = \'{dataset_id}\''
                    ),
                }
            )

        elif kind == "datetime":
            metrics.append(
                {
                    "metric_id": f"trend_{name}",
                    "title": f"Trend by {name.replace('_', ' ').title()}",
                    "description": f"Daily trend based on {name}.",
                    "type": "trend",
                    "chart_type": "line",
                    "sql": (
                        f'SELECT date_trunc(\'day\', CAST("{name}" AS timestamp)) AS period, COUNT(*) AS value '
                        f'FROM "{table_name}" WHERE dataset_id = \'{dataset_id}\' '
                        f'GROUP BY 1 ORDER BY 1 ASC LIMIT 180'
                    ),
                }
            )

    return metrics
