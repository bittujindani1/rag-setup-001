#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

SKIP_PREFLIGHT="${SKIP_PREFLIGHT:-false}"
SKIP_FRONTEND_SYNC="${SKIP_FRONTEND_SYNC:-false}"
SKIP_IMAGE_BUILD="${SKIP_IMAGE_BUILD:-false}"
LAMBDA_IMAGE_URI="${LAMBDA_IMAGE_URI:-}"

require_terraform
require_frontend

if [[ "$SKIP_PREFLIGHT" != "true" ]]; then
  bash "$SCRIPT_DIR/preflight.sh"
fi

if [[ "$SKIP_IMAGE_BUILD" != "true" && -z "$LAMBDA_IMAGE_URI" ]]; then
  LAMBDA_IMAGE_URI="$(bash "$SCRIPT_DIR/build_lambda_image.sh" | tail -n 1)"
fi

terraform_cmd -chdir="$TERRAFORM_DIR" init

TF_ARGS=()
if [[ -n "$LAMBDA_IMAGE_URI" ]]; then
  TF_ARGS+=("-var=lambda_image_uri=$LAMBDA_IMAGE_URI")
fi

log "Applying Terraform"
terraform_cmd -chdir="$TERRAFORM_DIR" apply "${TF_ARGS[@]}" "$@"

if [[ "$SKIP_FRONTEND_SYNC" != "true" ]]; then
  bash "$SCRIPT_DIR/sync_frontend.sh"
fi

log "Pipeline trigger complete"
log "Frontend URL: $(terraform_output_raw frontend_url)"
log "Lambda Function URL: $(terraform_output_raw lambda_function_url)"
