import os
import sys
import urllib
from pathlib import Path
from requests_aws4auth import AWS4Auth
from langchain_community.vectorstores import OpenSearchVectorSearch
from opensearchpy import OpenSearch, RequestsHttpConnection
from langchain_community.utilities.redis import get_client
from opensearchpy import OpenSearch, RequestsHttpConnection, helpers
from langchain_openai import AzureOpenAIEmbeddings

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from env_bootstrap import bootstrap_env
from provider_factory import get_config, get_filename_index, get_s3_vector_store
bootstrap_env(Path(__file__).resolve().with_name(".env"))


AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_SERVICE = os.getenv("AWS_SERVICE")

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL")

REDIS_PASSWORD  = os.getenv("REDIS_PASSWORD")
REDIS_HOST  = os.getenv("REDIS_HOST")

REDIS_PORT = os.getenv("REDIS_PORT")
redis_url = None
if REDIS_PASSWORD and REDIS_HOST and REDIS_PORT:
    encoded_password = urllib.parse.quote(REDIS_PASSWORD)
    redis_url = f"redis://:{encoded_password}@{REDIS_HOST}:{REDIS_PORT}"

awsauth = None
if AWS_ACCESS_KEY and AWS_SECRET_KEY and AWS_REGION and AWS_SERVICE:
    awsauth = AWS4Auth(AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, AWS_SERVICE)


api_key = os.getenv("AZURE_OPENAI_API_KEY_EMBEDDINGS")
azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_version = os.getenv("AZURE_API_VERSION")
embedding_function = None
if api_key and azure_endpoint and api_version:
    os.environ["AZURE_OPENAI_API_KEY_EMBEDDINGS"] = api_key
    embedding_function = AzureOpenAIEmbeddings(
        azure_deployment="text-embedding-ada-002",
        openai_api_version=api_version,
        azure_endpoint=azure_endpoint,
    )


def get_vectorstore(index_name):
    config = get_config()
    if config.get("vector_store") == "s3":
        return get_s3_vector_store(index_name)

    print("Getting vectorstore for index", index_name)
    print("embd function====",embedding_function,"opensearch url===",OPENSEARCH_URL,"http_auth==",awsauth)
    print(azure_endpoint,"azure endpoint")
    print(api_version,"open ai version")
    print("azure openai api key",api_key)

    return OpenSearchVectorSearch(
        index_name=index_name,
        embedding_function=embedding_function,
        opensearch_url=OPENSEARCH_URL,
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300,
        max_retries=3,
        retry_on_timeout=True
    )




def create_index_if_not_exists(index_name):
    config = get_config()
    if config.get("vector_store") == "s3":
        return

    awsauth = AWS4Auth(AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, AWS_SERVICE)
    opensearch_host = OPENSEARCH_URL.split("//")[-1].split(":")[0]  
    
    opensearch_client = OpenSearch(
        hosts=[{'host': opensearch_host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300,  
        max_retries=3,
        retry_on_timeout=True
    )


    vector_field = "vector_field"
    dim = 1536  

    index_mapping = {
        "settings": {"index": {"knn": True, "knn.algo_param.ef_search": 512}},
        "mappings": {
            "properties": {
                "vector_field": {
                    "type": "knn_vector",
                    "dimension": 1536,
                    "method": {
                        "name": "hnsw",
                        "space_type": "l2",
                        "engine": "nmslib",
                        "parameters": {"ef_construction": 512, "m": 16},
                    },
                },
                "metadata": {
                    "properties": {
                        "filename": {"type": "keyword"},
                        "type": {"type": "keyword"},
                        "url": {"type": "keyword"},
                        "page_numbers": {"type": "keyword"}
                    }
                }
            }
        }
    }    

    # Create the index if it does not exist
    if not opensearch_client.indices.exists(index=index_name):
        opensearch_client.indices.create(index=index_name, body=index_mapping)
        print(f"Index '{index_name}' created successfully.")
    else:
        print(f"Index '{index_name}' already exists.")

    # Verify the mapping
    mapping = opensearch_client.indices.get_mapping(index=index_name)
    print("Index mapping:", mapping)





def list_all_filenames_in_index(index_name):
    config = get_config()
    if config.get("vector_store") == "s3":
        return get_filename_index().list_filenames(index_name)

    if not redis_url:
        return []
    client = get_client(redis_url)

    pattern = f"{index_name}:filename:*"

    filename_keys = client.keys(pattern)

    filenames = [key.decode('utf-8').split(f"{index_name}:filename:")[-1] for key in filename_keys]

    print(filenames)

    return filenames


def delete_documents_by_filename(index_name, filename):
    config = get_config()
    if config.get("vector_store") == "s3":
        vectorstore = get_s3_vector_store(index_name)
        vectorstore.delete_documents_by_filename(filename)
        filename_index = get_filename_index()
        for doc_id in filename_index.get_doc_ids(index_name, filename):
            try:
                from provider_factory import get_doc_store

                get_doc_store().delete(doc_id)
            except Exception:
                continue
        filename_index.delete(index_name, filename)
        return

    if not awsauth or not redis_url or not OPENSEARCH_URL:
        return
    opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_URL.split("//")[-1].split(":")[0], 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300,
        max_retries=3,
        retry_on_timeout=True
    )

    client = get_client(redis_url)

    query = {
        "query": {
            "term": {
                "metadata.filename": filename  
            }
        }
    }


    response = opensearch_client.search(index=index_name, body=query, size=1700)  
    opensearch_ids = [hit["_id"] for hit in response["hits"]["hits"]]
    print("opensearch_idsextracted", opensearch_ids)

    actions = [
        {"_op_type": "delete", "_index": index_name, "_id": doc_id}
        for doc_id in opensearch_ids
    ]

    if actions:
        success, errors = helpers.bulk(opensearch_client, actions, raise_on_error=False)

        real_errors = [error for error in errors if error.get("delete", {}).get("status") != 404]
        print(f"Bulk delete success count: {success}, failed count: {len(real_errors)}")
    else:
        print("No documents found for deletion in OpenSearch.")

    filename_key = f"{index_name}:filename:{filename}"

    custom_doc_ids = client.smembers(filename_key)
    print("Custom doc IDs in Redis for deletion:", custom_doc_ids)

    for custom_doc_id in custom_doc_ids:
        client.delete(custom_doc_id)  

    client.delete(filename_key)
    print(f"Deleted all entries in Redis for filename '{filename}'")











