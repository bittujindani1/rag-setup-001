#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

IMAGE_TAG="${IMAGE_TAG:-latest}"

require_terraform

if [[ ! -f "$BACKEND_DOCKERFILE" ]]; then
  fail "Lambda Dockerfile not found: $BACKEND_DOCKERFILE"
fi

log "Preparing Lambda build context"
rm -rf "$ROOT_DIR/docker/rag_api_build"
cp -R "$ROOT_DIR/RAG API" "$ROOT_DIR/docker/rag_api_build"

log "Ensuring ECR repository exists via targeted Terraform apply"
terraform_cmd -chdir="$TERRAFORM_DIR" init
terraform_cmd -chdir="$TERRAFORM_DIR" apply -target=aws_ecr_repository.rag_api -auto-approve

REPOSITORY_URL="$(terraform_output_raw ecr_repository_url)"
ACCOUNT_ID="$(aws_cmd sts get-caller-identity --query Account --output text)"

log "Logging in to ECR: $REPOSITORY_URL"
aws_cmd ecr get-login-password --region ap-south-1 | docker_cmd login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.ap-south-1.amazonaws.com"

log "Building Lambda image ${REPOSITORY_URL}:${IMAGE_TAG}"
docker_cmd build -f "$BACKEND_DOCKERFILE" -t "${REPOSITORY_URL}:${IMAGE_TAG}" "$ROOT_DIR"

log "Pushing Lambda image ${REPOSITORY_URL}:${IMAGE_TAG}"
docker_cmd push "${REPOSITORY_URL}:${IMAGE_TAG}"

log "Lambda image pushed successfully"
printf '%s:%s\n' "$REPOSITORY_URL" "$IMAGE_TAG"
