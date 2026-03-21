#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

log "Running local AWS identity check"
require_python
"$PYTHON_BIN" "$ROOT_DIR/scripts/important/show_aws_identity.py"

log "Running AWS service validation"
bash "$ROOT_DIR/scripts/important/run_aws_service_validation.sh"

log "Validating Terraform"
terraform_cmd -chdir="$TERRAFORM_DIR" init -backend=false >/dev/null
terraform_cmd -chdir="$TERRAFORM_DIR" validate

log "Building frontend"
require_frontend
pushd "$FRONTEND_DIR" >/dev/null
npm install
npm run build
popd >/dev/null

log "Preflight complete"
