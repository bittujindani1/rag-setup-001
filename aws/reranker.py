from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Iterable, List

from langchain_core.documents import Document


LOGGER = logging.getLogger(__name__)
TOKEN_PATTERN = re.compile(r"\w+")
MAX_CONTEXT_CHARS = 18000


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(text or "")}


def _normalized_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def _is_near_duplicate(existing_chunks: List[Document], candidate: Document) -> bool:
    candidate_text = _normalized_text(candidate.page_content)
    candidate_section = str(candidate.metadata.get("section_id", "") or "")
    candidate_filename = str(candidate.metadata.get("filename", "") or "")
    for existing in existing_chunks:
        existing_text = _normalized_text(existing.page_content)
        existing_section = str(existing.metadata.get("section_id", "") or "")
        existing_filename = str(existing.metadata.get("filename", "") or "")
        if candidate_filename and existing_filename == candidate_filename and candidate_section and candidate_section == existing_section:
            return True
        if candidate_filename and existing_filename == candidate_filename:
            similarity = SequenceMatcher(None, existing_text[:1800], candidate_text[:1800]).ratio()
            if similarity >= 0.9:
                return True
    return False


def rerank_chunks(
    query: str,
    chunks: Iterable[Document],
    *,
    final_k: int = 10,
    max_context_chars: int = MAX_CONTEXT_CHARS,
    max_chunks_per_doc: int = 3,
    bedrock_client=None,
) -> List[Document]:
    query_terms = _tokenize(query)
    scored_chunks: List[tuple[float, Document]] = []

    for chunk in chunks:
        text = chunk.page_content or chunk.metadata.get("text", "")
        chunk_terms = _tokenize(text)
        overlap_count = len(query_terms & chunk_terms)
        lexical_score = (overlap_count / len(query_terms)) if query_terms else 0.0
        embedding_score = float(chunk.metadata.get("vector_score", chunk.metadata.get("score", 0.0)) or 0.0)
        final_score = (0.7 * embedding_score) + (0.3 * lexical_score)

        metadata = dict(chunk.metadata)
        metadata.update(
            {
                "text": text,
                "filename": metadata.get("filename"),
                "page_number": metadata.get("page_number", metadata.get("page_num")),
                "score": final_score,
                "vector_score": embedding_score,
                "lexical_score": lexical_score,
            }
        )
        scored_chunks.append((final_score, Document(page_content=text, metadata=metadata)))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)

    if bedrock_client is not None and scored_chunks:
        try:
            top_documents = [chunk for _, chunk in scored_chunks[: max(final_k * 4, 40)]]
            reranked_scores = bedrock_client.rerank_texts(query, [doc.page_content for doc in top_documents], top_n=len(top_documents))
            if reranked_scores:
                rerank_by_index = {
                    int(item["index"]): float(item["relevance_score"])
                    for item in reranked_scores
                    if item.get("index") is not None
                }
                rescored_chunks: List[tuple[float, Document]] = []
                for index, (base_score, chunk) in enumerate(scored_chunks):
                    if index in rerank_by_index:
                        combined_score = (0.85 * rerank_by_index[index]) + (0.15 * base_score)
                    else:
                        combined_score = base_score
                    chunk.metadata["rerank_score"] = rerank_by_index.get(index)
                    chunk.metadata["score"] = combined_score
                    rescored_chunks.append((combined_score, chunk))
                scored_chunks = sorted(rescored_chunks, key=lambda item: item[0], reverse=True)
        except Exception:
            LOGGER.exception("Cross-encoder reranking failed; using heuristic scores only.")

    final_chunks: List[Document] = []
    per_document_counts: dict[str, int] = {}
    total_chars = 0
    for score, chunk in scored_chunks:
        if len(final_chunks) >= final_k:
            break
        filename = str(chunk.metadata.get("filename", "") or "")
        if filename and per_document_counts.get(filename, 0) >= max_chunks_per_doc:
            continue
        if _is_near_duplicate(final_chunks, chunk):
            continue
        chunk_chars = len(chunk.page_content or "")
        if final_chunks and total_chars + chunk_chars > max_context_chars:
            continue
        total_chars += chunk_chars
        chunk.metadata["score"] = score
        final_chunks.append(chunk)
        if filename:
            per_document_counts[filename] = per_document_counts.get(filename, 0) + 1

    LOGGER.info(
        "Reranker selected final_chunks=%s total_context_chars=%s",
        len(final_chunks),
        total_chars,
    )
    return final_chunks
