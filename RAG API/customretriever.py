from langchain_community.storage import RedisStore
from langchain_community.utilities.redis import get_client
import logging
import urllib
import os
import re
import sys
from pathlib import Path
from langchain_core.retrievers import BaseRetriever
from requests_aws4auth import AWS4Auth
from opensearchpy import RequestsHttpConnection
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from langchain_openai import AzureOpenAIEmbeddings
from pydantic import ConfigDict
from collections import defaultdict

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


def _retrieve_documents(retriever, query: str):
    if hasattr(retriever, "invoke"):
        return retriever.invoke(query)
    return retriever.get_relevant_documents(query)



def create_retriever(index_name: str, corpus_version: str = ""):
    config = get_config()
    if config.get("vector_store") == "s3":
        return AWSMultiVectorRetriever(index_name=index_name, corpus_version=corpus_version)

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
    # For the AWS retriever, retrieval is already true hybrid over the full corpus.
    if isinstance(vectorstore_retriever, AWSMultiVectorRetriever):
        LOGGER.info("Using built-in hybrid retriever query=%s", query)
        return vectorstore_retriever
    return vectorstore_retriever


def _expand_query(query: str) -> str:
    lowered = (query or "").lower()
    expansions: list[str] = []
    synonym_map = {
        "claim process": ["claim procedure", "claims procedure", "reimbursement flow", "filing a claim"],
        "waiting period": ["cooling period", "initial waiting period"],
        "clause": ["section", "article"],
    }
    for phrase, synonyms in synonym_map.items():
        if phrase in lowered:
            expansions.extend(synonyms)
    if not expansions:
        return query
    return f"{query} {' '.join(expansions)}"


def _query_variants(query: str) -> list[str]:
    variants = [query]
    expanded = _expand_query(query)
    if expanded != query:
        variants.append(expanded)

    lowered = (query or "").lower()
    if " and " in lowered:
        for part in [item.strip() for item in re.split(r"\band\b", query, flags=re.IGNORECASE) if item.strip()]:
            variants.append(part)
            expanded_part = _expand_query(part)
            if expanded_part != part:
                variants.append(expanded_part)
    return list(dict.fromkeys(item for item in variants if item))


def _doc_key(doc: Document) -> tuple[str, str, str]:
    metadata = doc.metadata or {}
    return (
        str(metadata.get("chunk_id") or metadata.get("section_id") or ""),
        str(metadata.get("document_id") or metadata.get("filename") or ""),
        (doc.page_content or "")[:200],
    )


def _deduplicate_documents(documents: list[Document]) -> list[Document]:
    deduplicated: list[Document] = []
    seen: set[tuple[str, str, str]] = set()
    for doc in documents:
        key = _doc_key(doc)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(doc)
    return deduplicated


def _apply_doc_diversity(documents: list[Document], max_chunks_per_doc: int = 3) -> list[Document]:
    diversified: list[Document] = []
    counts: dict[str, int] = defaultdict(int)
    for doc in documents:
        filename = str(doc.metadata.get("filename", "") or "")
        if filename and counts[filename] >= max_chunks_per_doc:
            continue
        diversified.append(doc)
        if filename:
            counts[filename] += 1
    return diversified


def _promote_to_parent_context(documents: list[Document]) -> list[Document]:
    promoted: list[Document] = []
    seen_parent_keys: set[tuple[str, str]] = set()
    for doc in documents:
        metadata = dict(doc.metadata)
        parent_text = str(metadata.get("parent_text", "") or "").strip()
        parent_id = str(metadata.get("parent_id", "") or "")
        if parent_text and parent_id:
            parent_key = (str(metadata.get("filename", "") or ""), parent_id)
            if parent_key in seen_parent_keys:
                continue
            seen_parent_keys.add(parent_key)
            metadata["section_id"] = parent_id
            promoted.append(Document(page_content=parent_text, metadata=metadata))
            continue
        promoted.append(doc)
    return promoted


def _rrf_merge(dense_docs: list[Document], sparse_docs: list[Document], limit: int) -> list[Document]:
    scored: dict[tuple[str, str, str], tuple[float, Document]] = {}
    for rank, doc in enumerate(dense_docs, start=1):
        key = _doc_key(doc)
        score = 1.0 / (60 + rank)
        current = scored.get(key)
        scored[key] = (score + (current[0] if current else 0.0), current[1] if current else doc)
    for rank, doc in enumerate(sparse_docs, start=1):
        key = _doc_key(doc)
        score = 1.0 / (60 + rank)
        current = scored.get(key)
        base_doc = current[1] if current else doc
        scored[key] = (score + (current[0] if current else 0.0), base_doc)

    merged = []
    for score, doc in sorted(scored.values(), key=lambda item: item[0], reverse=True):
        metadata = dict(doc.metadata)
        metadata["rrf_score"] = score
        merged.append(Document(page_content=doc.page_content, metadata=metadata))
    return merged[:limit]


