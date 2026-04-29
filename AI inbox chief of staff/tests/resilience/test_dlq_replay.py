"""Gate 6 resilience — DLQ replay worker.

Covers:
  - Selective replay with dry_run=True → no DB/queue mutations; reports inspected
    payloads only. The SQS source queue must NEVER receive a send_message call,
    and the DLQ must NEVER receive a delete_message call.
  - mailbox_filter scoping → messages whose body.mailbox_id != filter are skipped
    (no send/delete) while matching messages get re-sent and deleted.
  - Idempotent reprocessing → calling replay_dlq twice over the same logical
    payload set produces no duplicate side effects on the second pass when the
    DLQ is empty (which is the realistic state after the first pass deleted
    everything). This exercises the real-world idempotency guarantee.
  - Per-message replay error → a send_message failure on one message increments
    `errors`, the loop continues to drain remaining messages successfully, and
    `core.alerts.emit_alert` is invoked once for the batch (the post-loop
    summary alert in workers/dlq_replay.py).

All SQS interaction is mocked at the boto3 client level. No AWS calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from workers.dlq_replay import replay_dlq


# ─────────────────────────────── helpers ──────────────────────────────────


def _make_msg(message_id: str, mailbox_id: str = "mailbox-A", correlation_id: str | None = None) -> dict:
    """Build a fake SQS message envelope as receive_message would return."""
    body = {
        "mailbox_id": mailbox_id,
        "correlation_id": correlation_id or f"corr-{message_id}",
        "user_id": "user-1",
        "history_id": "12345",
    }
    return {
        "MessageId": message_id,
        "ReceiptHandle": f"rh-{message_id}",
        "Body": json.dumps(body),
        "Attributes": {"ApproximateReceiveCount": "3"},
    }


def _make_sqs_mock(message_batches: list[list[dict]]) -> MagicMock:
    """Build a MagicMock SQS client that returns the given batches in order
    on successive receive_message calls. After all batches, returns empty."""
    sqs = MagicMock()
    # Pad with a final empty batch so the worker's while-loop terminates.
    queue: list[dict] = [{"Messages": batch} for batch in message_batches] + [
        {"Messages": []}
    ]
    sqs.receive_message.side_effect = queue
    sqs.send_message.return_value = {"MessageId": "sent-id"}
    sqs.delete_message.return_value = {}
    return sqs


# ──────────────────────────────── tests ───────────────────────────────────


class TestDLQReplayDryRun:
    def test_dry_run_inspects_without_mutating_anything(self):
        sqs = _make_sqs_mock([
            [_make_msg("m1"), _make_msg("m2"), _make_msg("m3")],
        ])

        with patch("workers.dlq_replay.boto3.client", return_value=sqs):
            summary = replay_dlq(
                dlq_url="https://sqs/dlq",
                source_queue_url="https://sqs/source",
                dry_run=True,
            )

        # All three are skipped (dry_run never replays); inspected list populated.
        assert summary["dry_run"] is True
        assert summary["replayed"] == 0
        assert summary["skipped"] == 3
        assert summary["errors"] == 0
        assert len(summary["inspected"]) == 3
        assert {i["message_id"] for i in summary["inspected"]} == {"m1", "m2", "m3"}

        # Critical: no mutations.
        sqs.send_message.assert_not_called()
        sqs.delete_message.assert_not_called()


class TestDLQReplayMailboxFilter:
    def test_filter_scopes_to_named_mailbox_only(self):
        sqs = _make_sqs_mock([
            [
                _make_msg("m1", mailbox_id="mailbox-A"),
                _make_msg("m2", mailbox_id="mailbox-B"),
                _make_msg("m3", mailbox_id="mailbox-A"),
                _make_msg("m4", mailbox_id="mailbox-C"),
            ],
        ])

        with patch("workers.dlq_replay.boto3.client", return_value=sqs):
            summary = replay_dlq(
                dlq_url="https://sqs/dlq",
                source_queue_url="https://sqs/source",
                mailbox_filter="mailbox-A",
            )

        # Only mailbox-A messages should be replayed (m1, m3).
        assert summary["replayed"] == 2
        # m2 and m4 are skipped due to filter mismatch.
        assert summary["skipped"] == 2
        assert summary["errors"] == 0

        # Verify only mailbox-A messages were re-sent.
        sent_bodies = [
            json.loads(call.kwargs["MessageBody"])
            for call in sqs.send_message.call_args_list
        ]
        sent_mailboxes = sorted(b["mailbox_id"] for b in sent_bodies)
        assert sent_mailboxes == ["mailbox-A", "mailbox-A"]

        # Verify only mailbox-A messages were deleted from the DLQ.
        deleted_handles = sorted(
            call.kwargs["ReceiptHandle"] for call in sqs.delete_message.call_args_list
        )
        assert deleted_handles == ["rh-m1", "rh-m3"]


class TestDLQReplayIdempotency:
    def test_replaying_twice_produces_no_duplicate_side_effects(self):
        """First pass replays; second pass over the (now empty) DLQ does
        nothing. This documents the real-world idempotency contract: the DLQ
        is drained on success, so re-running the worker is safe."""
        # First pass: one message in the DLQ.
        sqs1 = _make_sqs_mock([[_make_msg("m1")]])

        with patch("workers.dlq_replay.boto3.client", return_value=sqs1):
            first = replay_dlq(
                dlq_url="https://sqs/dlq",
                source_queue_url="https://sqs/source",
            )

        assert first["replayed"] == 1
        assert sqs1.send_message.call_count == 1
        assert sqs1.delete_message.call_count == 1

        # Second pass: DLQ is now empty (worker deleted it on the first pass).
        sqs2 = _make_sqs_mock([])  # only the empty terminator batch

        with patch("workers.dlq_replay.boto3.client", return_value=sqs2):
            second = replay_dlq(
                dlq_url="https://sqs/dlq",
                source_queue_url="https://sqs/source",
            )

        assert second["replayed"] == 0
        assert second["skipped"] == 0
        assert second["errors"] == 0
        # Critically: no further sends or deletes.
        sqs2.send_message.assert_not_called()
        sqs2.delete_message.assert_not_called()


class TestDLQReplayErrorIsolation:
    def test_one_send_failure_alerts_and_continues_with_remaining(self):
        sqs = _make_sqs_mock([
            [_make_msg("m1"), _make_msg("m2"), _make_msg("m3")],
        ])

        # Make the second send fail; the first and third should still succeed.
        def _send(*, QueueUrl, MessageBody, **kwargs):
            body = json.loads(MessageBody)
            if body["correlation_id"] == "corr-m2":
                raise RuntimeError("SQS throttled")
            return {"MessageId": "sent"}

        sqs.send_message.side_effect = _send

        captured_alerts: list[tuple] = []

        def fake_emit_alert(severity, title, details=None):
            captured_alerts.append((severity, title, details))
            return {}

        # The worker's `from core.alerts import ...` is a deferred import
        # inside replay_dlq. Patch the source module so the deferred lookup
        # picks up the fake.
        with patch("workers.dlq_replay.boto3.client", return_value=sqs), \
             patch("core.alerts.emit_alert", side_effect=fake_emit_alert):
            summary = replay_dlq(
                dlq_url="https://sqs/dlq",
                source_queue_url="https://sqs/source",
            )

        # m1 and m3 replayed; m2 errored — but loop continued to drain the batch.
        assert summary["replayed"] == 2
        assert summary["errors"] == 1
        # delete_message only called for the two successful sends.
        deleted = sorted(
            call.kwargs["ReceiptHandle"] for call in sqs.delete_message.call_args_list
        )
        assert deleted == ["rh-m1", "rh-m3"]

        # Exactly one batch-level alert was emitted (post-loop summary).
        assert len(captured_alerts) == 1
        severity, title, details = captured_alerts[0]
        assert "DLQ replay had 1 error" in title
        assert details["errors"] == 1
        assert details["replayed"] == 2

    def test_dry_run_does_not_emit_alert_even_with_inspected_items(self):
        """Dry-run should never alert; alerts are reserved for real failures."""
        sqs = _make_sqs_mock([[_make_msg("m1"), _make_msg("m2")]])
        captured: list = []

        with patch("workers.dlq_replay.boto3.client", return_value=sqs), \
             patch("core.alerts.emit_alert", side_effect=lambda *a, **kw: captured.append(a) or {}):
            summary = replay_dlq(
                dlq_url="https://sqs/dlq",
                source_queue_url="https://sqs/source",
                dry_run=True,
            )

        assert summary["errors"] == 0
        assert captured == []
