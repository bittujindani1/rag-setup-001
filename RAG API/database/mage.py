import datetime
import requests
from pydantic import BaseModel
import logging


REDIS_QUEUE_NAME = "RAGSTUDIO"


from env_bootstrap import bootstrap_env

bootstrap_env()



MAGE_EXCHANGE_UPDATE="https://mage.htcnxt.ai:8080/platform/dataexchange/update/job-status/"
MAGE_HOST_ENQUEUE="https://mage.htcnxt.ai:8080/platform/databasecrud/redis/enqueue"



class Job(BaseModel):
    job_id: str
    channel_name: str
    method_name: str
    project_name: str
    task: str
    arguments: dict


class Payload(BaseModel):
    message: Job



import datetime

# Generate a unique assistant_id using the current date, time
def generate_id(name: str) -> str:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    return f"{name}_{timestamp}"

from database.sql_utils import perform_sql_insert

def enqueue_job(project_name, function_name, task, args):
    """Enqueues a job with a unique ID and sends it to the queue."""
    job_id = generate_id("File")
    job_args = Job(
        job_id=job_id,
        channel_name=REDIS_QUEUE_NAME,
        method_name=function_name,
        project_name=project_name,
        task=task,
        arguments=args.dict()
    )
    print("job_args", job_args)

    full_payload = Payload(message=job_args)
    
    SQL_SERVER= "usecasesdata.database.windows.net"
    SQL_DATABASE="usecasesdata"


    sql_data = {
        "file_id": job_id,
        "filename": None,  # Replace with actual filename if available
        "file_size": None,
        "chunk_number": None,
        "no_of_pages": None,
        "image_no": None,
        "table_no": None,
        "status": "Queued",
        "source": args.source,
        "type": None,
        "role": args.role,
        "url": None,
        "message": None,
        "embedding_dimension_size": None,
        "project_id": args.project_id,
        "length": None,
        "extracted_images_url_list": None,
        "extracted_table_url_list": None,
        "time_taken": None,
        "pricing": None,
        "total_prompt_tokens": None,
        "total_completion_tokens": None,
    }
    try:
        schema = "rag"
        TableName = "files"
        perform_sql_insert(
            server=SQL_SERVER,
            charset="utf8",
            database=SQL_DATABASE,
            schema_=schema,
            TableName=TableName,
            data_to_insert=sql_data
        )
    except Exception as e:

        raise HTTPException(status_code=400, detail=f"SQL insert failed: {str(e)}")    


    try:
        response = requests.post(url=MAGE_HOST_ENQUEUE, json=full_payload.dict())
        return response.json()
    except Exception as e:
        raise e

import json
def update_job_status(job_id, status, task, project):
    MAGE_EXCHANGE_URL = MAGE_EXCHANGE_UPDATE
    payload = json.dumps(
        {"job_id": job_id, "job_status": status, "stream": REDIS_QUEUE_NAME, "task": task, "project": project}
    )
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    try:

        resp = requests.post(MAGE_EXCHANGE_URL, headers=headers, data=payload)
    except Exception as e:
        raise e
