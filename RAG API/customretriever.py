from langchain_community.storage import RedisStore
from langchain_community.utilities.redis import get_client
import logging
import urllib
import os
import sys
from pathlib import Path
from langchain_core.retrievers import BaseRetriever
from requests_aws4auth import AWS4Auth
from opensearchpy import RequestsHttpConnection
from langchain.vectorstores import OpenSearchVectorSearch
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from langchain_openai import AzureOpenAIEmbeddings
from pydantic import ConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from provider_factory import get_bedrock_client, get_config, get_doc_store, get_s3_vector_store
from aws.reranker import MAX_CONTEXT_CHARS, rerank_chunks

LOGGER = logging.getLogger(__name__)

# %pip install --upgrade --quiet  rank_bm25 > /dev/null

REDIS_PASSWORD  = os.getenv("REDIS_PASSWORD")
REDIS_HOST  = os.getenv("REDIS_HOST")

REDIS_PORT = os.getenv("REDIS_PORT")

redis_url = None
store = None
if REDIS_PASSWORD and REDIS_HOST and REDIS_PORT:
    encoded_password = urllib.parse.quote(REDIS_PASSWORD)
    redis_url = f"redis://:{encoded_password}@{REDIS_HOST}:{REDIS_PORT}"
    client = get_client(redis_url)
    store = RedisStore(client=client)
id_key = "doc_id"



AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_SERVICE = os.getenv("AWS_SERVICE")

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL")

awsauth = None
if AWS_ACCESS_KEY and AWS_SECRET_KEY and AWS_REGION and AWS_SERVICE:
    awsauth = AWS4Auth(AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, AWS_SERVICE)

api_key = os.getenv("AZURE_OPENAI_API_KEY")
azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_version = os.getenv("AZURE_API_VERSION")

embedding_function = None
if api_key and azure_endpoint and api_version:
    os.environ["AZURE_OPENAI_API_KEY"] = api_key
    embedding_function = AzureOpenAIEmbeddings(
        azure_deployment="text-embedding-ada-002",
        openai_api_version=api_version,
        azure_endpoint=azure_endpoint,
    )



def create_retriever(index_name: str):
    config = get_config()
    if config.get("vector_store") == "s3":
        return AWSMultiVectorRetriever(index_name=index_name)

    if not (embedding_function and OPENSEARCH_URL and awsauth and redis_url):
        raise RuntimeError("OpenSearch/Redis retriever dependencies are not configured.")

    from langchain.retrievers.multi_vector import MultiVectorRetriever

    # Initialize the vectorstore
    vectorstore = OpenSearchVectorSearch(
        index_name=index_name,
        embedding_function=embedding_function,  
        opensearch_url=OPENSEARCH_URL,
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )

    # Initialize the RedisStore
    client = get_client(redis_url)
    store = RedisStore(client=client)
    id_key = "doc_id"

    # Create the MultiVectorRetriever
    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=store,
        id_key=id_key,
        search_kwargs={
            "k": 5,
        }
    )
    return retriever


