from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
import logging
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from chainlit.data.base import BaseDataLayer
    from chainlit.element import ElementDict
    from chainlit.step import StepDict
    from chainlit.types import Feedback, PageInfo, PaginatedResponse, Pagination, ThreadDict, ThreadFilter
    from chainlit.user import PersistedUser, User
else:
    try:
        from chainlit.data.base import BaseDataLayer
        from chainlit.element import ElementDict
        from chainlit.step import StepDict
        from chainlit.types import Feedback, PageInfo, PaginatedResponse, Pagination, ThreadDict, ThreadFilter
        from chainlit.user import PersistedUser, User
    except ModuleNotFoundError:
        class StepDict(TypedDict, total=False):
            id: str
            threadId: str
            type: str
            name: str
            output: str
            input: str
            createdAt: str
            streaming: bool

        class ThreadDict(TypedDict, total=False):
            id: str
            createdAt: str
            updatedAt: str
            name: str
            userId: str
            userIdentifier: str
            tags: list
            metadata: dict
            steps: list
            elements: list

        class Feedback(TypedDict, total=False):
            id: str
            threadId: str
            forId: str

        class Pagination(TypedDict, total=False):
            first: int
            cursor: str | None

        class ThreadFilter(TypedDict, total=False):
            userId: str | None
            search: str | None

        class PageInfo(TypedDict, total=False):
            hasNextPage: bool
            startCursor: str | None
            endCursor: str | None

        class PaginatedResponse(dict):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)

        class PersistedUser(TypedDict, total=False):
            id: str
            identifier: str
            createdAt: str
            metadata: dict

        class User(TypedDict, total=False):
            identifier: str
            metadata: dict

        class ElementDict(TypedDict, total=False):
            id: str

        class BaseDataLayer:
            pass


