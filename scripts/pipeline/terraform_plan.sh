#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PLAN_FILE="${PLAN_FILE:-$TERRAFORM_DIR/mvp-demo.tfplan}"

require_terraform
log "Initializing Terraform"
terraform_cmd -chdir="$TERRAFORM_DIR" init

log "Creating Terraform plan at $PLAN_FILE"
terraform_cmd -chdir="$TERRAFORM_DIR" plan -out="$PLAN_FILE" "$@"

log "Terraform plan complete"
