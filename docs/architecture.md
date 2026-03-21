# Architecture

## Target flow

User -> Chainlit BOT -> API Gateway -> Lambda RAG API -> S3 + DynamoDB + Bedrock

## Preserved application behavior

- Existing `/SFRAG/ingest` and `/SFRAG/retrieval` endpoints remain intact.
- Chainlit BOT continues to call the RAG API over HTTP.
- Ingestion still extracts text, tables, and figures from PDFs.
- Citation generation still runs from retrieved metadata.
- Session-based chat history still exists, now on DynamoDB.
- Chainlit sidebar thread history now persists in DynamoDB via `rag_chat_threads`.

## AWS connector design

- `aws/bedrock_client.py`
  - Titan embeddings
  - Claude 3 Haiku text and multimodal prompts
- `aws/dynamodb_store.py`
  - document store
  - filename index
  - chat history
- `aws/s3_vector_store.py`
  - stores gzip-compressed embedding payloads in S3
  - maintains an `embeddings_index.json` manifest
  - caches the manifest per Lambda execution
  - stores `page_content` in the manifest so retrieval avoids per-result S3 `GET` calls
  - performs NumPy-based cosine similarity search in Python
- `aws/reranker.py`
  - combines embedding similarity with lexical overlap
  - reranks the initial retrieval set
  - preserves citation metadata and score on the final chunk set
- `aws/cache_manager.py`
  - query cache in DynamoDB
- `aws/thread_store.py`
  - Chainlit thread persistence
  - sidebar thread listing and resume support

## Retrieval flow

The current retrieval path is:

1. Initial vector recall from S3 index manifest, typically top 20.
2. Hydration from DynamoDB doc store when needed.
3. Score-based reranking using lexical overlap plus vector similarity.
4. Final top-4 chunk selection.
5. Context-budget trim before Bedrock prompt assembly.
6. The same final chunk set is reused for citations.

This reduces repeated Bedrock and storage work while improving grounding.

## Runtime hardening

- Bedrock wrapper now handles empty responses, invalid JSON payloads, and invocation failures safely.
- Bedrock text generation now falls back from Claude 3 Haiku to Claude 3 Sonnet when the primary model fails or returns unusable output.
- Logging captures cache hits plus embedding, vector search, and LLM latencies.
- The S3 vector manifest is loaded once per warm Lambda execution to reduce repeated list/get work.
- Retrieval is protected by DynamoDB-backed per-session rate limiting.
- `/metrics` exposes process-local averages and cache hit rate for debugging and demos.
- Cache keys normalize query text before hashing to improve hit rate on equivalent user phrasing.
- Citation filtering no longer requires an extra LLM call.

## Local validation path

- `tests/smoke_test_ingest.py` uploads a test PDF and validates the ingestion response.
- `tests/smoke_test_query.py` triggers retrieval and validates response structure and citations.
- `scripts/important/run_support_checks.sh` bundles health, metrics, AWS preflight, extractor-only, and retrieval-only checks.

## Hierarchical retrieval

The ingestion path now tags each stored item with:

- `document_id`
- `section_id`
- `chunk_id`
- `hierarchy_level`

This supports a Document -> Section -> Chunk retrieval model without rewriting the rest of the pipeline.

## Citation runtime behavior

- PDF citation links are refreshed at retrieval time so S3 downloads do not fail on old presigned URLs.
- Image citations are opened directly from their stored PNG URL through the BOT action callback.
- Citation entries are chosen from the reranked chunk list and carry preserved metadata such as `filename`, `page_number`, and `score`.
