# Migration Handoff - RAG MVP Enhancement

**Team:** ai-coe  
**Created By:** dhairya

## Quick Start for New Session

Tell the AI assistant:

> Read HANDOFF.md and .claude/plans/unified-roaming-blanket.md, then start implementing Phase 1 (backend enhancements).

---

## What We Are Building

7 enhancements to the existing RAG application, deployed as a cost-optimized MVP (~$8-18/mo) on AWS serverless.

| # | Feature | Summary |
|---|---------|---------|
| 1 | Delete History | 3-dot menu per thread with delete (clears BOTH DynamoDB tables) |
| 2 | Document Upload | Presigned S3 upload, 5MB limit, PDF/DOCX/TXT/XLSX |
| 3 | Smart Multi-Doc RAG | Disambiguation when query matches multiple doc categories |
| 4 | Auto-Categorize | LLM classifies docs at ingest time, category badges in UI |
| 5 | React Frontend | Replace Chainlit with React SPA (MUI v5, TypeScript, Vite) |
| 6 | AWS Deployment | S3 static site + Lambda Function URL (no ALB/Fargate/API Gateway) |
| 7 | Synthetic Tickets | ~150 ServiceNow tickets for demo, ingested via CSV/JSON |

---

## Architecture

```
[Browser] --HTTP--> [S3 Static Website]      React SPA
[Browser] --HTTPS-> [Lambda Function URL]    FastAPI RAG API (Mangum)
                         |
              [S3 / DynamoDB / Bedrock]
```

### AWS Services (17 total, fully serverless)

| Service | Purpose | Status |
|---------|---------|--------|
| S3 - frontend | React static website (public-read) | NEW |
| S3 - documents | Raw uploads (with CORS for presigned PUT) | EXISTS |
| S3 - vectors | Embeddings + index | EXISTS |
| S3 - extracted | Extracted content | EXISTS |
| Lambda + Function URL | FastAPI RAG API (replaces API Gateway) | EXISTS + NEW |
| DynamoDB - chat_history | Conversations (by session_id) | EXISTS |
| DynamoDB - chat_threads | Thread metadata (by thread_id) | EXISTS |
| DynamoDB - doc_store | Document chunks | EXISTS |
| DynamoDB - filename_index | Filename to doc map | EXISTS |
| DynamoDB - query_cache | Cache (TTL) | EXISTS |
| DynamoDB - rate_limits | Rate limiting (TTL) | EXISTS |
| DynamoDB - document_categories | Category metadata | NEW |
| DynamoDB - ingest_jobs | Ingestion progress tracking | NEW |
| Bedrock | Claude Haiku + Titan Embed | EXISTS |
| ECR | Backend Docker image | EXISTS |
| IAM | Roles + bucket policies | EXISTS |
| CloudWatch | Lambda logs | EXISTS |

### Services Explicitly Removed

- ~~API Gateway~~ -- Lambda Function URL is free and simpler
- ~~CloudFront~~ -- S3 website hosting for v1 (add later for HTTPS)
- ~~ALB~~ -- not needed
- ~~ECS/Fargate~~ -- not needed
- ~~VPC/NAT~~ -- not needed

---

## Key Decisions (All Finalized)

1. **React over Chainlit** -- S3 static hosting (~$0.25/mo) vs Fargate (~$24/mo)
2. **Lambda Function URL over API Gateway** -- free, one less service
3. **Presigned S3 uploads** -- browser uploads directly to S3, avoids Lambda 6MB payload limit
4. **Synchronous ingestion** -- Lambda does NOT support durable background tasks; asyncio.create_task() is not viable. Ingest runs synchronously within Lambda's 900s timeout. Status tracked in DynamoDB for UI recovery.
5. **No auth for v1** -- open public demo, no JWT
6. **No CloudFront for v1** -- S3 website is HTTP-only; this is acceptable for the MVP, and HTTP frontend -> HTTPS Lambda Function URL is allowed by browsers
7. **Separate indexes** -- insurance docs and support tickets use different `index_name` values
8. **File types** -- PDF, DOCX, TXT, XLSX (needs python-docx, openpyxl)
9. **Ticket ingestion** -- CSV/JSON directly (not converted to PDF)

