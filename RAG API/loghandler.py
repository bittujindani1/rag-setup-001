

from langchain.callbacks.base import BaseCallbackHandler
from typing import Any, List, Dict
from uuid import UUID

class LoggingCallbackHandler(BaseCallbackHandler):
    def __init__(self):
        self.total_tokens = 0
        self.llm_responses = []
        self.retrieved_documents = []

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ):
        print("\n--- LLM Start ---")
        for idx, prompt in enumerate(prompts):
            print(f"Prompt {idx + 1}:\n{prompt}\n")

    def on_llm_end(self, response, **kwargs: Any):
        print("--- LLM End ---")
        # Log the generations
        print(response)
        for idx, generations in enumerate(response.generations):
            print(f"Prompt {idx + 1} Generations:")
            for gen_idx, generation in enumerate(generations):
                print(f"Generation {gen_idx + 1}:\n{generation.text.strip()}\n")
        # Collect token usage from response.llm_output
        if response.llm_output:
            print(response.llm_output)
            # usage = response.llm_output['token_usage']
            # total_tokens = usage.get('total_tokens', 0)
            # self.total_tokens += total_tokens
            # print(f"Tokens used: {total_tokens}")
        else:
            print("Token usage not available.")
        # Append the response to llm_responses
        self.llm_responses.append(response)

    def on_llm_error(self, error: BaseException, **kwargs: Any):
        print(f"LLM Error: {error}")

    def on_retriever_start(
        self, serialized: Dict[str, Any], query: str, **kwargs: Any
    ):
        print("\n--- Retriever Start ---")
        print(f"Query: {query}\n")

    def on_retriever_end(self, documents, **kwargs: Any):
        print("--- Retriever End ---")
        # Log retrieved documents
        self.retrieved_documents.extend(documents)
        print(f"Retrieved {len(documents)} documents:")
        print(documents)


    def on_retriever_error(self, error: BaseException, **kwargs: Any):
        print(f"Retriever Error: {error}")