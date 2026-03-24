from __future__ import annotations

import json
import logging
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict


LOGGER = logging.getLogger(__name__)


class DynamoDBDocStore:
    def __init__(self, table_name: str, region_name: str) -> None:
        self.region_name = region_name
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)
        self.client = boto3.client("dynamodb", region_name=region_name)

    def mset(self, pairs: Sequence[Tuple[str, str]]) -> None:
        with self.table.batch_writer() as batch:
            for doc_id, content in pairs:
                batch.put_item(Item={"doc_id": doc_id, "content": content})

    def mget(self, keys: Sequence[str]) -> List[Optional[str]]:
        if not keys:
            return []
        unique_keys = list(dict.fromkeys(keys))
        request_items = {
            self.table.name: {
                "Keys": [{"doc_id": {"S": key}} for key in unique_keys],
            }
        }
        response = self.client.batch_get_item(RequestItems=request_items)
        raw_items = response.get("Responses", {}).get(self.table.name, [])
        item_map = {
            item["doc_id"]["S"]: item.get("content", {}).get("S")
            for item in raw_items
            if "doc_id" in item
        }
        return [item_map.get(key) for key in keys]

    def delete(self, doc_id: str) -> None:
        self.table.delete_item(Key={"doc_id": doc_id})


class DynamoDBFilenameIndex:
    def __init__(self, table_name: str, region_name: str) -> None:
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def add_doc_ids(self, index_name: str, filename: str, doc_ids: Iterable[str]) -> None:
        self.table.put_item(
            Item={
                "index_filename": f"{index_name}#{filename}",
                "index_name": index_name,
                "doc_ids": list(doc_ids),
            }
        )

    def list_filenames(self, index_name: str) -> List[str]:
        try:
            response = self.table.query(
                IndexName="index_name-index",
                KeyConditionExpression=Key("index_name").eq(index_name),
                ProjectionExpression="index_filename",
            )
            items = response.get("Items", [])
        except ClientError:
            LOGGER.warning("index_name-index unavailable; falling back to scan for filename listing")
            response = self.table.scan(
                ProjectionExpression="index_filename",
                FilterExpression=Attr("index_filename").begins_with(f"{index_name}#"),
            )
            items = response.get("Items", [])
        return [item["index_filename"].split("#", 1)[1] for item in items]

    def get_doc_ids(self, index_name: str, filename: str) -> List[str]:
        item = self.table.get_item(Key={"index_filename": f"{index_name}#{filename}"}).get("Item")
        return item.get("doc_ids", []) if item else []

    def delete(self, index_name: str, filename: str) -> None:
        self.table.delete_item(Key={"index_filename": f"{index_name}#{filename}"})


class DynamoDBDocumentCategoryStore:
    def __init__(self, table_name: str, region_name: str) -> None:
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def upsert_document(
        self,
        *,
        index_name: str,
        filename: str,
        category: str,
        source_type: str,
        content_type: str,
        size_bytes: int,
        storage_url: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        item = {
            "index_filename": f"{index_name}#{filename}",
            "index_name": index_name,
            "filename": filename,
            "category": category,
            "source_type": source_type,
            "content_type": content_type,
            "size_bytes": int(size_bytes),
            "storage_url": storage_url,
            "updated_at": int(time.time()),
        }
        if metadata:
            item.update(metadata)
        self.table.put_item(
            Item=item
        )

    def delete_document(self, index_name: str, filename: str) -> None:
        self.table.delete_item(Key={"index_filename": f"{index_name}#{filename}"})

    def list_documents(self, index_name: str) -> List[Dict]:
        try:
            response = self.table.query(
                IndexName="index_name-index",
                KeyConditionExpression=Key("index_name").eq(index_name),
            )
            items = response.get("Items", [])
        except ClientError:
            LOGGER.warning("index_name-index unavailable for document categories; falling back to scan")
            response = self.table.scan(
                FilterExpression=Attr("index_name").eq(index_name),
            )
            items = response.get("Items", [])
        items.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
        return items

    def list_categories(self, index_name: str) -> List[Dict[str, int]]:
        category_counts: Dict[str, int] = {}
        for item in self.list_documents(index_name):
            category = item.get("category") or "uncategorized"
            category_counts[category] = category_counts.get(category, 0) + 1
        return [
            {"category": category, "count": count}
            for category, count in sorted(category_counts.items(), key=lambda item: item[0])
        ]

    def list_index_names(self) -> List[str]:
        items: List[Dict] = []
        scan_kwargs = {"ProjectionExpression": "index_name"}
        response = self.table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        while response.get("LastEvaluatedKey"):
            response = self.table.scan(ExclusiveStartKey=response["LastEvaluatedKey"], **scan_kwargs)
            items.extend(response.get("Items", []))
        return sorted(
            {
                str(item.get("index_name", "")).strip()
                for item in items
                if str(item.get("index_name", "")).strip()
            }
        )


class DynamoDBIngestJobStore:
    def __init__(self, table_name: str, region_name: str) -> None:
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def create_job(self, job_id: str, index_name: str, filename: str, source_type: str) -> Dict:
        item = {
            "job_id": job_id,
            "status": "queued",
            "index_name": index_name,
            "filename": filename,
            "source_type": source_type,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }
        self.table.put_item(Item=item)
        return item

    def update_job(self, job_id: str, **fields) -> Dict:
        item = self.get_job(job_id) or {"job_id": job_id}
        item.update(fields)
        item["updated_at"] = int(time.time())
        self.table.put_item(Item=item)
        return item

    def get_job(self, job_id: str) -> Optional[Dict]:
        response = self.table.get_item(Key={"job_id": job_id})
        return response.get("Item")


class DynamoDBFeedbackStore:
    def __init__(self, table_name: str, region_name: str) -> None:
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def create_feedback(self, *, user_id: str, workspace_id: str, feedback: str) -> Dict:
        timestamp = int(time.time() * 1000)
        item = {
            "user_id": user_id,
            "created_at": timestamp,
            "workspace_id": workspace_id,
            "feedback": feedback,
        }
        self.table.put_item(Item=item)
        return item


class DynamoDBChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, table_name: str, session_id: str, region_name: str) -> None:
        self.session_id = session_id
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    @property
    def messages(self) -> List[BaseMessage]:
        response = self.table.query(
            KeyConditionExpression=Key("session_id").eq(self.session_id),
            ScanIndexForward=False,
            Limit=6,
        )
        items = list(reversed(response.get("Items", [])))
        payload = [json.loads(item["message"]) for item in items if "message" in item]
        return messages_from_dict(payload)

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        now = int(time.time() * 1000)
        with self.table.batch_writer() as batch:
            for offset, message in enumerate(messages):
                batch.put_item(
                    Item={
                        "session_id": self.session_id,
                        "timestamp": now + offset,
                        "message": json.dumps(message_to_dict(message)),
                    }
                )

    def clear(self) -> None:
        response = self.table.query(
            KeyConditionExpression=Key("session_id").eq(self.session_id),
        )
        with self.table.batch_writer() as batch:
            for item in response.get("Items", []):
                batch.delete_item(
                    Key={
                        "session_id": item["session_id"],
                        "timestamp": item["timestamp"],
                    }
                )


class ConversationAuditStore:
    def __init__(self, table_name: str, region_name: str) -> None:
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def put_turn(
        self,
        session_id: str,
        timestamp: int,
        user_message: str,
        assistant_message: str,
    ) -> None:
        self.table.put_item(
            Item={
                "session_id": session_id,
                "timestamp": timestamp,
                "user_message": user_message,
                "assistant_message": assistant_message,
            }
        )
