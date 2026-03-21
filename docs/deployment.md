# Deployment

## Prerequisites

- AWS account with Bedrock access enabled for Titan Embeddings and Claude 3 Haiku
- Terraform installed locally
- Docker available if packaging Lambda/Chainlit images
- AWS CLI configured for the target account
- Git Bash available for local command execution

## Runtime configuration

Start from `.env.example` and set:

- `AWS_REGION`
- `BEDROCK_MODEL`
- `BEDROCK_FALLBACK_MODEL`
- `EMBEDDING_MODEL`
- `S3_BUCKET_DOCUMENTS`
- `S3_BUCKET_VECTORS`
- `S3_BUCKET_EXTRACTED`
- `DYNAMODB_CHAT_HISTORY_TABLE`
- `DYNAMODB_QUERY_CACHE_TABLE`
- `DYNAMODB_DOC_STORE_TABLE`
- `DYNAMODB_FILENAME_INDEX_TABLE`
- `DYNAMODB_RATE_LIMIT_TABLE`
- `DYNAMODB_THREAD_TABLE`
- `RATE_LIMIT_REQUESTS_PER_MINUTE`
- `RAG_API_URL`

## Suggested deployment sequence

1. Build and push the RAG API image for Lambda.
2. Optionally build and push the Chainlit BOT image for ECS Fargate.
3. Update `terraform.tfvars` with image URIs, subnet IDs, and security groups.
4. Run:
   - `terraform -chdir=terraform init`
   - `terraform -chdir=terraform plan`
5. Review plan output.
6. Do not run `terraform apply` until networking, IAM, and Bedrock access are validated.

## Local execution

### RAG API

From `RAG API` in Git Bash:

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### BOT

From `BOT` in Git Bash:

```bash
pip install -r requirements.txt
chainlit run main.py --host 0.0.0.0 --port 5101
```

Set `RAG_API_URL` to the API Gateway URL or the local FastAPI URL.
Set `DYNAMODB_THREAD_TABLE` to `rag_chat_threads` for Chainlit sidebar persistence.

## Local smoke tests

Run these after the API is up:

```bash
python tests/smoke_test_ingest.py
python tests/smoke_test_query.py
```

If you have a preferred fixture PDF, set `TEST_PDF_PATH`. Otherwise the ingest smoke test generates a minimal PDF automatically.

## API testing examples

```bash
curl -X POST "http://localhost:8000/SFRAG/retrieval" \
  -H "Content-Type: application/json" \
  -d '{"user_query":"What does this document describe?","index_name":"smoke-test-index","session_id":"local-dev"}'
```

```bash
curl "http://localhost:8000/metrics"
```

If you burst more than the configured number of retrieval calls for one session in one minute, the API returns HTTP `429`.

## Supported scripts

Use the supported scripts under [`scripts/important/`](C:/Users/dhairya.jindani/Documents/AI-coe%20projects/Rag/scripts/important):

```bash
bash scripts/important/run_local_validation.sh
PYTHON_BIN="$(pwd)/.venv_local/Scripts/python" bash scripts/important/run_aws_service_validation.sh
PYTHON_BIN="$(pwd)/.venv_local/Scripts/python" bash scripts/important/run_support_checks.sh
```

Use [`scripts/maintenance/`](C:/Users/dhairya.jindani/Documents/AI-coe%20projects/Rag/scripts/maintenance) only for deeper troubleshooting or regression repro steps.
