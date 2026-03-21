import os.path
import pickle
from typing import Dict, List, Optional
import os
import uuid
import json
import requests
import base64
import aiohttp
import asyncio
import sys
from pathlib import Path
from langchain_core.output_parsers import StrOutputParser
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from env_bootstrap import bootstrap_env
from provider_factory import get_bedrock_client

bootstrap_env(Path(__file__).resolve().parent / ".env")


sys_msg = """You are a helpful Knowledge Base AI Agent capable of using a variety of tools to answer a question and assign an appropriate retrieval method based on the user's query. Make sure to use only one tool at a time by relating to the Context: {messages}. Here are a few of the tools available to you:

- Greeting: The Greeting tool should be used whenever you get the greetings message like "hi, good morning, happy morning, good afternoon, good evening" etc.

- End: The End tool should be used whenever you are requested to end the conversation like "bye, thanks for the chat, see you, byebye" etc.

- Acknowledge: The Acknowledge tool must be used to respond to the user when the user just provides some random details. 
               You must acknowledge the details provided by the user and ask how you can assist further regarding the details provided.

- Issue: The Issue tool should only be used when the query involves anything related to **insurance** or **auto insurance** stuff,concepts,rules,etc. 
        -if issue tool identified create query only using users most recently asked question . do not use previous messages, if you can't identify question clearly from recent user message from {messages} then only see, else do not add any other words of your own.
         The `"input"` should be a structured query based on the user's message, ensuring that the retrieval is successful and accurate.
         - If the application name is irrelevant to the issue, keep `application_name` as "not provided". 
         The output for the Issue tool should only include `"tool"` and `"input"`.
         -strictly adhere to users message and do not generate any words of your own for issue tool
         if tool is issue and recent user query is asking about something related to its previous question then get a context from {messages}, search for recent question and answer provided  and create the query accordingly
        for example, if user asked " give me difference between mandatory coverage and optional coverage" then next question user asked is -"can u give tabular output" then your structured query will be "can u give me tabular output showing difference between mandatory coverage and optional coverage"

- General: if user query doesn't relate to any other tool and it is some kind of general question like who is pm, what is country of this, general knowledge questions if asked then return General tool.for such tool you must not provide any answer based on your training and respond only that "I am Technical Assistant and I do not have information regarding this topic"
         - Do not respond to general tool question. ONLY state that "Sorry, I am a Technical support assistant. I don't have the information on this."
The output must be a structured dictionary with key-value pairs. For example, to answer the query, "good evening" you must use the Greeting tool to respond like so:

```json
{
    "tool": "Greeting",
    "input": "Hey happy evening, How can I help you?"
    
}
Or for the query "bye" you must respond:
{
    "tool": "End",
    "input": "Happy to assist you!"
}
Or for the query "I booked insurance" you must respond:
{
    "tool": "Acknowledge",
    "input": "It's great to hear that you have insurance, How can I help you on it?"
    
}
Or to answer the Issue "what are the optional coverage" you must respond:
{
    "tool": "Issue",
    "input": "what are the optional coverage"
}
Or for the query "who is narendra modi" you must respond:
{
    "tool": "General",
    "input": "Sorry, I am a Technical support assistant. I don't have the information on this."
    
}
Or for the query "give me a recipe for dhokla" you must respond:
{
    "tool": "General",
    "input": "Sorry, I am a Technical support assistant. I don't have the information on this."
}
If the user's query can include one question or multiple questions, you need to identify the integrated tool for it and keep all questions as they are.
from {messages} you should always get the context of user s recent question and specify tools accordingly.
 Let's get started.The user's query is as follows: """


from langchain.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatOpenAI
import os

bedrock_client = get_bedrock_client()

def generate_session_id():
    # Generate a UUID and remove the hyphens
    session_id = str(uuid.uuid4()).replace("-", "")
    return session_id


def _bedrock_completion(system_prompt: str, user_prompt: str, max_tokens: int = 512, temperature: float = 0.1) -> str:
    return bedrock_client.generate_text(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
    )

