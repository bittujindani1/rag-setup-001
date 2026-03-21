from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain.storage import InMemoryStore
from langchain_core.documents import Document
import uuid
import urllib
import sys
from pathlib import Path
from langchain_community.utilities.redis import get_client
from langchain.storage import RedisStore
import os

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from provider_factory import get_config, get_doc_store, get_filename_index


REDIS_PASSWORD  = os.getenv("REDIS_PASSWORD")
REDIS_HOST  = os.getenv("REDIS_HOST")

REDIS_PORT = os.getenv("REDIS_PORT")

redis_url = None
if REDIS_PASSWORD and REDIS_HOST and REDIS_PORT:
    encoded_password = urllib.parse.quote(REDIS_PASSWORD)
    redis_url = f"redis://:{encoded_password}@{REDIS_HOST}:{REDIS_PORT}"


class _RetrieverAdapter:
    def __init__(self, vectorstore, docstore):
        self.vectorstore = vectorstore
        self.docstore = docstore



def create_multi_vector_retriever(
    vectorstore, text_summaries, texts, text_metadata,
    table_summaries, tables, table_metadata,
    image_summaries, images, image_metadata,
    filename, index_name  # Adding filename parameter to associate with each doc_id
):
    config = get_config()
    
    print("towards doc store")
    client = get_client(redis_url) if config.get("doc_store") != "dynamodb" and redis_url else None
    store = RedisStore(client=client) if client else get_doc_store()
    id_key = "doc_id"
    print("intializing Multivector")

    if config.get("vector_store") == "s3" or config.get("doc_store") == "dynamodb":
        retriever = _RetrieverAdapter(vectorstore=vectorstore, docstore=store)
    else:
        retriever = MultiVectorRetriever(
            vectorstore=vectorstore,
            docstore=store,
            id_key=id_key,
        )

    # Helper function to add documents to both vector and Redis stores
    total_indexed = 0

    def add_documents(doc_summaries, doc_contents, doc_metadata):
        nonlocal total_indexed
        print("inside add documents")
        # Generate unique custom `doc_id`s for tracking in Redis
        doc_ids = [str(uuid.uuid4()) for _ in doc_contents]
        summary_docs = [
            Document(
                page_content=s,
                metadata={
                    **metadata,
                    id_key: doc_ids[i],
                    "document_id": filename,
                    "section_id": f"{filename}:section:{i+1}",
                    "chunk_id": doc_ids[i],
                    "hierarchy_level": "chunk",
                }
            )
            for i, (s, metadata) in enumerate(zip(doc_summaries, doc_metadata))
        ]
        print("summmary docs",summary_docs)
        # Add documents to OpenSearch vector store
        retriever.vectorstore.add_documents(summary_docs)
        print("retrieve add docs")
        # Store document content in Redis, with `doc_id` as the key
        retriever.docstore.mset(list(zip(doc_ids, doc_contents)))

        # Store `doc_id`s under filename key in Redis for tracking by filename
        if client:
            filename_key = f"{index_name}:filename:{filename}"
            for custom_doc_id in doc_ids:
                client.sadd(filename_key, custom_doc_id)
        else:
            get_filename_index().add_doc_ids(index_name, filename, doc_ids)
        total_indexed += len(summary_docs)
                    
    print("using add doc function")
    # Add text, table, and image documents with metadata
    if text_summaries and texts and text_metadata:
        add_documents(text_summaries, texts, text_metadata)
    if table_summaries and tables and table_metadata:
        add_documents(table_summaries, tables, table_metadata)
    if image_summaries and images and image_metadata:
        add_documents(image_summaries, images, image_metadata)
    print("create multivector retriever succesfull")
    return retriever, total_indexed
