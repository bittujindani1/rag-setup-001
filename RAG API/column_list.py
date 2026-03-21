
ASSISTANT_COLUMN_NAMES = [
    'assistant_id',
    'retrieval_method',
    'assistant_name',
    'assistant_desc',
    'assistant_image_url',
    'language',
    'project_name',
    'retrieval_llm_model',
    'prev_messages_window',
    'max_waiting_period',
    'similarity_threshold',
    'vector_similarity_weight',
    'top_k_chunks',
    'max_tokens',
    'temperature',
    'sources_list',
    'max_retries',
    'fallback_response',
    'system_prompt',
    'response_style',
    'opening_dialogue',
    'conversational',
    'citations',
    'use_cache',
    'streaming',
    'text_to_speech',
    'allow_multimodal_input',
    'pii_masking',
    'pricing',
    'toxic_queries_flag',
    'project_ingest_method',
    'project_embed_model',
    'project_vector_store',
    'project_db_url',
    'project_db_username',
    'project_db_password',
    'project_type',
    'project_specifics',
    'evaluation',
    'evaluation_method',
    'creationdate',
    'modifieddate',
    'no_of_chat_sessions',
    'userdetails',
    'role_level'
]





# List of columns to fetch
COLUMNS_FOR_ASSISTANT_DASHBOARD = [
    'assistant_id',
    'assistant_name',
    'assistant_desc',
    'assistant_image_url',
    'creationdate',
    'modifieddate',
    'no_of_chat_sessions',
    'userdetails',
    'role_level'      
]

COLUMNS_FOR_CHAT_DASHBOARD = [
    "chat_id", "assistant_id", "chat_name", "feedback_counter",
    "conversation_count", "sentiment_analysis", "accuracy",
    "created_date", "modified_date", "userdetails", "role_level"
]

# Define columns for the Conversation table
COLUMNS_FOR_CONVERSATION = [
    "conversation_id", "chat_id", "query", "response", "citation_url", "time_of_query",
    "response_time", "feedback_comments", "voted", "evaluation_score", "pricing",
    "userdetails", "role_level", "multimodal_Input", "multimodal_url_list", "creation_date"
]