# def multiquery(question):
#     # Template to generate alternative queries
#     template = """You are an AI language model assistant. Your task is to generate three
#     different versions of the given user question to retrieve relevant documents from a vector
#     database. By generating multiple perspectives on the user question, your goal is to help
#     the user overcome some of the limitations of the distance-based similarity search.
#     Provide these alternative questions separated by newlines. Original question: {question}"""

#     # Create a prompt template
#     prompt_perspectives = ChatPromptTemplate.from_template(template)

#     # Initialize the language model
#     res = ChatOpenAI(temperature=0)
#     print(f"multiquery,{res}")

#     # Function to generate alternative queries
#     prompt = prompt_perspectives.format_messages(question=question)
#     response = res(prompt)
#     output = response.content
#     queries = output.strip().split('\n')
#     print(queries)
#     return queries
    

# def paraphrase(question):
   
#     # Template to generate alternative queries
#     template = """You are an AI language model assistant. Your task is to paraphrase the given user question in three different ways. By generating multiple variations of the user question, your goal is to help the user retrieve relevant information from a database more effectively.
#     Provide these paraphrased questions separated by newlines. Original question: {question}"""

#     # Create a prompt template
#     prompt_perspectives = ChatPromptTemplate.from_template(template)

#     # Initialize the language model
#     res = ChatOpenAI(temperature=0)

#     # Function to generate alternative queries
#     prompt = prompt_perspectives.format_messages(question=question)
#     response = res(prompt)
#     output = response.content
#     queries = output.strip().split('\n')
#     return queries

# from langchain_core.output_parsers import StrOutputParser
# def decomposition(question):
#     # Decomposition
#     template = """You are a helpful assistant that generates multiple sub-questions related to an input question. \n
#     The goal is to break down the input into a set of sub-problems / sub-questions that can be answers in isolation. \n
#     Generate multiple search queries related to: {question} \n
#     Output (3 queries):"""
#     prompt_decomposition = ChatPromptTemplate.from_template(template)
    
#     # LLM
#     res = ChatOpenAI(temperature=0)
    
#     # Chain
#     generate_queries_decomposition = ( prompt_decomposition | res | StrOutputParser() | (lambda x: x.split("\n")))
#     questions = generate_queries_decomposition.invoke({"question":question})
#     return questions

# from langchain.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate
# def step_back(initial_question):
#     # Function to Generate Step-Back Questions
#     """
#     Generates a list of step-back questions from the initial question.
#     Args:
#         initial_question (str): The starting question.
#         max_steps (int): The maximum number of step-back iterations.
#     Returns:
#         List[str]: A list of step-back questions.
#     """
#     # Few-Shot Examples
#     examples = [
#         {
#             "input": "Could the members of The Police perform lawful arrests?",
#             "output": "what can the members of The Police do?",
#         },
#         {
#             "input": "Jan Sindel’s was born in what country?",
#             "output": "what is Jan Sindel’s personal history?",
#         },
#     ]
    
#     # Example Prompt
#     example_prompt = ChatPromptTemplate.from_messages(
#         [
#             ("human", "{input}"),
#             ("ai", "{output}"),
#         ]
#     )
    
#     # Few-Shot Prompt Template
#     few_shot_prompt = FewShotChatMessagePromptTemplate(
#         example_prompt=example_prompt,
#         examples=examples,
#     )
    
#     # Main Prompt
#     main_prompt = ChatPromptTemplate.from_messages(
#         [
#             (
#                 "system",
#                 """You are an expert at world knowledge. Your task is to step back and paraphrase a question to a more generic step-back question, which is easier to answer. Here are a few examples:""",
#             ),
#             # Few-shot examples
#             few_shot_prompt,
#             # New question
#             ("user", "{question}"),
#         ]
#     )
    
#     # Chain to Generate Step-Back Question
#     generate_step_back_chain = main_prompt | ChatOpenAI(temperature=0) | StrOutputParser()
#     max_steps=5
#     questions = [initial_question]
#     for _ in range(max_steps):
#         last_question = questions[-1]
#         step_back_question = generate_step_back_chain.invoke({"question": last_question}).strip()
#         # Check if the new question is the same as the last one to prevent infinite loops
#         if step_back_question.lower() == last_question.lower():
#             break
#         questions.append(step_back_question)
#     return questions
 