---

## Critical Implementation Notes

These were identified during code review and would break the implementation if missed:

### 1. Delete Must Clear TWO Tables
`DynamoDBThreadStore.delete_thread()` at `aws/thread_store.py:202` only deletes from `rag_chat_threads`. Conversation messages live separately in `rag_chat_history` keyed by `session_id`. The `session_id` is stored in thread metadata at `BOT/main.py:177` as `metadata={"session_id": session_id}`. Delete must:
- Query thread to get session_id from metadata
- Call `DynamoDBChatMessageHistory.clear()` at `aws/dynamodb_store.py:117`
- Then call `DynamoDBThreadStore.delete_thread()`

### 2. Terraform Resource Names
The repo uses these exact names (do NOT guess):
- `aws_apigatewayv2_api.rag_http_api` (NOT `http_api`)
- `aws_lambda_function.rag_api`
- `aws_ecs_cluster.chainlit` / `aws_ecs_task_definition.chainlit` / `aws_ecs_service.chainlit`

### 3. Lambda Entry Point
Mangum handler at `RAG API/lambda_handler.py:6`:
```python
from mangum import Mangum
handler = Mangum(app)
```

### 4. S3 CORS for Presigned Uploads
The documents S3 bucket needs CORS configuration for browser PUT uploads. Without this, presigned uploads will fail silently.

### 5. Deploy Order Matters
Docker image MUST be pushed to ECR BEFORE `terraform apply`. And `VITE_API_URL` must be set from terraform output BEFORE `npm run build`.

### 6. S3 Frontend is HTTP-Only
S3 website hosting does not support HTTPS. Lambda Function URL is HTTPS. This is acceptable for the MVP because browsers allow an HTTP page to call an HTTPS API; that is not mixed content. If HTTPS for the frontend is needed later, CloudFront can be added as a follow-up enhancement (~$0.50/mo).

### 7. AWS Credentials and CLI
The repo works correctly with the shared AWS credentials file at `%USERPROFILE%\\.aws\\credentials` and the local Python environments. The machine-wide `python -m awscli` path may be broken because `awscli` and `botocore` are version-mismatched there, but that is not the supported runtime for this repo.

Use these supported paths instead:
- `scripts/important/run_aws_service_validation.sh` for AWS preflight checks
- `scripts/important/show_aws_identity.py` to verify the active boto3 credential source
- `.venv_local\\Scripts\\python.exe` for local backend and validation runs

Current validated behavior:
- boto3 in `.venv_local` resolves credentials via the shared credentials file
- STS, S3, DynamoDB, Bedrock, and the S3 vector store all passed from the repo validation script

---

## Codebase Map

```
RAG/
  BOT/                          # Chainlit frontend (LEGACY after migration)
    main.py                     # Chat handler, tool classification, thread management
    utils.py                    # Helper functions
    Dockerfile                  # Container config
  RAG API/                      # FastAPI backend (PRIMARY - all new endpoints go here)
    main.py                     # FastAPI app: /SFRAG/ingest, /SFRAG/retrieval, /health, /metrics
    lambda_handler.py           # Mangum wrapper for Lambda
    customchain.py              # Multi-modal RAG chain with history, prompt building
    customretriever.py          # Ensemble retriever (vector + BM25), reranking
    ingest_doc.py               # Document ingestion pipeline
    extraction.py               # Text/table/image extraction from PDF
    citations.py                # Citation dedup and presigned URL refresh
    metadata.py                 # Metadata creation (filename, type, page_numbers)
    summary.py                  # Text/image summarization
    vectordb_utils.py           # Vector store initialization
    Dockerfile                  # Container config for Lambda
    requirements.txt            # Dependencies (includes Mangum)
  aws/                          # AWS service wrappers
    bedrock_client.py           # Bedrock LLM + embeddings
    s3_vector_store.py          # S3-based vector storage with cosine similarity
    dynamodb_store.py           # DynamoDB: doc store, filename index, chat history
    thread_store.py             # DynamoDB: thread store + Chainlit data layer
    cache_manager.py            # Query caching
    reranker.py                 # Document reranking (70% embedding + 30% lexical)
    rate_limiter.py             # Per-session rate limiting
    metrics.py                  # Performance metrics
    document_extractor.py       # External extraction service wrapper
  config/
    aws_config.yaml             # AWS service configuration
  terraform/
    main.tf                     # S3, DynamoDB, Lambda, API Gateway, IAM, optional Fargate
    variables.tf                # aws_region, project_name, lambda_image_uri, etc.
    outputs.tf                  # api_gateway_url, bucket names
  scripts/important/            # Supported scripts (validation, restart, e2e)
  tests/                        # Smoke tests
  config_loader.py              # YAML + env config loader
  provider_factory.py           # Factory for AWS service instances
  env_bootstrap.py              # Load .env files
```

