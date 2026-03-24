import json
import logging
import urllib.parse
import sys
from pathlib import Path
import boto3

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from env_bootstrap import bootstrap_env
from provider_factory import get_config

bootstrap_env(Path(__file__).resolve().with_name(".env"))
LOGGER = logging.getLogger(__name__)
async def get_citations(user_query, retrieved_docs, processed_metadata):
    ranked_pairs = list(zip(retrieved_docs, processed_metadata))
    ranked_pairs.sort(
        key=lambda item: float(item[0].metadata.get("score", 0.0) or 0.0),
        reverse=True,
    )
    filtered_citations = [metadata for _, metadata in ranked_pairs]
    LOGGER.info("Selected citations from reranked docs count=%s", len(filtered_citations))
    deduplicated_metadata = deduplicate_citations(filtered_citations)
    return deduplicated_metadata


def _refresh_presigned_pdf_url(pdf_url: str) -> str:
    if not pdf_url or "amazonaws.com" not in pdf_url:
        return pdf_url

    try:
        config = get_config()
        parsed = urllib.parse.urlparse(pdf_url)
        bucket_name = parsed.netloc.split(".")[0]
        object_key = parsed.path.lstrip("/")
        s3_client = boto3.client("s3", region_name=config["aws_region"])
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": object_key},
            ExpiresIn=3600,
        )
    except Exception:
        return pdf_url


def deduplicate_citations(citations):
    unique_citations = []
    seen = {}

    for citation in citations:
        citation["pdf_url"] = _refresh_presigned_pdf_url(citation.get("pdf_url"))
        # Deduplicate by filename only — presigned URLs differ per chunk
        citation_key = citation.get("filename") or citation.get("pdf_url") or id(citation)

        if citation_key not in seen:
            seen[citation_key] = citation
            unique_citations.append(citation)
        else:
            existing_citation = seen[citation_key]
            existing_urls = existing_citation.get("url", [])
            new_urls = citation.get("url", [])
            combined_urls = list(dict.fromkeys(existing_urls + new_urls))
            existing_citation["url"] = combined_urls

            existing_pages = existing_citation.get("page_numbers", [])
            new_pages = citation.get("page_numbers", [])
            combined_pages = sorted(
                {str(p) for p in (existing_pages + new_pages) if str(p).strip() and str(p) != "N/A"},
                key=lambda x: int(x) if x.isdigit() else 0,
            )
            existing_citation["page_numbers"] = combined_pages

    return unique_citations