# def hyde(question):
#     # Prompt to generate hypothetical questions
#     template = """Please write 3  hypothetical questions that are related to the following question:
    
#     Question: {question}
    
#     Hypothetical Questions:"""
    
#     prompt_hyde = ChatPromptTemplate.from_template(template)
    
#     # LLM chain to generate hypothetical questions
#     generate_hypothetical_questions = (
#         prompt_hyde | ChatOpenAI(temperature=0) | StrOutputParser()
#     )
    
#     output = generate_hypothetical_questions.invoke({"question": question})
    
#     # Parse the output into a list of questions
#     hypothetical_questions = output.strip().split('\n')
#     # print(hypothetical_questions)
#     return hypothetical_questions

image_prompt="""You are an advanced AI assistant tasked with extracting data related to the insurance domain from user-provided images and structuring a query to pass to a retrieval database. You will receive an image containing questions or messages, and you must perform the following tasks:

1. **Extract the question**: Identify and extract the key message from the image provided.
2. **Classify the state**: Determine whether the state is mentioned in the extracted data for which we need to retrieve information.
3. **Generate a Query**: Based on the extracted message, generate a highly accurate query that can retrieve the most relevant resolution from a database.

Your response must always follow this structured JSON format:
```json
{
    "classification": "<user_given_state or none>",
    "error": "<extracted_error_message>",
    "resolution_query": "<generated_query_for_resolution>"
}
Ensure the query is highly specific, concise, and formatted for optimal database retrieval accuracy. If no error is detected, clearly state that."""


async def image_process(encoded_image):
    return await asyncio.to_thread(
        bedrock_client.generate_multimodal_text,
        "Extract the insurance-related question from this image and return only JSON.",
        [encoded_image],
        image_prompt,
        800,
        0.1,
    )


def decomposition(question):
    system_prompt = "Generate up to 3 retrieval-oriented sub-questions, one per line, with no numbering."
    output = _bedrock_completion(system_prompt, question, 200, 0.0)
    return [line.strip() for line in output.splitlines() if line.strip()]



async def modified_retrieval_query(user_query):
   
    # Create the full prompt based on the provided instructions
    system_prompt = """You are an helpful AI assistant who can extract and restructure and divides the user query ,which can be furthure used for maximum data retrieval from vectorstore.
    Given a {user_query}, determine if it:

    1.Contains one or more distinct questions.
    2.Requests a difference or comparison between points.
    3.Asks for similarities or detailed coverage across multiple entities.
    4.Based on the structure and intent of the query, rephrase it to retrieve the most relevant documents or text data from a vector store. Output the query in a JSON format without adding any unnecessary data. Ensure responses are precise and follow the provided examples.
    5.Provide a response strictly as JSON without any additional explanations or text. 
    Example:
    {"query":["What are the optional coverages for Maryland state"]}
    Ensure no additional text, comments, or formatting outside this structure.

    Examples:

    1.User Query: "Give me the difference between mandatory coverages for Nevada and Minnesota state."
    Output: {"query":["What are mandatory coverages for Nevada", "what are mandatory coverages for Minnesota state"]}

    2.User Query: "Can we compare all states' bodily injured coverage?"
    Output: {"query":["Bodily injured coverage for all states"]}

    3.User Query: "Give me the between optional coverages for Nevada and Minnesota state in tabular format."
    Output: {"query":["What are optional coverages for Nevada", "what are optional coverages for Minnesota state"]}

    Instructions:

    -Identify if the query is asking for a difference, comparison, or information about multiple entities.
    -Break down complex or multi-part questions into distinct components where necessary.
    -Remove any format requests (e.g., "in tabular format") as these do not affect the content retrieval.
   -Ensure that ONLY essential information given in the output as JSON which i should be able to parse furthure using json.loads() and it should NOT return as None
    -give consistent output
    """
    # The full prompt with the user query and the document contexts

    # Call Azure OpenAI's API to get chat completion asynchronously
    try:
        # print("sys_prompt#########",system_prompt)
        # print("user_prompt#######",user_prompt)
        extraction_result = await asyncio.to_thread(
            _bedrock_completion,
            system_prompt,
            user_query,
            200,
            0.1,
        )
        print("ext modified query",extraction_result)
        # json_result = json.loads(extraction_result)
        # print("json modified query",json_result)
        return extraction_result
    except Exception as e:
        pass
        return None
    
