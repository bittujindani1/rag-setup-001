from __future__ import annotations

import logging
import re
from typing import Iterable, List

from langchain_core.documents import Document


LOGGER = logging.getLogger(__name__)
TOKEN_PATTERN = re.compile(r"\w+")
MAX_CONTEXT_CHARS = 18000


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(text or "")}


def rerank_chunks(
    query: str,
    chunks: Iterable[Document],
    *,
    final_k: int = 10,
    max_context_chars: int = MAX_CONTEXT_CHARS,
    max_chunks_per_doc: int = 3,
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

    final_chunks: List[Document] = []
    per_document_counts: dict[str, int] = {}
    total_chars = 0
    for score, chunk in scored_chunks:
        if len(final_chunks) >= final_k:
            break
        filename = str(chunk.metadata.get("filename", "") or "")
        if filename and per_document_counts.get(filename, 0) >= max_chunks_per_doc:
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
