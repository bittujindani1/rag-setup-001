
import base64
import re
from PIL import Image
from langchain_core.documents import Document
import io
from langchain_core.messages import HumanMessage

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
)


def plt_img_base64(img_base64):
    """Display base64 encoded string as image"""
    return f'<img src="data:image/jpeg;base64,{img_base64}" />'

def looks_like_base64(sb):
    """Check if the string looks like base64"""
    return re.match("^[A-Za-z0-9+/]+[=]{0,2}$", sb) is not None

def is_image_data(b64data):
    """Check if base64 data is an image by looking at its start"""
    image_signatures = {
        b"\xff\xd8\xff": "jpg",
        b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a": "png",
        b"\x47\x49\x46\x38": "gif",
        b"\x52\x49\x46\x46": "webp",
    }
    try:
        header = base64.b64decode(b64data)[:8]
        for sig in image_signatures:
            if header.startswith(sig):
                return True
        return False
    except Exception:
        return False

def resize_base64_image(base64_string, size=(128, 128)):
    img_data = base64.b64decode(base64_string)
    img = Image.open(io.BytesIO(img_data))
    resized_img = img.resize(size, Image.LANCZOS)
    buffered = io.BytesIO()
    resized_img.save(buffered, format=img.format)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def split_image_text_types(docs):
    """
    Split base64-encoded images and texts.
    """
    b64_images = []
    texts = []
    for doc in docs:
        # Ensure document content is string, decode if bytes
        if isinstance(doc, Document):
            doc_content = doc.page_content
        else:
            doc_content = doc

        if isinstance(doc_content, bytes):
            doc_content = doc_content.decode("utf-8")

        if looks_like_base64(doc_content) and is_image_data(doc_content):
            doc_content = resize_base64_image(doc_content, size=(1300, 600))
            b64_images.append(doc_content)
        else:
            # Prefix with source filename so the LLM can attribute correctly
            if isinstance(doc, Document) and doc.metadata.get("filename"):
                doc_content = f"[Source: {doc.metadata['filename']}]\n{doc_content}"
            texts.append(doc_content)
    return {"images": b64_images, "texts": texts}



def img_prompt_func(data_dict):
    formatted_texts = "\n".join(data_dict["context"]["texts"])
    messages = []
    if data_dict["context"]["images"]:
        for image in data_dict["context"]["images"]:
            image_message = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"}
            }
            #print("image_message", image_message)
            messages.append(image_message)
    else:
        print("No images found.")

    # Include last few messages from chat history
    chat_history = data_dict.get("chat_history", [])
    print("chat_history", chat_history)
    last_messages = chat_history[-4:]  # Adjust the number as needed

    # Build conversation history string with only message content
    conversation_history = ""
    for msg in last_messages:
        if isinstance(msg, HumanMessage):
            conversation_history += f"User: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            conversation_history += f"Assistant: {msg.content}\n"

    # Ensure 'question' is only the user's question
    question = data_dict['question']
    if isinstance(question, dict) and 'input' in question:
        question = question['input']

    text_message = {
        "type": "text",
        "text": (
            """You are a RAG synthesis assistant who gives final answers to user queries based on images, tables, and text retrieved. Ground the data only to the context provided and not on the factual training data of the LLM. Each response must be crafted based only on the retrieved information to ensure high accuracy and alignment with the user’s specific query.

            ***Key Instructions for Structuring Responses:***
            1.Strict Use of Retrieved Information:
                Base your response entirely on the retrieved content. Do not supplement answers with external knowledge or common-sense information from the general LLM training. The response must reflect only what has been retrieved.
                If the query is unanswerable with the retrieved content, respond with: “I don’t have enough information on this matter and may need to update my knowledge.” Do not provide partial or inferred answers beyond what is retrieved.
            2.Domain-Focused, Relevant Content:
                Only include information that directly addresses the user’s query. For example, if asked about differences between mandatory coverages in Nevada and Minnesota, focus solely on these two states. Exclude irrelevant content, even if retrieved.
                Topic-Specific Clarity: In cases where retrieved information overlaps with other contexts (e.g., general insurance terms or unrelated state laws), isolate only the relevant sections.
            3.Direct and Professional Language:
                Deliver responses directly and concisely. Avoid introductory phrases like “Based on the provided data…” or “From the retrieved information…” or "...as outlined in the retrieved content" and present the answer without referencing the format or source type (e.g., tables, images).do not state that the response is retrieved.
            4.Acknowledging Missing Information:
                If relevant details to fully address the query are unavailable in the retrieved content (such as detailed comparisons or state-specific law breakdowns not included), mention only the available data without making assumptions. Avoid speculating or inferring details beyond the retrieved information.
            5.No Supplementation Beyond Retrieval:
                Do not add supplementary information from your general knowledge base, even if it appears relevant. The response must rely strictly on the retrieved content without additional context or explanations.

            """
            f"Conversation history:\n{conversation_history}\n"
            f"User-provided question: {question}\n\n"
            "Text and/or tables retrieved are as follows from which to only answer:\n"
            f"{formatted_texts}"
        ),
    }
    print("text_message", text_message)
    messages.append(text_message)
    return [HumanMessage(content=messages)]