class AWSMultiVectorRetriever(BaseRetriever):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    index_name: str
    config: dict
    vectorstore: object
    docstore: object
    corpus_version: str = ""
    id_key: str = "doc_id"
    k: int = 40
    corpus_documents: list[Document] | None = None
    bm25_retriever: object | None = None

    def __init__(self, index_name: str, corpus_version: str = "") -> None:
        config = get_config()
        reranker_config = config.get("reranker", {})
        super().__init__(
            index_name=index_name,
            config=config,
            vectorstore=get_s3_vector_store(index_name, corpus_version),
            docstore=get_doc_store(),
            corpus_version=corpus_version,
            id_key="doc_id",
            k=int(reranker_config.get("initial_k", 40)),
            corpus_documents=None,
            bm25_retriever=None,
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

    def _load_full_corpus_docs(self) -> list[Document]:
        if self.corpus_documents is not None:
            return self.corpus_documents
        index_entries = self.vectorstore.get_index_entries()
        doc_ids = [entry.get("doc_id") for entry in index_entries if entry.get("doc_id")]
        raw_docs = self.docstore.mget(doc_ids) if doc_ids else []
        corpus_documents: list[Document] = []
        for entry, raw_doc in zip(index_entries, raw_docs):
            metadata = dict(entry.get("metadata", {}))
            metadata.update(
                {
                    "filename": metadata.get("filename"),
                    "document_id": metadata.get("document_id", metadata.get("filename")),
                    "chunk_id": metadata.get("chunk_id", entry.get("doc_id")),
                    "section_id": metadata.get("section_id", metadata.get("chunk_id", entry.get("doc_id"))),
                }
            )
            corpus_documents.append(
                Document(
                    page_content=raw_doc or entry.get("page_content", ""),
                    metadata=metadata,
                )
            )
        self.corpus_documents = corpus_documents
        return corpus_documents

    def _get_bm25_retriever(self):
        if self.bm25_retriever is None:
            corpus_documents = self._load_full_corpus_docs()
            self.bm25_retriever = BM25Retriever.from_documents(corpus_documents)
        return self.bm25_retriever

    def _sparse_search(self, query: str, *, k: int) -> list[Document]:
        bm25_retriever = self._get_bm25_retriever()
        bm25_retriever.k = k
        sparse_docs = _retrieve_documents(bm25_retriever, query)
        enriched_docs: list[Document] = []
        for rank, doc in enumerate(sparse_docs, start=1):
            metadata = dict(doc.metadata)
            metadata["lexical_rank"] = rank
            enriched_docs.append(Document(page_content=doc.page_content, metadata=metadata))
        return enriched_docs

    def _get_relevant_documents(self, query: str, *, run_manager=None):
        reranker_config = self.config.get("reranker", {})
        initial_k = int(reranker_config.get("initial_k", self.k))
        final_k = int(reranker_config.get("final_k", self.config.get("retrieval_k", 10)))
        query_variants = _query_variants(query)
        dense_candidates: list[Document] = []
        sparse_candidates: list[Document] = []
        for variant in query_variants:
            summary_docs = self.vectorstore.similarity_search(variant, k=initial_k)
            dense_candidates.extend(self._hydrate(summary_docs))
            sparse_candidates.extend(self._sparse_search(variant, k=initial_k))
        hydrated_docs = _deduplicate_documents(dense_candidates)
        sparse_docs = _deduplicate_documents(sparse_candidates)
        hybrid_candidates = _rrf_merge(hydrated_docs, sparse_docs, limit=max(initial_k * 2, final_k * 3))
        hybrid_candidates = _apply_doc_diversity(_deduplicate_documents(hybrid_candidates), max_chunks_per_doc=3)
        if reranker_config.get("enabled", True):
            final_docs = rerank_chunks(
                query,
                hybrid_candidates,
                final_k=final_k,
                max_context_chars=MAX_CONTEXT_CHARS,
                max_chunks_per_doc=3,
                bedrock_client=get_bedrock_client(),
            )
        else:
            final_docs = hybrid_candidates[:final_k]
        final_docs = _promote_to_parent_context(_apply_doc_diversity(final_docs, max_chunks_per_doc=3))
        LOGGER.info(
            "retrieval_variants=%d retrieval_dense=%d retrieval_sparse=%d hybrid_candidates=%d reranked=%d",
            len(query_variants),
            len(hydrated_docs),
            len(sparse_docs),
            len(hybrid_candidates),
            len(final_docs),
        )
        return final_docs

    async def _aget_relevant_documents(self, query: str, *, run_manager=None):
        return self._get_relevant_documents(query, run_manager=run_manager)

#exclude image_base64 from vectore docs and then pass to keyword retriver
#twice call vectorstore vectorstore_retriever.get_relevant_documents(query)=to get text and table
#----vectorstore_retriever.similarity_search(query)=to get image summaries in text
#---- then add text table and image summaries to pass to keyword retriever  so that it will utilize all to match
#currently imgaes are going as base 64 thats why not it may not match keyword on image 