### Existing API Endpoints

| Method | Path | Purpose | File:Line |
|--------|------|---------|-----------|
| GET | /health | Health check | RAG API/main.py:104 |
| GET | /metrics | Performance metrics | RAG API/main.py:143 |
| POST | /SFRAG/retrieval | Query + answer with citations | RAG API/main.py:158 |
| POST | /SFRAG/ingest | Upload and process PDF | RAG API/main.py:291 |

### Existing Data Models

| Class | File:Line | Purpose |
|-------|-----------|---------|
| QueryRequest | RAG API/main.py:98 | Retrieval request (user_query, index_name, session_id) |
| DynamoDBChatMessageHistory | aws/dynamodb_store.py:89 | Chat messages by session_id |
| DynamoDBThreadStore | aws/thread_store.py:27 | Thread CRUD (thread_id + timestamp) |
| DynamoDBDocStore | aws/dynamodb_store.py:33 | Document chunk storage |
| DynamoDBFilenameIndex | aws/dynamodb_store.py:55 | Filename to doc_id mapping |
| S3VectorStore | aws/s3_vector_store.py | Embedding storage + cosine similarity search |
| AWSMultiVectorRetriever | RAG API/customretriever.py | Retriever with metadata (filename, type, page) |
| MultiModalRAGChainWithHistory | RAG API/customchain.py | Chain: query rewrite -> retrieve -> answer |

### Key Config

| Variable | Purpose | Current Value |
|----------|---------|---------------|
| AWS_REGION | Region | ap-south-1 |
| BEDROCK_MODEL | Primary LLM | anthropic.claude-3-haiku-20240307-v1:0 |
| BEDROCK_FALLBACK_MODEL | Fallback LLM | anthropic.claude-3-sonnet-20240229-v1:0 |
| EMBEDDING_MODEL | Embeddings | amazon.titan-embed-text-v2:0 |
| VECTOR_STORE | Store type | s3 |
| DOC_STORE | Store type | dynamodb |

---

## New API Endpoints to Build

| Method | Path | Feature | Purpose |
|--------|------|---------|---------|
| GET | /SFRAG/threads | 1 | List threads for sidebar |
| GET | /SFRAG/threads/{thread_id} | 1 | Get thread with messages |
| DELETE | /SFRAG/threads/{thread_id} | 1 | Delete thread + chat history |
| POST | /SFRAG/threads | 5 | Create new thread |
| POST | /SFRAG/threads/{thread_id}/messages | 5 | Save message to thread |
| POST | /SFRAG/upload-url | 2 | Generate presigned S3 PUT URL |
| GET | /SFRAG/ingest-status/{job_id} | 2 | Poll ingestion progress |
| GET | /SFRAG/categories/{index_name} | 4 | List categories with doc counts |
| GET | /SFRAG/documents/{index_name} | 4 | List documents with categories |
| POST | /SFRAG/ingest-tickets | 7 | Ingest CSV/JSON tickets directly |

Modify existing:
- `POST /SFRAG/ingest` -- accept `s3_key` param (read from S3 instead of multipart)
- `POST /SFRAG/retrieval` -- accept `document_filter` and `category_filter` params

