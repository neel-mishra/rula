from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config import settings
from core.queue.backend import (
    InlineQueueBackend,
    QueueMessage,
    RedisStreamsQueueBackend,
    SQSQueueBackend,
    get_queue_backend,
)


class _FakeSQSClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.deleted: list[dict] = []
        self.messages: list[dict] = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)

    def receive_message(self, **kwargs):
        return {"Messages": self.messages}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)


class _FakeRedis:
    def __init__(self) -> None:
        self.acked: list[tuple[str, str, str]] = []
        self.deleted: list[tuple[str, str]] = []
        self._xreadgroup_results = []

    async def xgroup_create(self, stream, group, id="$", mkstream=True):
        return None

    async def xadd(self, stream, fields):
        return "1-0"

    async def xreadgroup(self, **kwargs):
        return self._xreadgroup_results

    async def xack(self, stream, group, receipt_handle):
        self.acked.append((stream, group, receipt_handle))

    async def xdel(self, stream, receipt_handle):
        self.deleted.append((stream, receipt_handle))


@pytest.mark.asyncio
async def test_inline_backend_is_noop():
    backend = InlineQueueBackend()
    await backend.send("ingest", {"x": 1})
    msgs = await backend.receive("ingest")
    assert msgs == []
    await backend.delete("ingest", "r1")


@pytest.mark.asyncio
async def test_sqs_backend_send_receive_delete(monkeypatch):
    fake = _FakeSQSClient()
    fake.messages = [{"Body": '{"k":"v"}', "ReceiptHandle": "rh-1"}]

    monkeypatch.setattr(settings, "sqs_ingest_queue_url", "https://example.com/ingest")
    monkeypatch.setattr(settings, "aws_endpoint_url", "")

    with patch("boto3.client", return_value=fake):
        backend = SQSQueueBackend()
        await backend.send("ingest", {"k": "v"}, group_id="g1", dedup_id="d1")
        msgs = await backend.receive("ingest")
        await backend.delete("ingest", "rh-1")

    assert len(fake.sent) == 1
    assert fake.sent[0]["QueueUrl"] == "https://example.com/ingest"
    assert fake.sent[0]["MessageGroupId"] == "g1"
    assert fake.sent[0]["MessageDeduplicationId"] == "d1"
    assert msgs == [QueueMessage(body='{"k":"v"}', receipt_handle="rh-1", raw=fake.messages[0])]
    assert len(fake.deleted) == 1


@pytest.mark.asyncio
async def test_sqs_backend_skips_when_queue_url_missing(monkeypatch):
    fake = _FakeSQSClient()
    monkeypatch.setattr(settings, "sqs_ingest_queue_url", "")

    with patch("boto3.client", return_value=fake):
        backend = SQSQueueBackend()
        await backend.send("ingest", {"k": "v"})
        msgs = await backend.receive("ingest")
        await backend.delete("ingest", "rh-1")

    assert fake.sent == []
    assert msgs == []
    assert fake.deleted == []


@pytest.mark.asyncio
async def test_redis_streams_backend_send_receive_delete(monkeypatch):
    fake_redis = _FakeRedis()
    fake_redis._xreadgroup_results = [
        ("inbox:ingest", [("1-0", {"body": '{"k":"v"}'})]),
    ]

    with patch("redis.asyncio.from_url", return_value=fake_redis):
        backend = RedisStreamsQueueBackend()
        await backend.send("ingest", {"k": "v"})
        msgs = await backend.receive("ingest", max_messages=1, wait_time_seconds=1)
        await backend.delete("ingest", "1-0")

    assert len(msgs) == 1
    assert msgs[0].body == '{"k":"v"}'
    assert msgs[0].receipt_handle == "1-0"
    assert fake_redis.acked == [("inbox:ingest", "inbox-cos", "1-0")]
    assert fake_redis.deleted == [("inbox:ingest", "1-0")]


def test_get_queue_backend_selector(monkeypatch):
    monkeypatch.setattr(settings, "queue_backend", "inline")
    assert isinstance(get_queue_backend(), InlineQueueBackend)

    monkeypatch.setattr(settings, "queue_backend", "redis_streams")
    with patch("redis.asyncio.from_url", return_value=_FakeRedis()):
        assert isinstance(get_queue_backend(), RedisStreamsQueueBackend)

    monkeypatch.setattr(settings, "queue_backend", "sqs")
    with patch("boto3.client", return_value=_FakeSQSClient()):
        assert isinstance(get_queue_backend(), SQSQueueBackend)
