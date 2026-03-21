import asyncio
import logging
import sys
from pathlib import Path
from typing import List

from langchain_core.messages import AIMessage, HumanMessage

from image_utils import split_image_text_types

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from provider_factory import build_chat_history, get_bedrock_client


LOGGER = logging.getLogger(__name__)
MAX_CONTEXT_CHARS = 6000
ANSWER_SYSTEM_PROMPT = """
You are a RAG synthesis assistant who gives final answers to user queries based on images, tables, and text retrieved.
Answer only using the provided context. Do not use outside knowledge, internet knowledge, or assumptions.
If the answer is not available in the provided context, say exactly:
"The documents do not contain this information."
Keep responses direct and professional. Do not mention that the answer was retrieved.
"""


QUESTION_REWRITE_SYSTEM_PROMPT = """
Rewrite the user's latest question into a standalone retrieval query using the recent chat history only when the
latest question depends on earlier context. If it is already standalone, return it unchanged.
"""


def _retrieve_documents(retriever, query: str):
    if hasattr(retriever, "invoke"):
        return retriever.invoke(query)
    return retriever.get_relevant_documents(query)


class MultiModalRAGChainWithHistory:
    def __init__(self, retriever) -> None:
        self.retriever = retriever
        self.bedrock = get_bedrock_client()

    def _history_to_text(self, messages: List) -> str:
        lines = []
        for message in messages[-6:]:
            if isinstance(message, HumanMessage):
                lines.append(f"User: {message.content}")
            elif isinstance(message, AIMessage):
                lines.append(f"Assistant: {message.content}")
        return "\n".join(lines)

    def _rewrite_question(self, user_input: str, history_messages: List) -> str:
        if not history_messages:
            return user_input
        prompt = (
            f"Conversation history:\n{self._history_to_text(history_messages)}\n\n"
            f"Latest user question:\n{user_input}"
        )
        rewritten = self.bedrock.generate_text(
            prompt=prompt,
            system_prompt=QUESTION_REWRITE_SYSTEM_PROMPT,
            max_tokens=256,
            temperature=0.0,
        )
        return rewritten or user_input

    def _build_prompt(self, question: str, history_messages: List, docs: List) -> tuple[str, List[str]]:
        docs = self._limit_docs_to_budget(docs)
        context = split_image_text_types(docs)
        formatted_texts = "\n".join(context["texts"])
        prompt = (
            f"Conversation history:\n{self._history_to_text(history_messages)}\n\n"
            f"User-provided question: {question}\n\n"
            "Text and/or tables retrieved are as follows from which to only answer:\n"
            f"{formatted_texts}"
        )
        return prompt, context["images"]

    def _limit_docs_to_budget(self, docs: List) -> List:
        ordered_docs = sorted(docs, key=lambda doc: float(doc.metadata.get("score", 0.0) or 0.0), reverse=True)
        limited_docs = []
        total_chars = 0
        for doc in ordered_docs:
            doc_chars = len(doc.page_content or "")
            if limited_docs and total_chars + doc_chars > MAX_CONTEXT_CHARS:
                continue
            total_chars += doc_chars
            limited_docs.append(doc)
        return limited_docs

    async def prepare_context(self, user_input: str, session_id: str):
        history = build_chat_history(session_id)
        history_messages = history.messages
        standalone_question = await asyncio.to_thread(self._rewrite_question, user_input, history_messages)
        docs = await asyncio.to_thread(_retrieve_documents, self.retriever, standalone_question)
        return {
            "history": history,
            "history_messages": history_messages,
            "standalone_question": standalone_question,
            "docs": docs,
        }

    async def astream(self, inputs, config=None):
        config = config or {}
        session_id = config.get("configurable", {}).get("session_id", "default")
        user_input = inputs["input"]
        prepared_context = inputs.get("prepared_context")
        if prepared_context is None:
            prepared_context = await self.prepare_context(user_input, session_id)
        history = prepared_context["history"]
        history_messages = prepared_context["history_messages"]
        standalone_question = prepared_context["standalone_question"]
        docs = prepared_context["docs"]
        LOGGER.info("Using prepared retrieval docs count=%s session_id=%s", len(docs), session_id)
        prompt, images = self._build_prompt(standalone_question, history_messages, docs)

        if images:
            response_text = await asyncio.to_thread(
                self.bedrock.generate_multimodal_text,
                prompt,
                images,
                ANSWER_SYSTEM_PROMPT,
                1024,
                0.1,
            )
        else:
            response_text = await asyncio.to_thread(
                self.bedrock.generate_text,
                prompt,
                ANSWER_SYSTEM_PROMPT,
                1024,
                0.1,
            )

        await asyncio.to_thread(
            history.add_messages,
            [HumanMessage(content=user_input), AIMessage(content=response_text)],
        )

        chunk_size = 120
        for index in range(0, len(response_text), chunk_size):
            yield AIMessage(content=response_text[index : index + chunk_size])


def multi_modal_rag_chain(retriever):
    return MultiModalRAGChainWithHistory(retriever)


def multi_modal_rag_chain_with_history(retriever):
    return MultiModalRAGChainWithHistory(retriever)


def create_combine_docs_chain(llm, system_prompt, fallback_response, response_style):
    return {
        "llm": llm,
        "system_prompt": system_prompt,
        "fallback_response": fallback_response,
        "response_style": response_style,
    }
