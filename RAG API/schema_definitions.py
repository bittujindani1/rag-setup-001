

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator
from typing import Optional
import datetime


from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# assistant_id is pk
class AssistantData(BaseModel):
    retrieval_method: Optional[str] = None
    assistant_name: Optional[str] = None
    assistant_desc: Optional[str] = None
    assistant_image_url: Optional[str] = None
    language: Optional[str] = None
    project_name: Optional[str] = None
    retrieval_llm_model: Optional[str] = None
    prev_messages_window: Optional[int] = None
    max_waiting_period: Optional[int] = None
    similarity_threshold: Optional[float] = None
    vector_similarity_weight: Optional[float] = None
    top_k_chunks: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    sources_list: Optional[str] = None
    max_retries: Optional[int] = None
    fallback_response: Optional[str] = None
    system_prompt: Optional[str] = None
    response_style: Optional[str] = None
    opening_dialogue: Optional[str] = None
    conversational: Optional[bool] = None
    citations: Optional[bool] = None
    use_cache: Optional[bool] = None
    streaming: Optional[bool] = None
    text_to_speech: Optional[bool] = None
    allow_multimodal_input: Optional[bool] = None
    pii_masking: Optional[bool] = None
    pricing: Optional[bool] = None
    toxic_queries_flag: Optional[bool] = None
    project_ingest_method: Optional[str] = None
    project_embed_model: Optional[str] = None
    project_vector_store: Optional[str] = None
    project_db_url: Optional[str] = None
    project_db_username: Optional[str] = None
    project_db_password: Optional[str] = None
    project_type: Optional[str] = None
    project_specifics: Optional[str] = None
    evaluation: Optional[bool] = None
    evaluation_method: Optional[str] = None
    #creationdate: Optional[datetime] = Field(default_factory=datetime.utcnow)
    #modifieddate: Optional[datetime] = None
    no_of_chat_sessions: Optional[int] = 0  # Default value is 0
    userdetails : Optional[str] = None
    role_level : Optional[str] = None


    class Config:
        orm_mode = True
        extra = "forbid"  # Forbid extra fields





#chat_id is pk

# Define the Pydantic model for ChatData
class ChatData(BaseModel):
    assistant_id: str
    chat_name: Optional[str] = None
    feedback_counter: Optional[int] = 0
    conversation_count: Optional[int] = 0
    sentiment_analysis: Optional[int] = 0
    accuracy: Optional[float] = None
    userdetails: Optional[str] = None
    role_level: Optional[str] = None

    class Config:
        orm_mode = True
        extra = "forbid"  # Forbid extra fields


from pydantic import BaseModel, Field
from typing import Optional


class ConversationData(BaseModel):
    chat_id: str
    query: Optional[str] = None
    response: Optional[str] = None
    citation_url: Optional[str] = None
    time_of_query: Optional[str] = None  # Adjust to datetime if needed
    response_time: Optional[str] = None  # Adjust to time if needed
    feedback_comments: Optional[str] = None
    voted: Optional[bool] = None
    evaluation_score: Optional[float] = None
    pricing: Optional[float] = None
    userdetails: Optional[str] = None
    role_level: Optional[str] = None
    multimodal_Input: Optional[bool] = Field(alias="multimodal_Input", default=None)
    multimodal_url_list: Optional[str] = None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

