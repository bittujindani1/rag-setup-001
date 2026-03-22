#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_URL="${API_URL:-https://gj67rokz4s7k42mrvbo6xxtl2a0scxia.lambda-url.ap-south-1.on.aws}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv_local/Scripts/python.exe}"

"$PYTHON_BIN" "$ROOT_DIR/scripts/generate_analytics_demo_datasets.py"

export API_URL
"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path
import requests

root = Path(r"c:\Users\dhairya.jindani\Documents\AI-coe projects\Rag")
api_url = os.environ["API_URL"]
datasets = [
    ("snow_analytics_demo", root / "scripts" / "generated" / "servicenow_tickets.csv", "text/csv"),
    ("aws_cost_analytics", root / "scripts" / "generated" / "aws_service_costs.csv", "text/csv"),
    ("claims_kpi_demo", root / "scripts" / "generated" / "claims_operational_kpis.csv", "text/csv"),
]

for dataset_id, file_path, content_type in datasets:
    with file_path.open("rb") as handle:
        response = requests.post(
            f"{api_url}/SFRAG/analytics/upload",
            data={"dataset_id": dataset_id},
            files={"file": (file_path.name, handle, content_type)},
            timeout=300,
        )
    print(dataset_id, response.status_code)
    print(response.text[:500])
PY
