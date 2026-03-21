#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RAG_API_DIR="$ROOT_DIR/RAG API"
ENV_FILE="$ROOT_DIR/.env"
FASTAPI_HOST="${FASTAPI_HOST:-127.0.0.1}"
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
HEALTH_URL="http://${FASTAPI_HOST}:${FASTAPI_PORT}/health"
PYTHON_BIN="${PYTHON_BIN:-python}"

API_PID=""
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

cleanup() {
  if [[ -n "$API_PID" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" 2>/dev/null || true
  fi
}

print_summary() {
  local overall="FAIL"
  if [[ "$INGEST_STATUS" -eq 0 && "$QUERY_STATUS" -eq 0 ]]; then
    overall="PASS"
  fi

  echo
  echo "Validation Summary"
  echo "API startup: PASS"
  echo "Ingest test: $([[ "$INGEST_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Query test: $([[ "$QUERY_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Overall: $overall"

  [[ "$overall" == "PASS" ]]
}

trap cleanup EXIT

load_env

export RAG_API_URL="${RAG_API_URL:-http://${FASTAPI_HOST}:${FASTAPI_PORT}}"
export TEST_PDF_PATH="${TEST_PDF_PATH:-$ROOT_DIR/tests/sample_docs/test_insurance.pdf}"
export DEBUG=false

echo "Starting FastAPI server on ${FASTAPI_HOST}:${FASTAPI_PORT}"
cd "$RAG_API_DIR" || exit 1
"$PYTHON_BIN" -m uvicorn main:app --host "$FASTAPI_HOST" --port "$FASTAPI_PORT" >"$ROOT_DIR/.local_validation_api.log" 2>&1 &
API_PID=$!

READY=0
for _ in $(seq 1 60); do
  if curl --silent --fail "$HEALTH_URL" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [[ "$READY" -ne 1 ]]; then
  echo "FastAPI server did not become healthy"
  echo "See .local_validation_api.log for details"
  echo
  echo "Validation Summary"
  echo "API startup: FAIL"
  echo "Ingest test: SKIPPED"
  echo "Query test: SKIPPED"
  echo "Overall: FAIL"
  exit 1
fi

echo "Running ingest smoke test"
cd "$ROOT_DIR" || exit 1
"$PYTHON_BIN" tests/smoke_test_ingest.py
INGEST_STATUS=$?

echo "Running query smoke test"
"$PYTHON_BIN" tests/smoke_test_query.py
QUERY_STATUS=$?

if print_summary; then
  exit 0
fi

exit 1
