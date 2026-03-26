import base64
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from provider_factory import get_bedrock_client


def generate_text_summaries(texts, tables, summarize_texts=True):
    client = get_bedrock_client()
    # These summaries remain useful for metadata and answer synthesis, but raw chunk text
    # is now the primary retrieval input used for embeddings.
    prompt_text = """
You are an AI assistant tasked with summarizing tables and text for optimized retrieval.
Capture the main themes, important keywords, structure, key facts, and retrieval-friendly details.
"""

    text_summaries = []
    table_summaries = []

    if texts and summarize_texts:
        for text in texts:
            text_summaries.append(
                client.generate_text(
                    prompt=f"Summarize this text for retrieval:\n{text}",
                    system_prompt=prompt_text,
                    max_tokens=600,
                    temperature=0.0,
                )
            )
    elif texts:
        text_summaries = texts

    if tables:
        for table in tables:
            table_summaries.append(
                client.generate_text(
                    prompt=f"Summarize this table for retrieval:\n{table}",
                    system_prompt=prompt_text,
                    max_tokens=600,
                    temperature=0.0,
                )
            )

    return text_summaries, table_summaries


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def generate_img_summaries(path):
    img_base64_list = []
    image_summaries = []
    client = get_bedrock_client()
    prompt = """
Describe this image in detail for retrieval. Include labels, numbers, tables, graphs, page features,
and any details that would help identify or answer questions about it later.
"""

    for img_file in sorted(os.listdir(path)):
        if img_file.endswith(".png"):
            img_path = os.path.join(path, img_file)
            base64_image = encode_image(img_path)
            img_base64_list.append(base64_image)
            image_summaries.append(
                client.generate_multimodal_text(
                    text_prompt=prompt,
                    images_base64=[base64_image],
                    system_prompt="Return a concise but detailed retrieval summary.",
                    max_tokens=800,
                    temperature=0.0,
                )
            )

    return img_base64_list, image_summaries
