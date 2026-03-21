#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv_local/Scripts/python}"
FASTAPI_HOST="${FASTAPI_HOST:-127.0.0.1}"
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
API_URL="http://${FASTAPI_HOST}:${FASTAPI_PORT}"
TEST_INDEX_NAME="${TEST_INDEX_NAME:-fresh-e2e-$(date +%s)}"
TEST_QUERY="${TEST_QUERY:-What does this document describe?}"
TEST_PDF_PATH="${TEST_PDF_PATH:-$ROOT_DIR/tests/sample_docs/test_insurance.pdf}"

HEALTH_STATUS=1
INGEST_STATUS=1
QUERY_STATUS=1

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

print_summary() {
  local overall="FAIL"
  if [[ "$HEALTH_STATUS" -eq 0 && "$INGEST_STATUS" -eq 0 && "$QUERY_STATUS" -eq 0 ]]; then
    overall="PASS"
  fi

  echo
  echo "End-to-End Summary"
  echo "Index: $TEST_INDEX_NAME"
  echo "PDF: $TEST_PDF_PATH"
  echo "API /health: $([[ "$HEALTH_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Ingest: $([[ "$INGEST_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Query: $([[ "$QUERY_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Overall: $overall"

  [[ "$overall" == "PASS" ]]
}

load_env
export DEBUG=false
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN"
  exit 1
fi

if [[ ! -f "$TEST_PDF_PATH" ]]; then
  echo "PDF not found: $TEST_PDF_PATH"
  echo "Set TEST_PDF_PATH to a full path for a new PDF."
  exit 1
fi

echo "Checking API health"
if curl --silent --fail "$API_URL/health" >/dev/null 2>&1; then
  HEALTH_STATUS=0
else
  echo "API health check failed at $API_URL/health"
  print_summary
  exit 1
fi

echo "Running ingest on index: $TEST_INDEX_NAME"
if "$PYTHON_BIN" - <<PY
from pathlib import Path
import requests

pdf_path = Path(r'''${TEST_PDF_PATH}''')
index_name = r'''${TEST_INDEX_NAME}'''
resp = None
with pdf_path.open('rb') as handle:
    resp = requests.post(
        '${API_URL}/SFRAG/ingest',
        data={'index_name': index_name},
        files={'file': (pdf_path.name, handle, 'application/pdf')},
        timeout=1800,
    )
print(resp.status_code)
print(resp.text)
resp.raise_for_status()
payload = resp.json()
assert payload.get('status') == 'Index ingested successfully'
PY
then
  INGEST_STATUS=0
else
  print_summary
  exit 1
fi

echo "Running retrieval query"
if "$PYTHON_BIN" - <<PY
import requests

resp = requests.post(
    '${API_URL}/SFRAG/retrieval',
    json={
        'user_query': r'''${TEST_QUERY}''',
        'index_name': r'''${TEST_INDEX_NAME}''',
        'session_id': 'e2e-job-session',
    },
    timeout=300,
)
print(resp.status_code)
print(resp.text)
resp.raise_for_status()
payload = resp.json()
assert isinstance(payload.get('response', {}).get('content'), str)
assert isinstance(payload.get('citation'), list)
PY
then
  QUERY_STATUS=0
else
  print_summary
  exit 1
fi

if print_summary; then
  exit 0
fi

exit 1