#Define Ensemble Retriever logic
def create_ensemble_retriever(vectorstore_retriever, query):
    # Step 1: Retrieve documents from vectorstore retriever
    vector_docs = vectorstore_retriever.get_relevant_documents(query)
    LOGGER.info("Vector docs retrieved count=%s", len(vector_docs))
    if not vector_docs:
        LOGGER.warning("No documents retrieved for query=%s. Using dummy document.", query)
        vector_docs = [
            Document(
                page_content="No relevant content available.",
                metadata={"min_role": query, "info": "dummy"}
            )
        ]
    document_objects = []
    for doc in vector_docs:
        if isinstance(doc, Document):
            document_objects.append(doc)
        elif isinstance(doc, bytes):
            document_objects.append(Document(page_content=doc.decode("utf-8"), metadata={}))
        else:
            document_objects.append(Document(page_content=str(doc), metadata={}))
    # Step 2: Initialize BM25Retriever
    # img_docs=
    keyword_retriever = BM25Retriever.from_documents(document_objects)
    keyword_retriever.k = 5

    class StaticDocumentRetriever(BaseRetriever):
        model_config = ConfigDict(arbitrary_types_allowed=True)
        documents: list[Document]

        def _get_relevant_documents(self, query: str, *, run_manager=None):
            return list(self.documents)

        async def _aget_relevant_documents(self, query: str, *, run_manager=None):
            return list(self.documents)

    class LightweightEnsembleRetriever(BaseRetriever):
        model_config = ConfigDict(arbitrary_types_allowed=True)
        primary: BaseRetriever
        secondary: BaseRetriever

        def _merge(self, primary_docs, secondary_docs):
            merged = []
            seen = set()
            for doc in list(primary_docs) + list(secondary_docs):
                key = (
                    doc.metadata.get("chunk_id"),
                    doc.metadata.get("document_id"),
                    doc.page_content[:200],
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(doc)
            return merged

        def _get_relevant_documents(self, query: str, *, run_manager=None):
            primary_docs = self.primary.get_relevant_documents(query)
            secondary_docs = self.secondary.get_relevant_documents(query)
            return self._merge(primary_docs, secondary_docs)

        async def _aget_relevant_documents(self, query: str, *, run_manager=None):
            return self._get_relevant_documents(query, run_manager=run_manager)

    # Step 3: Combine both retrievers without depending on optional langchain.retrievers package.
    ensemble_retriever = LightweightEnsembleRetriever(
        primary=StaticDocumentRetriever(documents=document_objects),
        secondary=keyword_retriever,
    )
    LOGGER.info("Created ensemble retriever query=%s", query)
    return ensemble_retriever


class AWSMultiVectorRetriever(BaseRetriever):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    index_name: str
    config: dict
    vectorstore: object
    docstore: object
    id_key: str = "doc_id"
    k: int = 5

    def __init__(self, index_name: str) -> None:
        config = get_config()
        reranker_config = config.get("reranker", {})
        super().__init__(
            index_name=index_name,
            config=config,
            vectorstore=get_s3_vector_store(index_name),
            docstore=get_doc_store(),
            id_key="doc_id",
            k=int(reranker_config.get("initial_k", 20)),
        )

    def _hydrate(self, summary_docs):
        doc_ids = [doc.metadata.get(self.id_key) for doc in summary_docs if doc.metadata.get(self.id_key)]
        raw_docs = self.docstore.mget(doc_ids) if doc_ids else []
        hydrated = []
        for summary_doc, raw_doc in zip(summary_docs, raw_docs):
            hydrated.append(
                Document(
                    page_content=raw_doc or summary_doc.page_content,
                    metadata=dict(summary_doc.metadata),
                )
            )
        return hydrated

    def _get_relevant_documents(self, query: str, *, run_manager=None):
        reranker_config = self.config.get("reranker", {})
        initial_k = int(reranker_config.get("initial_k", self.k))
        final_k = int(reranker_config.get("final_k", self.config.get("retrieval_k", 4)))
        summary_docs = self.vectorstore.similarity_search(query, k=initial_k)
        hydrated_docs = self._hydrate(summary_docs)
        if reranker_config.get("enabled", True):
            final_docs = rerank_chunks(
                query,
                hydrated_docs,
                final_k=final_k,
                max_context_chars=MAX_CONTEXT_CHARS,
            )
        else:
            final_docs = hydrated_docs[:final_k]
        LOGGER.info("retrieval_initial=%d reranked=%d", len(hydrated_docs), len(final_docs))
        return final_docs

    async def _aget_relevant_documents(self, query: str, *, run_manager=None):
        return self._get_relevant_documents(query, run_manager=run_manager)

#exclude image_base64 from vectore docs and then pass to keyword retriver
#twice call vectorstore vectorstore_retriever.get_relevant_documents(query)=to get text and table
#----vectorstore_retriever.similarity_search(query)=to get image summaries in text
#---- then add text table and image summaries to pass to keyword retriever  so that it will utilize all to match
#currently imgaes are going as base 64 thats why not it may not match keyword on image 
