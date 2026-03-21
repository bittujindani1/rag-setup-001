#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv_local/Scripts/python}"

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

load_env
export DEBUG=false
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN"
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


root = Path.cwd()
env_values = load_env_file(root / ".env")
region = os.getenv("AWS_REGION") or env_values.get("AWS_REGION", "ap-south-1")

s3_buckets = [
    os.getenv("S3_BUCKET_DOCUMENTS") or env_values.get("S3_BUCKET_DOCUMENTS"),
    os.getenv("S3_BUCKET_VECTORS") or env_values.get("S3_BUCKET_VECTORS"),
    os.getenv("S3_BUCKET_EXTRACTED") or env_values.get("S3_BUCKET_EXTRACTED"),
]

ddb_tables = [
    os.getenv("DYNAMODB_CHAT_HISTORY_TABLE") or env_values.get("DYNAMODB_CHAT_HISTORY_TABLE"),
    os.getenv("DYNAMODB_QUERY_CACHE_TABLE") or env_values.get("DYNAMODB_QUERY_CACHE_TABLE"),
    os.getenv("DYNAMODB_DOC_STORE_TABLE") or env_values.get("DYNAMODB_DOC_STORE_TABLE"),
    os.getenv("DYNAMODB_FILENAME_INDEX_TABLE") or env_values.get("DYNAMODB_FILENAME_INDEX_TABLE"),
    os.getenv("DYNAMODB_RATE_LIMIT_TABLE") or env_values.get("DYNAMODB_RATE_LIMIT_TABLE"),
    os.getenv("DYNAMODB_THREAD_TABLE") or env_values.get("DYNAMODB_THREAD_TABLE"),
]

session = boto3.Session(region_name=region)
s3 = session.client("s3")
ddb = session.client("dynamodb")
bedrock = session.client("bedrock", region_name=region)

result = {
    "region": region,
    "s3": [],
    "dynamodb": [],
    "bedrock": {},
    "textract": {
        "persistent_resources": "none",
        "billing_model": "per_api_call",
    },
}

for bucket in filter(None, s3_buckets):
    entry = {"bucket": bucket}
    try:
        location = s3.get_bucket_location(Bucket=bucket)
        entry["region"] = location.get("LocationConstraint") or "us-east-1"
        versioning = s3.get_bucket_versioning(Bucket=bucket)
        entry["versioning"] = versioning.get("Status", "Disabled")

        total_size = 0
        object_count = 0
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                object_count += 1
                total_size += obj.get("Size", 0)

        entry["object_count"] = object_count
        entry["total_size_bytes"] = total_size
        entry["total_size_mb"] = round(total_size / (1024 * 1024), 4)
        entry["billed_while_idle"] = "yes" if total_size > 0 else "possibly_no"

        try:
            lifecycle = s3.get_bucket_lifecycle_configuration(Bucket=bucket)
            entry["lifecycle_rules"] = len(lifecycle.get("Rules", []))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            entry["lifecycle_rules"] = 0 if code == "NoSuchLifecycleConfiguration" else f"error:{code}"
    except ClientError as exc:
        entry["error"] = exc.response.get("Error", {}).get("Code")
    result["s3"].append(entry)

for table in filter(None, ddb_tables):
    entry = {"table": table}
    try:
        description = ddb.describe_table(TableName=table)["Table"]
        billing_mode = description.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")
        entry["status"] = description.get("TableStatus")
        entry["billing_mode"] = billing_mode
        entry["item_count"] = description.get("ItemCount")
        entry["table_size_bytes"] = description.get("TableSizeBytes")
        entry["table_size_mb"] = round((description.get("TableSizeBytes") or 0) / (1024 * 1024), 4)
        entry["gsi_names"] = [gsi["IndexName"] for gsi in description.get("GlobalSecondaryIndexes", [])]
        entry["billed_while_idle"] = "storage_only" if billing_mode == "PAY_PER_REQUEST" else "yes"

        continuous_backups = ddb.describe_continuous_backups(TableName=table)["ContinuousBackupsDescription"]
        entry["pitr_status"] = continuous_backups.get("PointInTimeRecoveryDescription", {}).get(
            "PointInTimeRecoveryStatus",
            "DISABLED",
        )
        ttl = ddb.describe_time_to_live(TableName=table)["TimeToLiveDescription"]
        entry["ttl_status"] = ttl.get("TimeToLiveStatus", "DISABLED")
        entry["ttl_attribute"] = ttl.get("AttributeName")
    except ClientError as exc:
        entry["error"] = exc.response.get("Error", {}).get("Code")
    result["dynamodb"].append(entry)

try:
    provisioned = bedrock.list_provisioned_model_throughputs(maxResults=100)
    summaries = provisioned.get("provisionedModelSummaries", [])
    result["bedrock"]["provisioned_model_throughput_count"] = len(summaries)
    result["bedrock"]["billed_while_idle"] = "yes" if summaries else "no"
    result["bedrock"]["provisioned_models"] = [
        {
            "name": item.get("provisionedModelName"),
            "model_id": item.get("modelId"),
            "status": item.get("status"),
        }
        for item in summaries
    ]
except ClientError as exc:
    result["bedrock"]["error"] = exc.response.get("Error", {}).get("Code")

print(json.dumps(result, indent=2))
PY
