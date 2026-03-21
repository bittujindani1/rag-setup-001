from __future__ import annotations

import logging
import time
import uuid

import boto3
from boto3.dynamodb.conditions import Attr, Key


LOGGER = logging.getLogger(__name__)


class DynamoDBRateLimiter:
    def __init__(self, table_name: str, region_name: str, limit_per_minute: int = 15) -> None:
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)
        self.limit_per_minute = limit_per_minute

    def check_and_record(self, session_id: str) -> tuple[bool, int]:
        now = int(time.time())
        cutoff = now - 60
        response = self.table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            FilterExpression=Attr("timestamp").gte(cutoff),
            Select="COUNT",
        )
        current_count = int(response.get("Count", 0))
        if current_count >= self.limit_per_minute:
            LOGGER.warning("Rate limit exceeded session_id=%s current_count=%s limit=%s", session_id, current_count, self.limit_per_minute)
            return False, current_count

        self.table.put_item(
            Item={
                "session_id": session_id,
                "request_id": f"{now}#{uuid.uuid4()}",
                "timestamp": now,
                "expires_at": now + 120,
            }
        )
        LOGGER.info("Rate limiter recorded session_id=%s current_count=%s expires_at=%s", session_id, current_count + 1, now + 120)
        return True, current_count + 1
