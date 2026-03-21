#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv_local/Scripts/python.exe}"
API_URL="${RAG_API_URL:-http://127.0.0.1:8000}"
DEMO_WORKSPACE="${DEMO_WORKSPACE:-demo-shared}"
SAMPLE_PDF="${SAMPLE_PDF:-$ROOT_DIR/tests/sample_docs/test_insurance.pdf}"
GENERATED_DIR="$ROOT_DIR/scripts/generated"
CSV_TICKETS="$GENERATED_DIR/servicenow_tickets.csv"
JSON_TICKETS="$GENERATED_DIR/servicenow_tickets.json"

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || {
    echo "Required file not found: $path" >&2
    exit 1
  }
}

load_env

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

echo "Using API: $API_URL"
echo "Using shared workspace: $DEMO_WORKSPACE"

echo "Generating synthetic ServiceNow tickets"
"$PYTHON_BIN" "$ROOT_DIR/scripts/generate_servicenow_tickets.py"

require_file "$SAMPLE_PDF"
require_file "$CSV_TICKETS"
require_file "$JSON_TICKETS"

echo "Checking API health"
curl --silent --fail "$API_URL/health" >/dev/null

echo "Uploading sample insurance PDF to $DEMO_WORKSPACE"
"$PYTHON_BIN" - <<PY
from pathlib import Path
import requests

api_url = r'''$API_URL'''
index_name = r'''$DEMO_WORKSPACE'''
pdf_path = Path(r'''$SAMPLE_PDF''')

with pdf_path.open('rb') as handle:
    response = requests.post(
        f"{api_url}/SFRAG/ingest",
        data={"index_name": index_name},
        files={"file": (pdf_path.name, handle, "application/pdf")},
        timeout=1800,
    )

print(response.status_code)
print(response.text)
response.raise_for_status()
PY

echo "Uploading synthetic tickets CSV to $DEMO_WORKSPACE"
"$PYTHON_BIN" - <<PY
from pathlib import Path
import requests

api_url = r'''$API_URL'''
index_name = r'''$DEMO_WORKSPACE'''
ticket_path = Path(r'''$CSV_TICKETS''')

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

echo "Demo workspace preload complete for $DEMO_WORKSPACE"
