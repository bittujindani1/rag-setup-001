import asyncio
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import aiohttp
import chainlit as cl
import chainlit.data as cl_data
import pandas as pd
from chainlit.context import context as chainlit_context
from chainlit.types import ThreadDict

from utils import (
    classify_tool,
    extract_inner_dict,
    generate_answer,
    generate_session_id,
    image_process,
    modified_retrieval_query,
    sys_msg,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from aws.thread_store import ChainlitDynamoThreadDataLayer, DynamoDBThreadStore
from env_bootstrap import bootstrap_env

bootstrap_env(Path(__file__).resolve().parent / ".env")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
LOGGER = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
THREAD_TABLE_NAME = os.getenv("DYNAMODB_THREAD_TABLE", "rag_chat_threads")
thread_store = DynamoDBThreadStore(table_name=THREAD_TABLE_NAME, region_name=AWS_REGION)
cl_data._data_layer = ChainlitDynamoThreadDataLayer(thread_store)

RAG_API_URL = os.getenv("RAG_API_URL", "http://localhost:8000")
RAG_INDEX_NAME = os.getenv("BOT_INDEX_NAME", os.getenv("TEST_INDEX_NAME", "statefarm_rag"))
DOCUMENT_QUERY_HINTS = (
    "document",
    "policy",
    "coverage",
    "claim",
    "claims",
    "insurance",
    "benefit",
    "benefits",
    "premium",
    "travel insurance",
    "baggage",
    "medical",
)


async def _send_file_preview(file_url: str) -> None:
    file_name = file_url.split("/")[-1].split("?")[0] or "citation"
    elements = [
        cl.File(
            name=file_name,
            url=file_url,
            display="inline",
        ),
    ]
    await cl.Message(content="", elements=elements).send()


@cl.action_callback("png_action")
async def on_png_action(action):
    try:
        await _send_file_preview(action.value)
    except Exception as e:
        return {"error": f"An error occurred: {str(e)}"}


@cl.action_callback("pdf_action")
async def on_pdf_action(action):
    try:
        await _send_file_preview(action.value)
    except Exception as e:
        return {"error": f"An error occurred: {str(e)}"}



@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    if (username, password) == ("admin", "admin"):
        return cl.User(identifier="admin")
    else:
        return None


def _system_message():
    return {
        "role": "Agent",
        "content": "You are a helpful KnowledgeBase AI Agent who tries their best to answer questions."
    }


def _restore_message_history(thread: ThreadDict) -> list:
    history = [_system_message()]
    for step in thread.get("steps", []):
        step_type = step.get("type")
        content = (step.get("output") or step.get("input") or "").strip()
        if not content:
            continue
        if step_type == "user_message":
            history.append({"role": "user", "content": content})
        elif step_type == "assistant_message":
            history.append({"role": "Agent", "content": content})
    return history


def _get_message_history() -> list:
    history = cl.user_session.get("message_history")
    if not history:
        history = [_system_message()]
        cl.user_session.set("message_history", history)
    return history


def _is_table_request(question: str) -> bool:
    lowered = (question or "").lower()
    return "tabular" in lowered or "table" in lowered


def _is_html_request(question: str) -> bool:
    return "html" in (question or "").lower()


def _format_structured_answer(answer_text: str, output_mode: str) -> str:
    parsed = extract_inner_dict(answer_text)
    if not parsed or "rows" not in parsed:
        return answer_text

    dataframe = pd.DataFrame(parsed["rows"])
    if output_mode == "html":
        return dataframe.to_html(index=False)
    return dataframe.to_markdown(index=False)


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    session_id = cl.user_session.get("id") or generate_session_id()
    cl.user_session.set("id", session_id)
    cl.user_session.set("thread_id", thread.get("id"))
    cl.user_session.set("conversation_state", "WAITING_FOR_INPUT")
    cl.user_session.set("message_history", _restore_message_history(thread))
    await cl.Message(f"Welcome back!How can I assist you?").send()


@cl.on_chat_start
async def on_chat_start():
    session_id = generate_session_id()
    thread_id = chainlit_context.session.thread_id
    cl.user_session.set("id", session_id)
    cl.user_session.set("conversation_state", "WAITING_FOR_INPUT")
    cl.user_session.set("model", "mixtral-8x7b-32768")
    cl.user_session.set("vectordb", "Opensearch")
    system_message = _system_message()
    cl.user_session.set("message_history", [system_message])
    cl.user_session.set("thread_id", thread_id)
    thread_store.ensure_thread(
        thread_id=thread_id,
        user_id="admin",
        user_identifier="admin",
        name="New chat",
        metadata={"session_id": session_id},
    )
    greeting = "Hello! I'm Insura, your personal insurance assistant. How can I help you today with any questions about your policy, claims, or coverage?"
    thread_store.save_message(
        thread_id=thread_id,
        role="assistant",
        content=greeting,
        user_id="admin",
        user_identifier="admin",
        thread_name="New chat",
    )
    await cl.Message(content=greeting).send()
    
    async def send_message_with_delay(message):
        await cl.Message(message,disable_feedback= True).send()
        await asyncio.sleep(5)  # Adjust the delay time as needed
  
    @cl.on_message  # this function will be called every time a user inputs a message in the UI
    async def main(message: cl.Message):
        start = time.time()
        session_id = cl.user_session.get("id") or generate_session_id()
        cl.user_session.set("id", session_id)
        thread_id = cl.user_session.get("thread_id") or chainlit_context.session.thread_id
        conversation_state = cl.user_session.get("conversation_state", "WAITING_FOR_INPUT")
        LOGGER.info("Handling user message session_id=%s thread_id=%s", session_id, thread_id)

        def instruction_format(messages: list,sys_msg:str, query: str):
            return f'<s> [INST] {messages} {sys_msg}[/INST]\nUser: {query}\nAgent: ```json </s>'
        
        def instruction_format_groq(messages: list,sys_msg: str):
            return f'<s> [INST] {messages}{sys_msg} ```json </s>'
        
        def format_state(query: str,state:str):
            return f'<s> [INST] {query}[/INST]\ for state {state} ```json </s>'

        # def instruction_format(sys_message: str, query: str, applicationname: str):
        #     return f'<s> [INST] {sys_message} [/INST]\nUser: {query}{applicationname}\nAgent: ```json </s>'

        def retrieve_query():
            try:
                result = classify_tool(groq_input, query)
                LOGGER.info("Tool classification raw_result=%s", result)
                return result

            except Exception as e:
                LOGGER.exception("Tool classification failed")
            
        def process_tools(response_data):
            start_index = response_data.find('{')
            end_index = response_data.find('}')
            json_str = response_data[start_index:end_index + 1]
            response_dict = json.loads(json_str)
            return response_dict

        def parse_retrieval_queries(raw_response: str, fallback_query: str):
            try:
                processed = process_tools(raw_response)
                queries = processed.get("query")
                if isinstance(queries, list) and queries:
                    return queries
            except Exception as exc:
                logging.warning("Failed to parse retrieval queries, using fallback query: %s", exc)
            return [fallback_query]
        
        async def opensearch_retrieve(issue_query):
        
            url = f"{RAG_API_URL}/SFRAG/retrieval"
            headers = {
                        "Content-Type": "application/json"   
                        }

            body = {
                    "user_query": issue_query,
                    "index_name": RAG_INDEX_NAME,
                    "session_id": session_id
                    }
            LOGGER.info("Calling retrieval API index_name=%s query=%s", RAG_INDEX_NAME, issue_query)
            # Use aiohttp for async requests
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as response:
                    response_text = await response.text()
                    LOGGER.info("Retrieval API status=%s", response.status)
                    return json.loads(response_text)

        def process_tools(response_data):
            start_index = response_data.find('{')
            end_index = response_data.find('}')
            json_str = response_data[start_index:end_index + 1]
            response_dict = json.loads(json_str)
            return response_dict

        def retrieve_toolsgpt():
            return {"tool": "General", "input": "Sorry, I am a Technical support assistant. I don't have the information on this."}

        def looks_like_document_question(user_query: str) -> bool:
            lowered_query = user_query.lower()
            return any(keyword in lowered_query for keyword in DOCUMENT_QUERY_HINTS)

        state_list=['nevada','pennsylvania','maryland','minnesota']


        if not message.elements:
            if conversation_state == "WAITING_FOR_INPUT":
                
                query = message.content
                thread_store.save_message(
                    thread_id=thread_id,
                    role="user",
                    content=query,
                    user_id="admin",
                    user_identifier="admin",
                    thread_name=query[:80],
                )
                thread_store.ensure_thread(
                    thread_id=thread_id,
                    user_id="admin",
                    user_identifier="admin",
                    name=query[:80],
                    metadata={"session_id": session_id},
                )
                
                # add_chat=add_message(session_id,"user",query)
                messages = _get_message_history()
                # messages = cl.user_session.get("message_history")
                # print("first:",messages)
                # logging.info(f"first: {messages}")
                
                messages.append({"role": "user", "content": message.content})
                # print("second:",messages)
                # logging.info(f"second: {messages}")
                input_prompt = instruction_format(messages,sys_msg,query)
                groq_input=instruction_format_groq(messages,sys_msg)
                
                retries = 0
                while retries < 5:
                    try:
                        response_data=await cl.make_async(retrieve_query)()
                        
                        break  
                    except Exception as e:
                        LOGGER.exception("Tool retrieval async attempt failed")
                        retries += 1
                        if retries >= 4:
                            await asyncio.sleep(5)
                            LOGGER.warning("Maximum tool retrieval retry attempts reached")
                            response_data=await cl.make_async(retrieve_toolsgpt)()
                            
                            
                        else:
                            LOGGER.info("Retrying tool retrieval")
                

                dict_res=process_tools(response_data)
                tool = dict_res["tool"]
                input_value = dict_res["input"]
                cl.user_session.set("tool", tool)
                cl.user_session.set("input_value", input_value)

                if tool == "General" and looks_like_document_question(query):
                    tool = "Issue"
                    input_value = query
                    cl.user_session.set("tool", tool)
                    cl.user_session.set("input_value", input_value)

                LOGGER.info("Resolved tool=%s input=%s", tool, input_value)
                if tool ==  "Issue":
                    initial_time=time.time()
                    retrieval_start=time.time()
                    states_input=input_value.lower()
                    unique_pdf_url=[]
                    
                    # for state in state_list:
                    #     print(state)
                    #     if state in states_input:
                    # Check if any state in the state_list is present in the input
                    matched_state = next((state for state in state_list if state in states_input), None)
                    dec_dict={}
                    if matched_state:
                        LOGGER.info("Matched state in query state=%s", matched_state)
                        initial_message = cl.Message(content="")
                        await initial_message.send()
                        await initial_message.update()
                        m_queries_process=await modified_retrieval_query(input_value)
                        m_query=parse_retrieval_queries(m_queries_process, input_value)
                        LOGGER.info("Modified decomposed query count=%s", len(m_query))
                        decomposed_res = await asyncio.gather(
                            *(opensearch_retrieve(sub_query) for sub_query in m_query)
                        )
                        for sub_query, res in zip(m_query, decomposed_res):
                            dec_dict[sub_query] = res["response"]["content"]

                        original_question=input_value

                    else:
                        initial_message = cl.Message(content="")
                        await initial_message.send()
                        await initial_message.update()
                        m_queries_process=await modified_retrieval_query(input_value)
                        m_query=parse_retrieval_queries(m_queries_process, input_value)
                        LOGGER.info("Modified decomposed query count=%s", len(m_query))
                        decomposed_res = await asyncio.gather(
                            *(opensearch_retrieve(sub_query) for sub_query in m_query)
                        )
                        for sub_query, res in zip(m_query, decomposed_res):
                            dec_dict[sub_query] = res["response"]["content"]
                        original_question=input_value
                    retrieval_end=time.time()
                    LOGGER.info("Prepared decomposition dictionary keys=%s", list(dec_dict.keys()))
                    if len(decomposed_res)>1:
                        LOGGER.info("Multiple retrieval results found count=%s", len(decomposed_res))
                        combined_citations = []
                        for response in decomposed_res:
                            combined_citations.extend(response["citation"])
                            
                        final=await generate_answer(dec_dict,original_question)
                        LOGGER.info("Generated combined answer chars=%s", len(final))
                        LOGGER.info("Original question=%s", original_question)
                        messages.append({"role": "Agent", "content": final})
                        cl.user_session.set("message_history", messages)

                        if _is_table_request(original_question):
                            LOGGER.info("Rendering tabular response")
                            markdown_table = _format_structured_answer(final, "markdown")
                            if markdown_table == final:
                                LOGGER.warning("Could not convert tabular response to dataframe")
                            await initial_message.remove()
                            await cl.Message(content=markdown_table).send()

                        elif _is_html_request(original_question):
                            LOGGER.info("Rendering HTML response")
                            html_content = _format_structured_answer(final, "html")
                            if html_content == final:
                                LOGGER.warning("Could not convert HTML response to dataframe")
                            
                            await initial_message.remove()
                            await cl.Message(content=html_content).send()

                        else:
                            LOGGER.info("Rendering streamed text response")
                            words =final.split(" ")  # Split the content into words
                            for word in words:
                                await initial_message.stream_token(word + " ")
                                
                            # Final message update after streaming
                            initial_message.content=final
                            await initial_message.update()

                        final_time=time.time()
                        
                        total_retrieval_time=retrieval_end-retrieval_start
                        minuteso = int(total_retrieval_time // 60)
                        secondso = int(total_retrieval_time % 60)
                        # Format the time as "Xmin Ysec"
                        re_timet = f"{minuteso}min {secondso}sec"
                        time_taken=final_time-initial_time
                        minutesC = int(time_taken // 60)
                        secondsC = int(time_taken % 60)
                        # Format the time as "Xmin Ysec"
                        final_timet = f"{minutesC}min {secondsC}sec"
                        await cl.Message(content=f"Response time:{final_timet} and Retrieval time:{re_timet}").send()
                        # combined_citations
                        # Lists to store .png URLs and pdf URLs
                        png_urls = []
                        pdf_urls = []
                        
                        # Loop through each item in citations
                        for citation in combined_citations:
                            # Add all .png URLs from the 'url' list
                            png_urls.extend([url for url in citation['url'] if url.endswith('.png')])
                            
                            # Add the 'pdf_url' to pdf_urls
                            pdf_urls.append(citation['pdf_url'])

                        unique_pdf_urls = list(set(pdf_urls))

                        
                        actions = []

                        # Create actions with serial numbers and corresponding PDF links
                        for index, pdf_url in enumerate(unique_pdf_urls, start=1):
                            # Extract the file name from the URL for the hover tooltip
                            file_name = pdf_url.split("/")[-1]
                            
                            # Create an action with a serial number, and associate it with the 'pdf_action' callback
                            actions.append(
                                cl.Action(
                                    name="pdf_action",  # Associate with 'pdf_action' callback
                                    value=pdf_url,
                                    label=f"{index}",    # Serial number as the action value
                                    description=f"{file_name}"  # Tooltip with file name
                                )
                            )

                        # Send message with all actions (buttons for each PDF)
                        await cl.Message(content=" Pdf_document_Citations:", actions=actions).send()

                        page_actions=[]
                        # Create actions for only unique PDF URLs
                        for index, image_url in enumerate(png_urls, start=1):
                            # Extract the file name from the URL for the hover tooltip
                            ifile_name = image_url.split("/")[-1]
                            
                            # Create an action with a serial number, and associate it with the 'pdf_action' callback
                            page_actions.append(
                                cl.Action(
                                    name="png_action",  # Associate with 'pdf_action' callback
                                    value=image_url,
                                    label=f"{index}",    # Label with serial number
                                    description=f"{ifile_name}"  # Tooltip with file name
                                )
                            )
                        # Send message with all actions (buttons for each PDF)
                        await cl.Message(content="\n Image Citations:", actions=page_actions).send()


                    else:
                        res=decomposed_res[0]
                        stream=res["response"]["content"]
                        rendered_output = stream
                        if _is_table_request(original_question):
                            LOGGER.info("Rendering single-result tabular response")
                            rendered_output = _format_structured_answer(stream, "markdown")
                        elif _is_html_request(original_question):
                            LOGGER.info("Rendering single-result HTML response")
                            rendered_output = _format_structured_answer(stream, "html")

                        messages.append({"role": "Agent", "content": rendered_output})
                        cl.user_session.set("message_history", messages)
                        LOGGER.info("Single retrieval response chars=%s", len(rendered_output))
                        if rendered_output != stream and (_is_table_request(original_question) or _is_html_request(original_question)):
                            await initial_message.remove()
                            await cl.Message(content=rendered_output).send()
                        else:
                            words = rendered_output.split(" ")
                            for word in words:
                                await initial_message.stream_token(word + " ")
                            initial_message.content = rendered_output
                            await initial_message.update()

                        retrieval_end=time.time()
                        total_retrieval_time=retrieval_end-retrieval_start
                        minuteso = int(total_retrieval_time // 60)
                        secondso = int(total_retrieval_time % 60)
                        # Format the time as "Xmin Ysec"
                        re_timet = f"{minuteso}min {secondso}sec"
                        
                        final_time=time.time()
                        pdf_url = res["citation"][0]["pdf_url"]
                        unique_pdf_url.append(pdf_url)
                        
                        png_urls = [url for url in res['citation'][0]['url'] if url.endswith('.png')]
                        
                        time_taken=final_time-initial_time
                        minutesC = int(time_taken // 60)
                        secondsC = int(time_taken % 60)
                        # Format the time as "Xmin Ysec"
                        final_timet = f"{minutesC}min {secondsC}sec"
                        await cl.Message(content=f"Response time:{final_timet} and Retrieval time:{re_timet}").send()
                        unique_pdf_urls = list(set(unique_pdf_url))

                        
                        actions = []

                        # Create actions with serial numbers and corresponding PDF links
                        for index, pdf_url in enumerate(unique_pdf_urls, start=1):
                            # Extract the file name from the URL for the hover tooltip
                            file_name = pdf_url.split("/")[-1]
                            
                            # Create an action with a serial number, and associate it with the 'pdf_action' callback
                            actions.append(
                                cl.Action(
                                    name="pdf_action",  # Associate with 'pdf_action' callback
                                    value=pdf_url,
                                    label=f"{index}",    # Serial number as the action value
                                    description=f"{file_name}"  # Tooltip with file name
                                )
                            )

                        # Send message with all actions (buttons for each PDF)
                        await cl.Message(content=" Pdf_document_Citations:", actions=actions).send()

                        page_actions=[]
                        # Create actions for only unique PDF URLs
                        for index, image_url in enumerate(png_urls, start=1):
                            # Extract the file name from the URL for the hover tooltip
                            ifile_name = image_url.split("/")[-1]
                            
                            # Create an action with a serial number, and associate it with the 'pdf_action' callback
                            page_actions.append(
                                cl.Action(
                                    name="png_action",  # Associate with 'pdf_action' callback
                                    value=image_url,
                                    label=f"{index}",    # Label with serial number
                                    description=f"{ifile_name}"  # Tooltip with file name
                                )
                            )
                        # Send message with all actions (buttons for each PDF)
                        await cl.Message(content="\n Image Citations:", actions=page_actions).send()
         
                elif tool=='Greeting':
                    await cl.Message(content=input_value).send()
                    messages.append({"role": "Agent", "content": input_value})
                    cl.user_session.set("message_history", messages)

                elif tool=='Acknowledge':
                    await cl.Message(content=input_value).send()
                    messages.append({"role": "Agent", "content": input_value})
                    cl.user_session.set("message_history", messages)

                elif tool=='End':
                    await cl.Message(content=input_value).send()
                    messages.append({"role": "Agent", "content": input_value})
                    cl.user_session.set("message_history", messages)

                elif tool=='General':
                    await cl.Message(content=input_value).send()
                    messages.append({"role": "Agent", "content": input_value})
                    cl.user_session.set("message_history", messages)

                else:
                    await cl.Message(content=f'{input_value}').send()
                    messages.append({"role": "Agent", "content": input_value})
                    cl.user_session.set("message_history", messages)
                    LOGGER.info("Fallback tool response sent")


        image_start=time.time()
        # Processing images exclusively
        images = [file for file in message.elements if "image" in file.mime]

        # Function to encode the image
        def encode_image(image_path):
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')

        unique_pdf_urls=[]

        # Path to your image
        for image in images:
            # Getting the base64 string
            base64_image = encode_image(image.path)
            # Fix: Await the image_process function
            output1 = await image_process(base64_image) # Await async function
            output=process_tools(output1)
            classification=output["classification"]
            LOGGER.info("Image classification=%s", classification)
            image_query=output["resolution_query"]
            LOGGER.info("Image resolution query=%s", image_query)
            retrieval_image=time.time()
            msg = cl.Message(content="")
            await msg.send()
            await msg.update()

            res=await opensearch_retrieve(image_query)
            # Stream response from res["content"]
            if "response" in res:
                for token in res["response"]["content"]:
                    await msg.stream_token(token)
                    
            # Final message update after streaming
            msg.content=res["response"]["content"]
            await msg.update()
            image_history = _get_message_history()
            image_history.append({"role": "Agent", "content": res["response"]["content"]})
            cl.user_session.set("message_history", image_history)
            #citation

            # # Extract pdf_url values
            pdf_url = res["citation"][0]["pdf_url"]
            unique_pdf_urls.append(pdf_url)

            # Extract all .png URLs
            png_urls = [url for url in res['citation'][0]['url'] if url.endswith('.png')]

            retrieval_end_image=time.time()
            image_end=time.time()
            all_retrieval_time=retrieval_end_image-retrieval_image
            min = int(all_retrieval_time // 60)
            sec = int(all_retrieval_time % 60)
            # Format the time as "Xmin Ysec"
            total_retrieve = f"{min}min {sec}sec"
            all_image_time=image_end-image_start
            
            # await cl.Message(content=image_ans).send()

            unique_pdf_urls = list(set(unique_pdf_urls))
            LOGGER.info("Image retrieval citations pdf_count=%s", len(unique_pdf_urls))
            
            mini = int(all_image_time // 60)
            seci = int(all_image_time % 60)
            # Format the time as "Xmin Ysec"
            all_image = f"{mini}min {seci}sec"
            await cl.Message(content=f"Response time:{all_image} and Retrieval time:{total_retrieve}").send()

            actions = []

            # Create actions with serial numbers and corresponding PDF links
            for index, pdf_url in enumerate(unique_pdf_urls, start=1):
                # Extract the file name from the URL for the hover tooltip
                file_name = pdf_url.split("/")[-1]
                
                # Create an action with a serial number, and associate it with the 'pdf_action' callback
                actions.append(
                    cl.Action(
                        name="pdf_action",  # Associate with 'pdf_action' callback
                        value=pdf_url,
                        label=f"{index}",    # Serial number as the action value
                        description=f"{file_name}"  # Tooltip with file name
                    )
                )

            # Send message with all actions (buttons for each PDF)
            await cl.Message(content="Pdf_Citations:", actions=actions).send()

            page_actions=[]
            # Create actions for only unique PDF URLs
            for index, image_url in enumerate(png_urls, start=1):
                # Extract the file name from the URL for the hover tooltip
                ifile_name = image_url.split("/")[-1]
                
                # Create an action with a serial number, and associate it with the 'pdf_action' callback
                page_actions.append(
                    cl.Action(
                        name="png_action",  # Associate with 'pdf_action' callback
                        value=image_url,
                        label=f"{index}",    # Label with serial number
                        description=f"{ifile_name}"  # Tooltip with file name
                    )
                )
            # Send message with all actions (buttons for each PDF)
            await cl.Message(content="\n Image Citations:", actions=page_actions).send()
