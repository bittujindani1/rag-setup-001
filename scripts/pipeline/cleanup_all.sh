#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

confirm() {
  local prompt="$1"
  local expected="$2"
  local answer
  read -r -p "$prompt " answer
  [[ "$answer" == "$expected" ]]
}

require_terraform

cat <<EOF
This will delete the deployed MVP infrastructure managed by Terraform and empty the S3 buckets first.

Buckets that may be emptied:
- frontend bucket
- documents bucket
- vectors bucket
- extracted bucket

No delete will happen unless you pass both confirmations.
EOF

if ! confirm "Type DELETE to continue:" "DELETE"; then
  fail "First confirmation did not match. Aborting."
fi

if ! confirm "Type DESTROY EVERYTHING to continue:" "DESTROY EVERYTHING"; then
  fail "Second confirmation did not match. Aborting."
fi

log "Reading current Terraform outputs before destroy"
FRONTEND_BUCKET="$(terraform_output_raw frontend_bucket 2>/dev/null || true)"
DOCUMENTS_BUCKET="$(terraform_output_raw documents_bucket 2>/dev/null || true)"
VECTORS_BUCKET="$(terraform_output_raw vectors_bucket 2>/dev/null || true)"
EXTRACTED_BUCKET="$(terraform_output_raw extracted_bucket 2>/dev/null || true)"

for bucket in "$FRONTEND_BUCKET" "$DOCUMENTS_BUCKET" "$VECTORS_BUCKET" "$EXTRACTED_BUCKET"; do
  if [[ -n "$bucket" ]]; then
    log "Emptying s3://$bucket"
    aws_cmd s3 rm "s3://$bucket" --recursive || true
  fi
done

log "Destroying Terraform-managed infrastructure"
terraform_cmd -chdir="$TERRAFORM_DIR" destroy "$@"

log "Cleanup complete"