LOGGER = logging.getLogger(__name__)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class DynamoDBThreadStore:
    def __init__(self, table_name: str, region_name: str) -> None:
        self.table_name = table_name
        self.region_name = region_name
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def _message_sort_key(self) -> str:
        return f"MSG#{int(time.time() * 1000)}#{uuid.uuid4().hex}"

    def _recent_duplicate_exists(self, thread_id: str, role: str, content: str) -> bool:
        response = self.table.query(
            KeyConditionExpression=Key("thread_id").eq(thread_id),
            ScanIndexForward=False,
            Limit=5,
        )
        for item in response.get("Items", []):
            if item.get("record_type") != "message":
                continue
            if item.get("role") == role and item.get("content") == content:
                return True
        return False

    def ensure_thread(
        self,
        thread_id: str,
        user_id: str,
        user_identifier: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        response = self.table.get_item(Key={"thread_id": thread_id, "timestamp": "THREAD"})
        existing = response.get("Item", {})
        created_at = existing.get("createdAt", utc_timestamp())
        item = {
            "thread_id": thread_id,
            "timestamp": "THREAD",
            "record_type": "thread",
            "id": thread_id,
            "createdAt": created_at,
            "updatedAt": utc_timestamp(),
            "name": name or existing.get("name") or "New chat",
            "userId": user_id,
            "user_id": user_id,
            "userIdentifier": user_identifier,
            "metadata": metadata or existing.get("metadata") or {},
            "tags": tags if tags is not None else existing.get("tags"),
        }
        self.table.put_item(Item=item)

    def save_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        *,
        user_id: str,
        user_identifier: str,
        thread_name: Optional[str] = None,
    ) -> Optional[str]:
        normalized = (content or "").strip()
        if not normalized:
            return None
        self.ensure_thread(
            thread_id=thread_id,
            user_id=user_id,
            user_identifier=user_identifier,
            name=thread_name,
        )
        if self._recent_duplicate_exists(thread_id, role, normalized):
            return None

        item = {
            "thread_id": thread_id,
            "timestamp": self._message_sort_key(),
            "record_type": "message",
            "message_id": uuid.uuid4().hex,
            "role": role,
            "content": normalized,
            "createdAt": utc_timestamp(),
        }
        self.table.put_item(Item=item)
        return item["message_id"]

    def load_thread(self, thread_id: str) -> Optional[ThreadDict]:
        response = self.table.query(
            KeyConditionExpression=Key("thread_id").eq(thread_id),
            ScanIndexForward=True,
        )
        items = response.get("Items", [])
        if not items:
            return None

        thread_item = next((item for item in items if item.get("record_type") == "thread"), None)
        if not thread_item:
            return None

        steps: List[StepDict] = []
        for item in items:
            if item.get("record_type") != "message":
                continue
            role = item.get("role", "assistant")
            step_type = "user_message" if role == "user" else "assistant_message"
            steps.append(
                StepDict(
                    id=item.get("message_id", uuid.uuid4().hex),
                    threadId=thread_id,
                    type=step_type,
                    name=role,
                    output=item.get("content", ""),
                    createdAt=item.get("createdAt"),
                )
            )

        return ThreadDict(
            id=thread_item["id"],
            createdAt=thread_item["createdAt"],
            name=thread_item.get("name"),
            userId=thread_item.get("userId"),
            userIdentifier=thread_item.get("userIdentifier"),
            tags=thread_item.get("tags"),
            metadata=thread_item.get("metadata"),
            steps=steps,
            elements=[],
        )

    def list_threads(
        self,
        *,
        user_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
    ) -> List[ThreadDict]:
        try:
            if user_id:
                response = self.table.query(
                    IndexName="user_id-index",
                    KeyConditionExpression=Key("user_id").eq(user_id),
                )
                items = response.get("Items", [])
            else:
                response = self.table.query(
                    IndexName="user_id-index",
                    KeyConditionExpression=Key("user_id").eq("admin"),
                )
                items = response.get("Items", [])
        except ClientError:
            LOGGER.warning("user_id-index unavailable; falling back to scan for thread listing")
            items = self.table.scan(
                FilterExpression=Attr("record_type").eq("thread"),
            ).get("Items", [])
        filtered: List[ThreadDict] = []
        for item in items:
            if item.get("record_type") != "thread":
                continue
            if user_id and item.get("userId") != user_id:
                continue
            if search and search.lower() not in (item.get("name") or "").lower():
                continue
            filtered.append(
                ThreadDict(
                    id=item["id"],
                    createdAt=item["createdAt"],
                    name=item.get("name"),
                    userId=item.get("userId"),
                    userIdentifier=item.get("userIdentifier"),
                    tags=item.get("tags"),
                    metadata=item.get("metadata"),
                    steps=[],
                    elements=[],
                )
            )
        filtered.sort(key=lambda thread: thread["createdAt"], reverse=True)
        return filtered[:limit]

    def list_all_threads(self, *, limit: int = 1000) -> List[ThreadDict]:
        items: List[Dict[str, Any]] = []
        response = self.table.scan(
            FilterExpression=Attr("record_type").eq("thread"),
        )
        items.extend(response.get("Items", []))
        while response.get("LastEvaluatedKey") and len(items) < limit:
            response = self.table.scan(
                FilterExpression=Attr("record_type").eq("thread"),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        threads: List[ThreadDict] = []
        for item in items[:limit]:
            threads.append(
                ThreadDict(
                    id=item["id"],
                    createdAt=item["createdAt"],
                    name=item.get("name"),
                    userId=item.get("userId"),
                    userIdentifier=item.get("userIdentifier"),
                    tags=item.get("tags"),
                    metadata=item.get("metadata"),
                    steps=[],
                    elements=[],
                )
            )
        threads.sort(key=lambda thread: thread["createdAt"], reverse=True)
        return threads

    def delete_thread(self, thread_id: str) -> None:
        response = self.table.query(KeyConditionExpression=Key("thread_id").eq(thread_id))
        with self.table.batch_writer() as batch:
            for item in response.get("Items", []):
                batch.delete_item(Key={"thread_id": item["thread_id"], "timestamp": item["timestamp"]})


class ChainlitDynamoThreadDataLayer(BaseDataLayer):
    def __init__(self, store: DynamoDBThreadStore) -> None:
        self.store = store
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def _run(self, fn, *args, **kwargs):
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: fn(*args, **kwargs))

    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        return PersistedUser(
            id=identifier,
            identifier=identifier,
            createdAt=utc_timestamp(),
            metadata={},
        )

    async def create_user(self, user: User) -> Optional[PersistedUser]:
        return PersistedUser(
            id=user.identifier,
            identifier=user.identifier,
            createdAt=utc_timestamp(),
            metadata=user.metadata,
        )

    async def delete_feedback(self, feedback_id: str) -> bool:
        return True

    async def upsert_feedback(self, feedback: Feedback) -> str:
        feedback.id = feedback.id or f"{feedback.threadId}:{feedback.forId}"
        return feedback.id

    async def create_element(self, element) -> None:
        return None

    async def get_element(self, thread_id: str, element_id: str) -> Optional[ElementDict]:
        return None

    async def delete_element(self, element_id: str, thread_id: Optional[str] = None) -> None:
        return None

    async def create_step(self, step_dict: StepDict) -> None:
        role = "user" if step_dict.get("type") == "user_message" else "assistant"
        content = step_dict.get("output") or step_dict.get("input") or ""
        thread_id = step_dict.get("threadId")
        if role != "user":
            return
        if not thread_id or not content.strip():
            return
        await self._run(
            self.store.save_message,
            thread_id,
            role,
            content,
            user_id="admin",
            user_identifier="admin",
        )

    async def update_step(self, step_dict: StepDict) -> None:
        role = "user" if step_dict.get("type") == "user_message" else "assistant"
        if role != "assistant" or step_dict.get("streaming"):
            return
        content = step_dict.get("output") or step_dict.get("input") or ""
        thread_id = step_dict.get("threadId")
        if not thread_id or not content.strip():
            return
        await self._run(
            self.store.save_message,
            thread_id,
            role,
            content,
            user_id="admin",
            user_identifier="admin",
        )

    async def delete_step(self, step_id: str) -> None:
        return None

    async def get_thread_author(self, thread_id: str) -> str:
        thread = await self._run(self.store.load_thread, thread_id)
        if not thread:
            return ""
        return thread.get("userIdentifier") or thread.get("userId") or ""

    async def delete_thread(self, thread_id: str) -> None:
        await self._run(self.store.delete_thread, thread_id)

    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        threads = await self._run(
            self.store.list_threads,
            user_id=filters.userId,
            search=filters.search,
            limit=pagination.first,
        )
        return PaginatedResponse(
            pageInfo=PageInfo(hasNextPage=False, startCursor=pagination.cursor, endCursor=None),
            data=threads,
        )

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        return await self._run(self.store.load_thread, thread_id)

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        await self._run(
            self.store.ensure_thread,
            thread_id,
            user_id or "admin",
            user_id or "admin",
            name,
            metadata,
            tags,
        )

    async def build_debug_url(self) -> str:
        return ""