async def generate_answer(input_dict, original_question):
    # Concatenate all relevant answers
    concatenated_answer = "\n".join([f"{key}: {value}" for key, value in input_dict.items()])
    
    # Generate input prompt for LLM
    input_prompt = f"""
    You are an AI assistant. Below are several answers to distinct questions provided by the user. Your task is to use all these question-answers to construct a well-structured, coherent, and comprehensive response to the user's original question.

    Original question: {original_question}

    Answers: {concatenated_answer}

    Your response should follow these instructions:

    1.Generate a single, thorough response that directly addresses the {original_question} based on the provided answers.
    2.Policy Reply: If the answers are not relevant to the original question, respond with:
    "Sorry, we couldn't provide information on this policy. Could you please connect with the nearest insurer?"
    3.Tabular JSON Format:
    -if {original_question} have words like tabular, table, json, html and requests a tabular format response then and ONLY then you should respond tabular JSON
    -use the answers to produce a tabular JSON output that can be easily converted to a pandas DataFrame.

    Only include necessary information in the JSON output, structuring it as follows:
    {{
    "columns": ["criteria", "Option1", "Option2"],
    "rows": [
        {{"criteria": "Criterion 1", "Option1": "Detailed answer for Option1", "Option2": "Detailed answer for Option2"}},
        {{"criteria": "Criterion 2", "Option1": "Value or Yes/No", "Option2": "Value or Yes/No"}}
        ]
    }}
    for example, if the user requests- 'give me difference between optional covergares of nevada and minnesota state in tabular format'
        ouput JSON=
        {{
        "columns": ["optional coverage", "Nevada", "Minnesota"],
        "rows": [
            {{"optional coverage": "Coverage Requirement", "Nevada": "covers damage to your vehicle when you are involved in an accident with another vehicle or object.", "Minnesota": "PIP is NOT required for motorcyclists in Minnesota. ATVs are not covered by standard auto insurance policies;"}},
            {{"optional coverage": "Uninsured Motorist", "Nevada": "covers a loss that is not the result of a collision. This usually includes fire, theft, hail, or an accident involving a deer", "Minnesota": "includes full glass replacement, towing, and rental car use when your car is unavailable."}},
            {{"optional coverage": "autoinsurance", "Nevada": "covers damage to your vehicle when involved in an accident with another vehicle or object.", "Minnesota": "not applicable"}},
            {{"optional coverage": "collision", "Nevada": "not applicable", "Minnesota": "PIP is NOT required for motorcyclists in Minnesota. ATVs are not covered by standard auto insurance policies;"}}
        ]
        }}
    ***Formatting Guidelines for Tabular JSON:***
    If information is available on common grounds, display it clearly in respective cells.
    If not, fill with "Not applicable" or "Yes/No" as relevant.
    Ensure that each cell value provides detailed information where possible.

    4.if {original_question} is talking about difference , comparison, similarity then use {concatenated_answer} to generate or arrange response accordingly in plain text format and not json.
    - Ensure that you use ONLY {concatenated_answer}to generate final answer based on {original_question}."""
    
    # Pass the prompt to the LLM function to retrieve the final structured answer
    response_data = await asyncio.to_thread(
        _bedrock_completion,
        "You are an AI assistant that synthesizes structured insurance answers from provided source answers only.",
        input_prompt,
        1000,
        0.1,
    )
    
    print("in generate answer",response_data)
    
    return response_data


def classify_tool(groq_input: str, query: str) -> str:
    return _bedrock_completion(groq_input, query, 400, 0.1)

def extract_inner_dict(response_text):
    # Remove outer ```json and ``` if they exist
    response_text = response_text.strip().strip("```json").strip("```").strip()
    
    # Parse JSON text to dictionary
    try:
        data_dict = json.loads(response_text)
        return data_dict
    except json.JSONDecodeError:
        print("Failed to decode JSON. Check the input format.")
        return None
