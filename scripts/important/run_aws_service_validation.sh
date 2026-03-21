#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
RAG_API_ENV_FILE="$ROOT_DIR/RAG API/.env"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv_local/Scripts/python}"

S3_STATUS=1
DDB_STATUS=1
BEDROCK_STATUS=1
VECTOR_STATUS=1

load_env() {
  local existing_access_key="${AWS_ACCESS_KEY_ID:-}"
  local existing_secret_key="${AWS_SECRET_ACCESS_KEY:-}"
  local existing_session_token="${AWS_SESSION_TOKEN:-}"
  local existing_region="${AWS_REGION:-}"

  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
  if [[ -n "$existing_access_key" ]]; then
    export AWS_ACCESS_KEY_ID="$existing_access_key"
  fi
  if [[ -n "$existing_secret_key" ]]; then
    export AWS_SECRET_ACCESS_KEY="$existing_secret_key"
  fi
  if [[ -n "$existing_session_token" ]]; then
    export AWS_SESSION_TOKEN="$existing_session_token"
  fi
  if [[ -n "$existing_region" ]]; then
    export AWS_REGION="$existing_region"
  fi
}

run_check() {
  local label="$1"
  local script_path="$2"

  echo "Running ${label}"
  if "$PYTHON_BIN" "$script_path"; then
    return 0
  fi
  return 1
}

print_summary() {
  local overall="FAIL"
  if [[ "$S3_STATUS" -eq 0 && "$DDB_STATUS" -eq 0 && "$BEDROCK_STATUS" -eq 0 && "$VECTOR_STATUS" -eq 0 ]]; then
    overall="PASS"
  fi

  echo
  echo "AWS Service Validation Summary"
  echo "S3: $([[ "$S3_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "DynamoDB: $([[ "$DDB_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Bedrock: $([[ "$BEDROCK_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "S3 vector store: $([[ "$VECTOR_STATUS" -eq 0 ]] && echo PASS || echo FAIL)"
  echo "Overall: $overall"

  [[ "$overall" == "PASS" ]]
}

load_env
unset DEBUG
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN"
  exit 1
fi

cd "$ROOT_DIR" || exit 1

run_check "S3 check" "tests/aws_check_s3.py"
S3_STATUS=$?

run_check "DynamoDB check" "tests/aws_check_dynamodb.py"
DDB_STATUS=$?

run_check "Bedrock check" "tests/aws_check_bedrock.py"
BEDROCK_STATUS=$?

run_check "S3 vector store check" "tests/aws_check_vector_store.py"
VECTOR_STATUS=$?

if print_summary; then
  exit 0
fi

exit 1
