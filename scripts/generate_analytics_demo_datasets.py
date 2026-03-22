from __future__ import annotations

import csv
from pathlib import Path


def build_aws_service_costs() -> list[dict[str, object]]:
    services = [
        ("Amazon EC2", "platform", "prod", "compute", 1280.0, "rightsizing"),
        ("Amazon RDS", "data", "prod", "database", 940.0, "reserved instance"),
        ("Amazon S3", "platform", "shared", "storage", 315.0, "lifecycle cleanup"),
        ("AWS Lambda", "digital", "prod", "serverless", 190.0, "memory tuning"),
        ("Amazon CloudWatch", "platform", "shared", "observability", 145.0, "log retention"),
        ("Amazon Bedrock", "ai-coe", "innovation", "genai", 610.0, "prompt routing"),
        ("Amazon DynamoDB", "claims", "prod", "database", 275.0, "on-demand review"),
        ("Amazon Athena", "ai-coe", "shared", "analytics", 96.0, "partition pruning"),
        ("AWS Glue", "ai-coe", "shared", "analytics", 88.0, "job consolidation"),
        ("Elastic Load Balancing", "platform", "prod", "network", 204.0, "listener cleanup"),
        ("Amazon VPC", "platform", "shared", "network", 154.0, "nat gateway review"),
        ("Amazon ECR", "platform", "shared", "containers", 42.0, "image retention"),
    ]

    rows: list[dict[str, object]] = []
    month_offsets = [0.96, 1.0, 1.07]
    months = ["2026-01", "2026-02", "2026-03"]
    for month, factor in zip(months, month_offsets):
        for service_name, owner_team, environment, cost_category, monthly_cost, optimization_hint in services:
            rows.append(
                {
                    "month": month,
                    "service_name": service_name,
                    "owner_team": owner_team,
                    "environment": environment,
                    "cost_category": cost_category,
                    "monthly_cost_usd": round(monthly_cost * factor, 2),
                    "optimization_hint": optimization_hint,
                }
            )
    return rows


def build_claims_operational_kpis() -> list[dict[str, object]]:
    regions = [
        ("north", 18, 7.1, 42, 4.6, "stable"),
        ("south", 24, 8.4, 38, 4.3, "elevated"),
        ("east", 16, 6.8, 29, 4.7, "stable"),
        ("west", 27, 9.2, 41, 4.1, "high"),
    ]
    weeks = ["2026-W09", "2026-W10", "2026-W11", "2026-W12"]
    rows: list[dict[str, object]] = []
    for week_index, week in enumerate(weeks):
        for region, open_claims, avg_cycle_days, adjuster_count, csat_score, backlog_band in regions:
            rows.append(
                {
                    "week": week,
                    "region": region,
                    "open_claims": open_claims + (week_index * 2),
                    "avg_cycle_days": round(avg_cycle_days + (week_index * 0.2), 1),
                    "adjuster_count": adjuster_count,
                    "csat_score": round(csat_score - (week_index * 0.05), 2),
                    "backlog_band": backlog_band if week_index < 2 else ("high" if region in {"south", "west"} else "stable"),
                    "manager_note": f"{region.title()} region focused on reducing reopened claims and balancing adjuster loads.",
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    output_dir = Path(__file__).resolve().parent / "generated"
    aws_cost_path = output_dir / "aws_service_costs.csv"
    claims_path = output_dir / "claims_operational_kpis.csv"

    write_csv(aws_cost_path, build_aws_service_costs())
    write_csv(claims_path, build_claims_operational_kpis())

    print(aws_cost_path)
    print(claims_path)


if __name__ == "__main__":
    main()
