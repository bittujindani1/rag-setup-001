#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TERRAFORM_DIR="$ROOT_DIR/terraform"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_DOCKERFILE="$ROOT_DIR/docker/Dockerfile.lambda"
LOCAL_PYTHON_DEFAULT="$ROOT_DIR/.venv_local/Scripts/python.exe"
CALL_ANALYZER_AWSCLI_PYTHON_DEFAULT="/c/Users/dhairya.jindani/Documents/AI-coe projects/Call Analyzer/.venv/Scripts/python.exe"
NODE_DIR_DEFAULT="/c/Users/dhairya.jindani/Downloads/npm code/node-v22.14.0-win-x64"
TERRAFORM_PATH_DEFAULT="/c/Users/dhairya.jindani/Documents/AI-coe projects/bkp-1/Call Analyzer/.tools/terraform.exe"

export PATH="${NODE_DIR:-$NODE_DIR_DEFAULT}:$PATH"

PYTHON_BIN="${PYTHON_BIN:-$LOCAL_PYTHON_DEFAULT}"
CALL_ANALYZER_AWSCLI_PYTHON="${CALL_ANALYZER_AWSCLI_PYTHON:-$CALL_ANALYZER_AWSCLI_PYTHON_DEFAULT}"

log() {
  printf '[pipeline] %s\n' "$*"
}

fail() {
  printf '[pipeline] ERROR: %s\n' "$*" >&2
  exit 1
}

resolve_terraform() {
  if [[ -n "${TERRAFORM_BIN:-}" ]]; then
    printf '%s\n' "$TERRAFORM_BIN"
    return 0
  fi
  if [[ -x "$TERRAFORM_PATH_DEFAULT" ]]; then
    printf '%s\n' "$TERRAFORM_PATH_DEFAULT"
    return 0
  fi
  if command -v terraform >/dev/null 2>&1; then
    command -v terraform
    return 0
  fi
  fail "Terraform not found. Set TERRAFORM_BIN before running this script."
}

terraform_cmd() {
  local tf_bin
  tf_bin="$(resolve_terraform)"
  "$tf_bin" "$@"
}

aws_cmd() {
  if command -v aws.cmd >/dev/null 2>&1; then
    aws.cmd "$@"
    return 0
  fi
  if command -v aws >/dev/null 2>&1; then
    aws "$@"
    return 0
  fi
  if [[ -x "$CALL_ANALYZER_AWSCLI_PYTHON" ]]; then
    "$CALL_ANALYZER_AWSCLI_PYTHON" -m awscli "$@"
    return 0
  fi
  fail "AWS CLI not found. Ensure Git Bash has aws available or set CALL_ANALYZER_AWSCLI_PYTHON."
}

require_python() {
  [[ -x "$PYTHON_BIN" ]] || fail "Python executable not found: $PYTHON_BIN"
}

require_frontend() {
  [[ -d "$FRONTEND_DIR" ]] || fail "Frontend directory not found: $FRONTEND_DIR"
}

require_terraform() {
  [[ -d "$TERRAFORM_DIR" ]] || fail "Terraform directory not found: $TERRAFORM_DIR"
}

resolve_docker() {
  if [[ -n "${DOCKER_BIN:-}" ]]; then
    printf '%s\n' "$DOCKER_BIN"
    return 0
  fi
  if command -v docker >/dev/null 2>&1; then
    command -v docker
    return 0
  fi
  if command -v docker.exe >/dev/null 2>&1; then
    command -v docker.exe
    return 0
  fi
  fail "Docker not found. Set DOCKER_BIN before running image build/push steps."
}

docker_cmd() {
  local docker_bin
  docker_bin="$(resolve_docker)"
  "$docker_bin" "$@"
}

terraform_output_raw() {
  terraform_cmd -chdir="$TERRAFORM_DIR" output -raw "$1"
}

ensure_frontend_env() {
  local api_url="$1"
  local index_name="${2:-statefarm_rag}"
  cat >"$FRONTEND_DIR/.env.production" <<EOF
VITE_API_BASE_URL=$api_url
VITE_INDEX_NAME=$index_name
EOF
}
