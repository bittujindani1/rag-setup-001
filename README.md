# AWS Serverless RAG Refactor

This repository keeps the existing BOT and FastAPI RAG flow intact while refactoring the infrastructure connectors toward low-cost AWS services.

## What changed

- Added config-driven provider selection in `config/aws_config.yaml`
- Added AWS wrappers in `aws/`
- Replaced Redis chat history with DynamoDB-backed history for the AWS path
- Replaced OpenSearch vector storage with S3-backed JSON embedding storage plus Python cosine similarity
- Added DynamoDB query caching
- Replaced direct OpenAI/Azure/Groq usage in the active path with Bedrock-based wrappers
- Added Terraform scaffolding for S3, DynamoDB, Lambda, API Gateway, IAM, and optional Fargate
- Added smoke tests under `tests/`
- Added `.env.example` for local runtime setup
- Added gzip-compressed S3 embedding objects plus a cached `embeddings_index.json`
- Added `/metrics`, Bedrock fallback, and DynamoDB-backed per-session rate limiting
- Added reranked retrieval: initial top-20 vector recall, score-based reranking, and top-4 context selection
- Removed duplicate retrieval work so the answer chain and citations now share the same retrieved document set
- Removed citation-time LLM filtering in favor of reranker-score-based citation selection

## Current layout

- `BOT`
- `RAG API`
- `aws`
- `config`
- `scripts/important`
- `scripts/maintenance`
- `terraform`
- `docs`

## Environment setup

Copy `.env.example` to `.env` and fill in the values you use locally.

Important variables:

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
- `DOCUMENT_EXTRACTOR_VERIFY_SSL`
- `DOCUMENT_EXTRACTOR_ALLOW_INSECURE_FALLBACK`

## Local workflow

Use Git Bash for the commands below.

1. Install dependencies.

```bash
cd "RAG API"
pip install -r requirements.txt
cd ../BOT
pip install -r requirements.txt
```

2. Start the RAG API.

```bash
cd "RAG API"
uvicorn main:app --host 0.0.0.0 --port 8000
```

3. Start the BOT.

```bash
cd BOT
chainlit run main.py --host 0.0.0.0 --port 5101
```

The Chainlit sidebar thread history uses DynamoDB table `rag_chat_threads`. When you open an older thread from the left panel, click `Resume Chat` before asking the next question.

4. Run local smoke tests.

```bash
python tests/smoke_test_ingest.py
python tests/smoke_test_query.py
```

## Local Validation

Use the bundled validation workflow to start the API locally, wait for `/health`, run both smoke tests, and stop the server automatically.

```bash
cp .env.example .env
bash scripts/important/run_local_validation.sh
```

## AWS Service Validation

Use the lower-cost preflight workflow before a full ingest/query run. It checks S3, DynamoDB, Bedrock, and the S3 vector store individually.

```bash
cp .env.example .env
PYTHON_BIN="$(pwd)/.venv_local/Scripts/python" bash scripts/important/run_aws_service_validation.sh
```

If that passes, run one end-to-end validation:

```bash
TEST_PDF_PATH="/c/Users/dhairya.jindani/Downloads/sample_travel_insurance_policy_test.pdf" \
PYTHON_BIN="$(pwd)/.venv_local/Scripts/python" \
bash scripts/important/run_local_validation.sh
```

If the external document extractor has a broken or expired TLS certificate, the backend now retries that call once with `verify=False` when `DOCUMENT_EXTRACTOR_ALLOW_INSECURE_FALLBACK=true`. Keep `DOCUMENT_EXTRACTOR_VERIFY_SSL=true` by default so healthy certificates still validate first.

## API examples

Ingest a PDF:

```bash
curl -X POST "http://localhost:8000/SFRAG/ingest" \
  -F "index_name=smoke-test-index" \
  -F "file=@tests/smoke_test_input.pdf;type=application/pdf"
```

Run a query:

```bash
curl -X POST "http://localhost:8000/SFRAG/retrieval" \
  -H "Content-Type: application/json" \
  -d '{"user_query":"What does this document describe?","index_name":"smoke-test-index","session_id":"smoke-test-session"}'
```

Read local metrics:

```bash
curl "http://localhost:8000/metrics"
```

## Retrieval behavior

The active retrieval path is now:

`query -> S3 vector search top 20 -> rerank -> top 4 -> context budget trim -> Bedrock`

Performance-focused notes:

- S3 vector search now reads `page_content` directly from `embeddings_index.json`, so retrieval no longer performs S3 `GET` calls per result.
- The same retrieved documents are reused for both answer generation and citation generation.
- Citations are selected from reranked chunk scores rather than an extra Bedrock filtering call.
- Query cache keys normalize the query text before hashing to improve cache hit rate.

Relevant config in [`config/aws_config.yaml`](C:/Users/dhairya.jindani/Documents/AI-coe%20projects/Rag/config/aws_config.yaml):

- `reranker.enabled`
- `reranker.initial_k`
- `reranker.final_k`

Example 429 behavior:

```bash
curl -X POST "http://localhost:8000/SFRAG/retrieval" \
  -H "Content-Type: application/json" \
  -d '{"user_query":"What does this document describe?","index_name":"smoke-test-index","session_id":"burst-session"}'
```

If the session exceeds the current per-minute limit, the API returns HTTP `429` with a message telling the caller to wait or increase the limit.

## Troubleshooting

Use the supported support-check script if local UI, citations, extractor, or retrieval flows stop working:

```bash
PYTHON_BIN="$(pwd)/.venv_local/Scripts/python" bash scripts/important/run_support_checks.sh
```

This checks:

- API `/health`
- API `/metrics`
- Chainlit `/login`
- AWS preflight access
- retrieval-only flow
- extractor-only flow

Script organization:

- supported scripts: [`scripts/important/`](C:/Users/dhairya.jindani/Documents/AI-coe%20projects/Rag/scripts/important)
- maintenance/reference scripts: [`scripts/maintenance/`](C:/Users/dhairya.jindani/Documents/AI-coe%20projects/Rag/scripts/maintenance)

Citation notes:

- PDF citations now return a fresh presigned S3 URL on each retrieval
- image citation buttons now open inline previews directly from the image URL
- citation selection uses reranked document scores and preserves `filename`, `page_number`, and `score`

## Useful scripts

Restart the Chainlit UI and wait until it is reachable:

```bash
bash scripts/important/restart_ui.sh
```

Run one fresh end-to-end ingest + query job:

```bash
bash scripts/important/run_e2e_job.sh
```

Use a new PDF by setting `TEST_PDF_PATH` to a full path before running the job:

```bash
export TEST_PDF_PATH="/c/Users/dhairya.jindani/Downloads/sample_travel_insurance_policy_test.pdf"
bash scripts/important/run_e2e_job.sh
```

If `TEST_PDF_PATH` is not set, the script uses:

- [`tests/sample_docs/test_insurance.pdf`](C:/Users/dhairya.jindani/Documents/AI-coe%20projects/Rag/tests/sample_docs/test_insurance.pdf)

## Logs to watch

- `CACHE_HIT`
- `VECTOR_SEARCH_LATENCY`
- `BEDROCK_LATENCY`
- `TOTAL_CHUNKS_INDEXED`

## Terraform validation

Only validate Terraform locally. Do not run `terraform apply`.

```bash
terraform -chdir=terraform init
terraform -chdir=terraform plan
```

See the docs folder for architecture, deployment, cost, and developer notes.
