"""
Tests for ``workers.audit_export`` — the S3 audit-event export pipeline (X.10).

Uses ``moto`` to mock S3 and the existing SQLite in-memory ``db_session``
fixture to seed ``audit_events`` rows. The audit_events table is read-only
from this worker's perspective — none of these tests modify the schema or
exercise UPDATE/DELETE paths.

Design notes:
    - Empty days produce NO S3 objects (verified by ``test_empty_day_produces_no_object``).
    - Idempotency uses a sentinel object at ``{prefix}/_runs/{date}.json``
      that records the lexicographic max event id exported for that date.
    - When ``AUDIT_EXPORT_S3_BUCKET`` is unset the worker logs and returns
      cleanly without touching S3 at all.
"""

from __future__ import annotations

import gzip
import json
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

from core.models.audit import AuditEvent
from workers import audit_export
from workers.audit_export import (
    ExportResult,
    export_audit_events,
    run_daily_export,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

TEST_BUCKET = "test-audit-export-bucket"
TEST_PREFIX = "audit/"


@pytest.fixture
def s3_mock():
    """Spin up a moto S3 mock and pre-create the test bucket."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=TEST_BUCKET)
        yield client


@pytest.fixture(autouse=True)
def _patch_worker_session(db_session, monkeypatch):
    """
    Make the worker read from the same in-memory SQLite session the test uses.

    The worker calls ``core.db.get_db_session()`` which builds its own engine
    pointing at a (separate) in-memory SQLite — that engine has no tables.
    Redirecting the symbol used inside ``workers.audit_export`` to the test's
    ``db_session`` keeps the worker code path identical while letting the
    test seed rows via ORM as usual.
    """

    @asynccontextmanager
    async def _fake_session():
        # Don't commit/rollback the outer test session here; the test fixture
        # owns the lifecycle.
        yield db_session

    monkeypatch.setattr(audit_export, "get_db_session", _fake_session)
    yield


def _make_event(
    *,
    created_at: datetime,
    event_type: str = "triage.decision",
    actor: str = "worker:triage",
    payload: dict | None = None,
    correlation_id: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        actor=actor,
        payload=payload or {"k": "v"},
        severity="info",
        correlation_id=correlation_id or str(uuid.uuid4()),
        created_at=created_at,
    )


async def _seed_events(db_session, events: list[AuditEvent]) -> None:
    for ev in events:
        db_session.add(ev)
    await db_session.commit()


def _list_data_objects(client, prefix: str = TEST_PREFIX) -> list[dict]:
    """Return data files only (excluding the ``_runs/`` ledger sentinels)."""
    resp = client.list_objects_v2(Bucket=TEST_BUCKET, Prefix=prefix)
    return [
        obj
        for obj in resp.get("Contents", [])
        if "/_runs/" not in obj["Key"]
    ]


def _list_ledger_objects(client, prefix: str = TEST_PREFIX) -> list[dict]:
    resp = client.list_objects_v2(Bucket=TEST_BUCKET, Prefix=f"{prefix}_runs/")
    return resp.get("Contents", [])


def _read_ndjson_gz(client, key: str) -> list[dict]:
    obj = client.get_object(Bucket=TEST_BUCKET, Key=key)
    raw = obj["Body"].read()
    decompressed = gzip.decompress(raw).decode("utf-8")
    return [json.loads(line) for line in decompressed.splitlines() if line.strip()]


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exports_events_to_mocked_s3(db_session, s3_mock):
    """Happy path — N events on a single day land as one gzip NDJSON object."""
    target = date(2026, 4, 27)
    base = datetime.combine(target, time(10, 0, 0), tzinfo=timezone.utc)
    events = [
        _make_event(created_at=base, event_type="auth.connect"),
        _make_event(
            created_at=base + timedelta(minutes=5),
            event_type="triage.decision",
            payload={"label": "PROMOTIONS", "confidence": 0.91},
        ),
        _make_event(
            created_at=base + timedelta(hours=2),
            event_type="mutation.archive",
        ),
    ]
    await _seed_events(db_session, events)

    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    result: ExportResult = await export_audit_events(
        start=start,
        end=start + timedelta(days=1),
        bucket=TEST_BUCKET,
        prefix=TEST_PREFIX,
        s3_client=s3_mock,
    )

    assert result.events_exported == 3
    assert result.skipped_no_bucket is False
    assert result.skipped_empty is False
    assert result.s3_key is not None
    assert result.s3_key.endswith(".ndjson.gz")
    assert result.new_watermark is not None

    data_objs = _list_data_objects(s3_mock)
    assert len(data_objs) == 1
    rows = _read_ndjson_gz(s3_mock, data_objs[0]["Key"])
    assert len(rows) == 3
    event_types = {r["event_type"] for r in rows}
    assert event_types == {"auth.connect", "triage.decision", "mutation.archive"}

    # Ledger sentinel was written.
    ledgers = _list_ledger_objects(s3_mock)
    assert len(ledgers) == 1
    assert ledgers[0]["Key"] == f"{TEST_PREFIX}_runs/{target.isoformat()}.json"


@pytest.mark.asyncio
async def test_rerun_is_idempotent_no_duplicate_export(db_session, s3_mock):
    """Re-running on the same date with no new rows skips writing a data file."""
    target = date(2026, 4, 26)
    base = datetime.combine(target, time(9, 0, 0), tzinfo=timezone.utc)
    events = [_make_event(created_at=base + timedelta(minutes=i)) for i in range(4)]
    await _seed_events(db_session, events)

    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    first = await export_audit_events(
        start=start, end=end, bucket=TEST_BUCKET, prefix=TEST_PREFIX, s3_client=s3_mock,
    )
    assert first.events_exported == 4
    assert _list_data_objects(s3_mock).__len__() == 1

    second = await export_audit_events(
        start=start, end=end, bucket=TEST_BUCKET, prefix=TEST_PREFIX, s3_client=s3_mock,
    )
    # No new rows since the watermark — must NOT write another data object.
    assert second.skipped_empty is True
    assert second.events_exported == 0
    assert second.previous_watermark == first.new_watermark
    assert _list_data_objects(s3_mock).__len__() == 1, (
        "second run wrote a duplicate data object — idempotency broken"
    )


@pytest.mark.asyncio
async def test_rerun_picks_up_only_new_events(db_session, s3_mock):
    """When new rows arrive after a prior run, only those are exported."""
    target = date(2026, 4, 25)
    base = datetime.combine(target, time(8, 0, 0), tzinfo=timezone.utc)
    initial = [_make_event(created_at=base + timedelta(minutes=i)) for i in range(2)]
    await _seed_events(db_session, initial)

    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    first = await export_audit_events(
        start=start, end=end, bucket=TEST_BUCKET, prefix=TEST_PREFIX, s3_client=s3_mock,
    )
    assert first.events_exported == 2

    later = [
        _make_event(created_at=base + timedelta(hours=4)),
        _make_event(created_at=base + timedelta(hours=5)),
        _make_event(created_at=base + timedelta(hours=6)),
    ]
    await _seed_events(db_session, later)

    second = await export_audit_events(
        start=start, end=end, bucket=TEST_BUCKET, prefix=TEST_PREFIX, s3_client=s3_mock,
    )
    assert second.events_exported == 3
    data_objs = _list_data_objects(s3_mock)
    assert len(data_objs) == 2  # one per run

    # The second object should contain only the 3 newer events.
    second_rows = _read_ndjson_gz(s3_mock, second.s3_key)
    assert len(second_rows) == 3


@pytest.mark.asyncio
async def test_date_partitioning_is_correct(db_session, s3_mock):
    """The S3 key embeds year=/month=/day= matching the export window."""
    target = date(2026, 1, 9)  # picked to verify zero-padding on month/day
    base = datetime.combine(target, time(12, 0, 0), tzinfo=timezone.utc)
    await _seed_events(db_session, [_make_event(created_at=base)])

    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    result = await export_audit_events(
        start=start,
        end=start + timedelta(days=1),
        bucket=TEST_BUCKET,
        prefix=TEST_PREFIX,
        s3_client=s3_mock,
    )

    assert result.s3_key is not None
    assert result.s3_key.startswith(f"{TEST_PREFIX}year=2026/month=01/day=09/")
    assert result.s3_key.endswith(".ndjson.gz")


@pytest.mark.asyncio
async def test_empty_day_produces_no_object(db_session, s3_mock):
    """No rows on the target date → no S3 object, no ledger update."""
    # Seed a row on a *different* day so the table isn't empty overall.
    other_day = datetime(2026, 4, 20, 14, 0, 0, tzinfo=timezone.utc)
    await _seed_events(db_session, [_make_event(created_at=other_day)])

    target = date(2026, 4, 21)
    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    result = await export_audit_events(
        start=start,
        end=start + timedelta(days=1),
        bucket=TEST_BUCKET,
        prefix=TEST_PREFIX,
        s3_client=s3_mock,
    )

    assert result.skipped_empty is True
    assert result.events_exported == 0
    assert result.s3_key is None

    # Bucket still has nothing under the partition for the empty day, and no
    # ledger sentinel was written for that day either.
    assert _list_data_objects(s3_mock) == []
    assert _list_ledger_objects(s3_mock) == []


@pytest.mark.asyncio
async def test_no_op_when_bucket_unset(db_session, s3_mock):
    """When AUDIT_EXPORT_S3_BUCKET is empty, function returns early cleanly."""
    target = date(2026, 4, 27)
    base = datetime.combine(target, time(10, 0, 0), tzinfo=timezone.utc)
    await _seed_events(db_session, [_make_event(created_at=base)])

    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    result = await export_audit_events(
        start=start,
        end=start + timedelta(days=1),
        bucket="",  # explicitly unset
        prefix=TEST_PREFIX,
        s3_client=s3_mock,
    )

    assert result.skipped_no_bucket is True
    assert result.events_exported == 0
    assert result.bucket is None
    # And nothing was written to S3.
    assert _list_data_objects(s3_mock) == []
    assert _list_ledger_objects(s3_mock) == []


@pytest.mark.asyncio
async def test_run_daily_export_targets_yesterday(db_session, s3_mock, monkeypatch):
    """``run_daily_export`` with no args exports yesterday's events (UTC)."""
    # Pin "today" to a deterministic value so this test doesn't depend on the
    # wall clock (or on whatever data other tests have committed to the
    # session-scoped SQLite engine — it rolls back transactions, not commits).
    fixed_today = date(2099, 1, 2)
    fixed_yesterday = fixed_today - timedelta(days=1)
    base = datetime.combine(fixed_yesterday, time(11, 0, 0), tzinfo=timezone.utc)
    await _seed_events(db_session, [_make_event(created_at=base)])

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(fixed_today.year, fixed_today.month, fixed_today.day, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(audit_export, "datetime", _FrozenDatetime)
    monkeypatch.setattr(audit_export.settings, "audit_export_s3_bucket", TEST_BUCKET)
    monkeypatch.setattr(audit_export.settings, "audit_export_s3_prefix", TEST_PREFIX)

    result = await run_daily_export(s3_client=s3_mock)
    assert result.target_date == fixed_yesterday
    assert result.events_exported == 1
    assert result.s3_key is not None
    assert f"year={fixed_yesterday.year:04d}" in result.s3_key


@pytest.mark.asyncio
async def test_dry_run_does_not_write_to_s3(db_session, s3_mock):
    """``dry_run=True`` reports planned export without touching S3."""
    target = date(2026, 4, 24)
    base = datetime.combine(target, time(10, 0, 0), tzinfo=timezone.utc)
    await _seed_events(db_session, [_make_event(created_at=base)])

    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    result = await export_audit_events(
        start=start,
        end=start + timedelta(days=1),
        bucket=TEST_BUCKET,
        prefix=TEST_PREFIX,
        s3_client=s3_mock,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.events_exported == 1
    assert result.s3_key is not None  # planned key reported
    assert _list_data_objects(s3_mock) == []
    assert _list_ledger_objects(s3_mock) == []


@pytest.mark.asyncio
async def test_rejects_multi_day_window(s3_mock):
    """Multi-day windows are rejected to keep partition layout unambiguous."""
    start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        await export_audit_events(
            start=start,
            end=start + timedelta(days=2),
            bucket=TEST_BUCKET,
            prefix=TEST_PREFIX,
            s3_client=s3_mock,
        )


@pytest.mark.asyncio
async def test_rejects_naive_datetime(s3_mock):
    """Naive (timezone-less) start/end are rejected."""
    with pytest.raises(ValueError):
        await export_audit_events(
            start=datetime(2026, 4, 1),
            end=datetime(2026, 4, 2),
            bucket=TEST_BUCKET,
            prefix=TEST_PREFIX,
            s3_client=s3_mock,
        )
