import sys
import uuid

from langchain.schema import Document

from aws.metrics import MetricsCollector
from aws.s3_vector_store import S3VectorStore
from provider_factory import get_bedrock_client, get_config


def main() -> int:
    config = get_config()
    suffix = uuid.uuid4().hex[:8]
    filename = f"vector-check-{suffix}.pdf"
    index_name = f"service-check-index-{suffix}"

    store = S3VectorStore(
        bucket_name=config["s3_bucket_vectors"],
        index_name=index_name,
        embedding_client=get_bedrock_client(),
        metrics_collector=MetricsCollector(),
    )

    documents = [
        Document(
            page_content="Trip cancellation coverage reimburses prepaid costs.",
            metadata={"filename": filename, "doc_id": f"doc-cancel-{suffix}", "section_id": "coverage", "chunk_id": "1"},
        ),
        Document(
            page_content="Baggage delay coverage can reimburse essential purchases.",
            metadata={"filename": filename, "doc_id": f"doc-baggage-{suffix}", "section_id": "coverage", "chunk_id": "2"},
        ),
    ]

    try:
        store.add_documents(documents)
        results = store.similarity_search("What covers trip cancellation?", k=2)
        assert results, "No vector search results returned"
        assert any("Trip cancellation" in doc.page_content for doc in results)
        assert filename in store.list_all_filenames()
        store.delete_documents_by_filename(filename)
        assert filename not in store.list_all_filenames()
        print("S3 vector store OK")
        return 0
    except AssertionError as exc:
        print(f"S3 vector validation failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"S3 vector validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
