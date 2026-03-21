# Developer Guide

## Configuration

The active backend is controlled through `config/aws_config.yaml` and environment variable overrides.

Important keys:

- `vector_store`
- `doc_store`
- `chat_history`
- `cache`
- `llm`
- `embedding_model`
- `llm_model`
- `dynamodb_thread_table`
- `reranker.enabled`
- `reranker.initial_k`
- `reranker.final_k`

## Key integration seams

- `RAG API/vectordb_utils.py`
- `RAG API/customretriever.py`
- `RAG API/customchain.py`
- `RAG API/ingest_doc.py`
- `RAG API/main.py`
- `BOT/utils.py`
- `BOT/main.py`

## Notes

- The AWS path is designed to minimize changes to the existing code shape.
- The S3 vector store is intentionally simple and cost-optimized, not high-throughput.
- If needed later, the config layer can switch providers again without rewriting endpoint code.
- Chainlit thread persistence is separate from RAG chat history and now uses `aws/thread_store.py`.
- Retrieval now uses a two-stage pattern: broad vector recall first, then lightweight in-process reranking.
- `RAG API/main.py` prepares retrieval context once per query and reuses it for both answer generation and citations.
- `RAG API/citations.py` no longer calls Bedrock to filter citations; it uses reranker scores from the retrieved docs.
- `aws/dynamodb_store.py` uses `batch_get_item` for doc hydration to cut round trips during retrieval.
- `aws/cache_manager.py` normalizes query text before hashing, which improves cache hit rates for punctuation/casing variants.

## Script layout

- Supported scripts live in [`scripts/important/`](C:/Users/dhairya.jindani/Documents/AI-coe%20projects/Rag/scripts/important)
- Maintenance/reference helpers live in [`scripts/maintenance/`](C:/Users/dhairya.jindani/Documents/AI-coe%20projects/Rag/scripts/maintenance)

Recommended entry point for troubleshooting:

```bash
PYTHON_BIN="$(pwd)/.venv_local/Scripts/python" bash scripts/important/run_support_checks.sh
```

## UI behavior notes

- Sidebar thread history requires DynamoDB table `rag_chat_threads`.
- Opening an older thread from the sidebar requires clicking `Resume Chat`.
- PDF citations are refreshed on each retrieval to avoid expired S3 links.
- Image citations open inline via the BOT action callback.
