#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv_local/Scripts/python}"
FASTAPI_HOST="${FASTAPI_HOST:-127.0.0.1}"
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
CHAINLIT_HOST="${CHAINLIT_HOST:-127.0.0.1}"
CHAINLIT_PORT="${CHAINLIT_PORT:-5101}"
API_URL="http://${FASTAPI_HOST}:${FASTAPI_PORT}"
CHAINLIT_URL="http://${CHAINLIT_HOST}:${CHAINLIT_PORT}"
TEST_INDEX_NAME="${TEST_INDEX_NAME:-smoke-test-index}"
TEST_QUERY="${TEST_QUERY:-What does this document describe?}"
TEST_PDF_PATH="${TEST_PDF_PATH:-$ROOT_DIR/tests/sample_docs/test_insurance.pdf}"

HEALTH_STATUS=1
METRICS_STATUS=1
UI_STATUS=1
AWS_STATUS=1
RETRIEVAL_STATUS=1
EXTRACTOR_STATUS=1

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

run_python_check() {
  local label="$1"
  local code="$2"

  echo "Running ${label}"
  if "$PYTHON_BIN" - <<PY
$code
PY
  then
    return 0
  fi
  return 1
}

print_summary() {
  local overall="FAIL"
  if [[ "$HEALTH_STATUS" -eq 0 && "$METRICS_STATUS" -eq 0 && "$UI_STATUS" -eq 0 && "$AWS_STATUS" -eq 0 && "$RETRIEVAL_STATUS" -eq 0 && "$EXTRACTOR_STATUS" -eq 0 ]]; then
    overall="PASS"
  fi

  echo
  echo "Support Check Summary"
  echo "API /health: $([[ "$HEALTH_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "API /metrics: $([[ "$METRICS_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Chainlit /login: $([[ "$UI_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "AWS preflight: $([[ "$AWS_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Retrieval-only check: $([[ "$RETRIEVAL_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Extractor-only check: $([[ "$EXTRACTOR_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Overall: $overall"
  echo
  echo "Useful logs:"
  echo "  $ROOT_DIR/.api_start_check.log"
  echo "  $ROOT_DIR/.venv_local_ui.log"
  echo "  $ROOT_DIR/.startup_recheck.log"

  [[ "$overall" == "PASS" ]]
}

load_env
export DEBUG=false
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN"
  exit 1
fi

echo "Checking API health"
if curl --silent --fail "${API_URL}/health" >/dev/null 2>&1; then
  HEALTH_STATUS=0
else
  echo "API health check failed at ${API_URL}/health"
fi

echo "Checking API metrics"
if curl --silent --fail "${API_URL}/metrics" >/dev/null 2>&1; then
  METRICS_STATUS=0
else
  echo "API metrics check failed at ${API_URL}/metrics"
fi

echo "Checking Chainlit UI"
if curl --silent --fail "${CHAINLIT_URL}/login" >/dev/null 2>&1; then
  UI_STATUS=0
else
  echo "Chainlit login check failed at ${CHAINLIT_URL}/login"
fi

echo "Running AWS preflight checks"
if bash "$ROOT_DIR/scripts/important/run_aws_service_validation.sh"; then
  AWS_STATUS=0
fi

run_python_check "retrieval-only check" "
import requests
resp = requests.post(
    '${API_URL}/SFRAG/retrieval',
    json={'user_query': '${TEST_QUERY}', 'index_name': '${TEST_INDEX_NAME}', 'session_id': 'support-check-session'},
    timeout=180,
)
print('STATUS', resp.status_code)
print(resp.text)
resp.raise_for_status()
payload = resp.json()
assert isinstance(payload.get('response', {}).get('content'), str)
assert isinstance(payload.get('citation'), list)
" && RETRIEVAL_STATUS=0

run_python_check "extractor-only check" "
import tempfile
from pathlib import Path
from aws.document_extractor import AWSDocumentExtractor

pdf_path = Path(r'''${TEST_PDF_PATH}''')
extractor = AWSDocumentExtractor()
pages = extractor.extract_document(str(pdf_path), pdf_path.name)
print('PAGE_COUNT', len(pages))
assert pages and isinstance(pages[0].get('page_number'), int)
" && EXTRACTOR_STATUS=0

if print_summary; then
  exit 0
fi

exit 1
