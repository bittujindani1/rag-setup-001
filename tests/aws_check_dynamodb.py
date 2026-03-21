import sys
import time
import uuid

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError
from langchain_core.messages import AIMessage, HumanMessage

from aws.cache_manager import DynamoDBCacheManager
from aws.dynamodb_store import DynamoDBChatMessageHistory, DynamoDBDocStore, DynamoDBFilenameIndex
from aws.metrics import MetricsCollector
from aws.rate_limiter import DynamoDBRateLimiter
from config_loader import load_app_config


def main() -> int:
    config = load_app_config()
    region = config["aws_region"]
    table_map = {
        "chat_history": config["dynamodb_chat_history_table"],
        "query_cache": config["dynamodb_query_cache_table"],
        "doc_store": config["dynamodb_doc_store_table"],
        "filename_index": config["dynamodb_filename_index_table"],
        "rate_limit": config["dynamodb_rate_limit_table"],
    }

    client = boto3.client("dynamodb", region_name=region)
    resource = boto3.resource("dynamodb", region_name=region)
    suffix = uuid.uuid4().hex[:8]

    try:
        for label, table_name in table_map.items():
            client.describe_table(TableName=table_name)
            print(f"DynamoDB table OK: {label} -> {table_name}")

        doc_store = DynamoDBDocStore(table_map["doc_store"], region)
        doc_id = f"service-check-doc-{suffix}"
        doc_store.mset([(doc_id, "travel insurance covers trip cancellation")])
        assert doc_store.mget([doc_id]) == ["travel insurance covers trip cancellation"]
        doc_store.delete(doc_id)
        assert doc_store.mget([doc_id]) == [None]
        print("DynamoDB doc store OK")

        filename_index = DynamoDBFilenameIndex(table_map["filename_index"], region)
        index_name = f"service-check-index-{suffix}"
        filename = f"service-check-{suffix}.pdf"
        expected_doc_ids = [f"doc-a-{suffix}", f"doc-b-{suffix}"]
        filename_index.add_doc_ids(index_name, filename, expected_doc_ids)
        assert filename in filename_index.list_filenames(index_name)
        assert filename_index.get_doc_ids(index_name, filename) == expected_doc_ids
        filename_index.delete(index_name, filename)
        assert filename_index.get_doc_ids(index_name, filename) == []
        print("DynamoDB filename index OK")

        cache = DynamoDBCacheManager(
            table_map["query_cache"],
            region,
            ttl_seconds=300,
            metrics_collector=MetricsCollector(),
        )
        cache_key = cache.build_cache_key(
            query="what is covered?",
            retrieval_k=5,
            index_name="service-check",
            model_name=suffix,
        )
        assert cache.get(cache_key) is None
        cache.set(cache_key, {"answer": "Trip delay"})
        assert cache.get(cache_key) == {"answer": "Trip delay"}
        resource.Table(table_map["query_cache"]).delete_item(Key={"query_hash": cache_key})
        print("DynamoDB query cache OK")

        history = DynamoDBChatMessageHistory(table_map["chat_history"], f"service-check-{suffix}", region)
        history.add_messages([HumanMessage(content="hello"), AIMessage(content="hi there")])
        messages = history.messages
        assert len(messages) >= 2
        history.clear()
        assert history.messages == []
        print("DynamoDB chat history OK")

        limiter = DynamoDBRateLimiter(table_map["rate_limit"], region, limit_per_minute=2)
        session_id = f"service-check-rate-{suffix}"
        allowed_one, count_one = limiter.check_and_record(session_id)
        allowed_two, count_two = limiter.check_and_record(session_id)
        allowed_three, count_three = limiter.check_and_record(session_id)
        assert allowed_one and count_one == 1
        assert allowed_two and count_two == 2
        assert not allowed_three and count_three == 2
        rate_table = resource.Table(table_map["rate_limit"])
        response = rate_table.query(
            KeyConditionExpression=Key("session_id").eq(session_id)
        )
        with rate_table.batch_writer() as batch:
            for item in response.get("Items", []):
                batch.delete_item(
                    Key={
                        "session_id": item["session_id"],
                        "request_id": item["request_id"],
                    }
                )
        print("DynamoDB rate limiter OK")
        return 0
    except (AssertionError, BotoCoreError, ClientError, KeyError) as exc:
        print(f"DynamoDB validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