---

## New Files to Create

| File | Feature | Purpose |
|------|---------|---------|
| RAG API/document_router.py | 3 | Disambiguation logic: group chunks by category, classify ambiguity |
| scripts/generate_servicenow_tickets.py | 7 | Generate ~150 synthetic tickets |
| scripts/deploy.sh | 6 | Full deployment: docker push -> terraform -> build -> S3 sync |
| frontend/ (entire directory) | 5 | React SPA with MUI v5 |

---

## React Frontend Stack

| Concern | Choice |
|---------|--------|
| Framework | React 18 + TypeScript |
| Build | Vite |
| UI | MUI v5 (dark theme) |
| State (local) | Zustand |
| State (server) | TanStack React Query |
| Streaming | fetch() + ReadableStream |
| Markdown | react-markdown + remark-gfm |

### React App Structure

```
frontend/
  src/
    api/           - client.ts, threads.ts, retrieval.ts, upload.ts, categories.ts
    stores/        - useChatStore.ts, useUIStore.ts
    hooks/         - useStreamingResponse.ts, useThreads.ts, useCategories.ts
    components/
      layout/      - AppLayout, Sidebar, Header
      chat/        - ChatContainer, MessageList, MessageBubble, MessageInput,
                     StreamingMessage, CitationPanel, DisambiguationCard
      threads/     - ThreadList, ThreadItem (3-dot menu + delete), ThreadDeleteDialog
      upload/      - FileUploadZone, UploadProgress
      categories/  - CategoryList, CategoryChip
    types/         - TypeScript interfaces
    theme/         - MUI dark theme
  package.json
  vite.config.ts
  tsconfig.json
```

---

## Implementation Order

```
PHASE 1 - Backend (Week 1-2):
  1. Thread list + delete (BOTH chat_threads AND chat_history tables)
  2. Presigned upload URL + S3 ingest + multi-format extraction (DOCX, TXT, XLSX)
  3. Ingest status tracking via DynamoDB (synchronous Lambda, status polling)
  4. Document router + disambiguation
  5. Auto-categorize + category API + filtered retrieval
  6. Ticket generation script + direct CSV/JSON ingestion
  7. Thread CRUD endpoints for React

PHASE 2 - React Frontend (Week 3-5):
  Week 3: Vite scaffold, MUI theme, layout, chat + streaming
  Week 4: Thread sidebar (3-dot delete), presigned file upload + status polling, citations
  Week 5: Categories panel, disambiguation UI, ticket corpus UI, polish

PHASE 3 - Deployment (Week 6):
  1. Build and push Lambda Docker image to ECR
  2. Terraform: S3 public website + Lambda Function URL + new DynamoDB tables
  3. Remove: API Gateway, ECS/Fargate resources from Terraform
  4. Deploy script: docker push -> terraform apply -> npm build -> S3 sync
  5. Update README.md
  6. End-to-end testing on public URL
```

---

## Verification Checklist

- [ ] Delete: 3-dot menu -> delete -> thread gone from sidebar AND chat_history cleared (both tables)
- [ ] Upload: Presigned URL upload of 4MB PDF -> success; 6MB -> rejected; DOCX/TXT/XLSX work
- [ ] Ingest status: UI shows extracting -> categorizing -> embedding -> done
- [ ] Smart RAG: Medical + auto insurance -> "what's the coverage?" -> disambiguation -> select -> attributed answer
- [ ] Categories: Ingested docs auto-categorized -> shown in sidebar -> filter works
- [ ] Tickets: Generate CSV -> ingest into separate corpus -> find similar tickets -> results don't mix with insurance
- [ ] React: Chat streaming -> citations -> upload -> delete -> categories all working
- [ ] Deployment: docker push -> terraform apply -> S3 sync -> public URL works end-to-end
- [ ] CORS: S3-hosted UI calls Lambda Function URL without errors

---

## Detailed Plan File

For full Terraform HCL snippets, deploy script, and additional details:
`.claude/plans/unified-roaming-blanket.md`
