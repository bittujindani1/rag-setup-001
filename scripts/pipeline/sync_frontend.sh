#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

API_URL="${API_URL:-}"
INDEX_NAME="${INDEX_NAME:-statefarm_rag}"

require_frontend
require_terraform

if [[ -z "$API_URL" ]]; then
  API_URL="$(terraform_output_raw lambda_function_url)"
fi

log "Preparing frontend build with API URL: $API_URL"
ensure_frontend_env "$API_URL" "$INDEX_NAME"

pushd "$FRONTEND_DIR" >/dev/null
npm install
npm run build
popd >/dev/null

FRONTEND_BUCKET="$(terraform_output_raw frontend_bucket)"
log "Syncing frontend dist to s3://$FRONTEND_BUCKET"
aws_cmd s3 sync "$FRONTEND_DIR/dist/" "s3://$FRONTEND_BUCKET" --delete

log "Frontend sync complete"
