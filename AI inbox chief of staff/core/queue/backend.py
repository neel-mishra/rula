from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from core.config import settings

log = structlog.get_logger(__name__)


@dataclass
class QueueMessage:
    body: str
    receipt_handle: str
    raw: dict[str, Any] | None = None


class QueueBackend:
    async def send(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        group_id: str | None = None,
        dedup_id: str | None = None,
    ) -> None:
        raise NotImplementedError

    async def receive(
        self,
        queue_name: str,
        *,
        max_messages: int = 10,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 300,
    ) -> list[QueueMessage]:
        raise NotImplementedError

    async def delete(self, queue_name: str, receipt_handle: str) -> None:
        raise NotImplementedError


class InlineQueueBackend(QueueBackend):
    async def send(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        group_id: str | None = None,
        dedup_id: str | None = None,
    ) -> None:
        log.info("queue.inline.send_noop", queue_name=queue_name, payload=payload)

    async def receive(
        self,
        queue_name: str,
        *,
        max_messages: int = 10,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 300,
    ) -> list[QueueMessage]:
        return []

    async def delete(self, queue_name: str, receipt_handle: str) -> None:
        return


class SQSQueueBackend(QueueBackend):
    def __init__(self) -> None:
        import boto3

        kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.aws_endpoint_url:
            kwargs["endpoint_url"] = settings.aws_endpoint_url
        self._client = boto3.client("sqs", **kwargs)

    @staticmethod
    def _queue_url(queue_name: str) -> str | None:
        urls = {
            "ingest": settings.sqs_ingest_queue_url,
            "triage": settings.sqs_triage_queue_url,
            "draft": settings.sqs_draft_queue_url,
            "brief": settings.sqs_brief_queue_url,
            "memory": settings.sqs_memory_queue_url,
            "eval": settings.sqs_eval_queue_url,
            "dlq": settings.sqs_dlq_url,
        }
        return urls.get(queue_name, "") or None

    async def send(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        group_id: str | None = None,
        dedup_id: str | None = None,
    ) -> None:
        queue_url = self._queue_url(queue_name)
        if not queue_url:
            log.info("queue.sqs.send_skipped_no_queue_url", queue_name=queue_name)
            return
        params: dict[str, Any] = {
            "QueueUrl": queue_url,
            "MessageBody": json.dumps(payload),
        }
        if group_id:
            params["MessageGroupId"] = group_id
        if dedup_id:
            params["MessageDeduplicationId"] = dedup_id
        self._client.send_message(**params)

    async def receive(
        self,
        queue_name: str,
        *,
        max_messages: int = 10,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 300,
    ) -> list[QueueMessage]:
        queue_url = self._queue_url(queue_name)
        if not queue_url:
            return []
        response = self._client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_time_seconds,
            VisibilityTimeout=visibility_timeout,
        )
        messages = response.get("Messages", [])
        return [
            QueueMessage(
                body=msg.get("Body", "{}"),
                receipt_handle=msg["ReceiptHandle"],
                raw=msg,
            )
            for msg in messages
        ]

    async def delete(self, queue_name: str, receipt_handle: str) -> None:
        queue_url = self._queue_url(queue_name)
        if not queue_url:
            return
        self._client.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle,
        )


class RedisStreamsQueueBackend(QueueBackend):
    def __init__(self) -> None:
        from redis.asyncio import from_url

        self._redis = from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        self._group = "inbox-cos"
        self._consumer = "worker-1"

    @staticmethod
    def _stream_name(queue_name: str) -> str:
        return f"inbox:{queue_name}"

    async def _ensure_group(self, queue_name: str) -> None:
        stream = self._stream_name(queue_name)
        try:
            await self._redis.xgroup_create(stream, self._group, id="$", mkstream=True)
        except Exception as exc:  # BUSYGROUP is expected after first boot
            if "BUSYGROUP" not in str(exc):
                raise

    async def send(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        group_id: str | None = None,
        dedup_id: str | None = None,
    ) -> None:
        stream = self._stream_name(queue_name)
        await self._redis.xadd(
            stream,
            {"body": json.dumps(payload)},
        )

    async def receive(
        self,
        queue_name: str,
        *,
        max_messages: int = 10,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 300,
    ) -> list[QueueMessage]:
        await self._ensure_group(queue_name)
        stream = self._stream_name(queue_name)
        # visibility_timeout is not directly mapped in this first pass.
        results = await self._redis.xreadgroup(
            groupname=self._group,
            consumername=self._consumer,
            streams={stream: ">"},
            count=max_messages,
            block=wait_time_seconds * 1000,
        )
        out: list[QueueMessage] = []
        for _, entries in results:
            for entry_id, fields in entries:
                out.append(
                    QueueMessage(
                        body=fields.get("body", "{}"),
                        receipt_handle=entry_id,
                        raw={"id": entry_id, "fields": fields},
                    )
                )
        return out

    async def delete(self, queue_name: str, receipt_handle: str) -> None:
        stream = self._stream_name(queue_name)
        await self._redis.xack(stream, self._group, receipt_handle)
        await self._redis.xdel(stream, receipt_handle)


def get_queue_backend() -> QueueBackend:
    if settings.queue_backend == "redis_streams":
        return RedisStreamsQueueBackend()
    if settings.queue_backend == "inline":
        return InlineQueueBackend()
    return SQSQueueBackend()
