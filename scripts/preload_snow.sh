#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv_local/Scripts/python.exe}"
API_URL="${RAG_API_URL:-http://127.0.0.1:8000}"
SNOW_WORKSPACE="${SNOW_WORKSPACE:-snow_idx}"
GENERATED_DIR="$ROOT_DIR/scripts/generated"
CSV_TICKETS="$GENERATED_DIR/servicenow_tickets.csv"
CSV_TICKETS_WIN="$(cygpath -w "$CSV_TICKETS" 2>/dev/null || echo "$CSV_TICKETS")"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

echo "Using API: $API_URL"
echo "Using ServiceNow workspace: $SNOW_WORKSPACE"

echo "Generating synthetic ServiceNow tickets"
"$PYTHON_BIN" "$ROOT_DIR/scripts/generate_servicenow_tickets.py"

if [[ ! -f "$CSV_TICKETS" ]]; then
  echo "Generated CSV not found: $CSV_TICKETS" >&2
  exit 1
fi

echo "Checking API health"
curl --silent --fail "$API_URL/health" >/dev/null

echo "Uploading synthetic tickets CSV to $SNOW_WORKSPACE"
"$PYTHON_BIN" - <<PY
from pathlib import Path
import requests

api_url = r'''$API_URL'''
index_name = r'''$SNOW_WORKSPACE'''
ticket_path = Path(r'''$CSV_TICKETS''')
ticket_path = Path(r'''$CSV_TICKETS_WIN''')

with ticket_path.open('rb') as handle:
    response = requests.post(
        f"{api_url}/SFRAG/ingest-tickets",
        data={"index_name": index_name},
        files={"file": (ticket_path.name, handle, "text/csv")},
        timeout=1800,
    )

print(response.status_code)
print(response.text)
response.raise_for_status()
PY

echo "ServiceNow preload complete for $SNOW_WORKSPACE"
