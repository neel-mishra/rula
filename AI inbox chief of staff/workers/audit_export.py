"""
Audit-event S3 export worker (roadmap X.10).

Streams rows from the ``audit_events`` table to S3 as gzip-compressed
newline-delimited JSON, partitioned by the ``created_at`` date.

Object layout::

    s3://{bucket}/{prefix}/year=YYYY/month=MM/day=DD/events-{run_id}.ndjson.gz

Idempotency:
    A sentinel object at ``s3://{bucket}/{prefix}/_runs/{date}.json`` records
    the largest event id and event count exported for that date. Re-runs
    against the same date skip rows whose id is lexicographically
    less-than-or-equal to the recorded watermark. Empty days produce no S3
    objects (no data file, no ledger update) so the export is fully a no-op
    on idle days.

Configuration:
    ``AUDIT_EXPORT_S3_BUCKET`` — destination bucket. When empty the worker
    logs and exits cleanly so dev/staging without S3 stays a no-op.
    ``AUDIT_EXPORT_S3_PREFIX`` — key prefix (default ``audit/``).

CLI::

    python -m workers.audit_export                 # exports yesterday (UTC)
    python -m workers.audit_export --date 2026-04-27
    python -m workers.audit_export --date 2026-04-27 --dry-run

The audit_events table is append-only and protected by a DB trigger; this
worker only reads from it and never issues UPDATE/DELETE.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select

from core.config import settings
from core.db import get_db_session
from core.models.audit import AuditEvent

log = structlog.get_logger(__name__)


# Streaming chunk size — keeps memory bounded for large export days.
_DB_CHUNK_SIZE = 500


@dataclass
class ExportResult:
    """Outcome of a single ``export_audit_events`` invocation."""

    bucket: str | None
    prefix: str
    target_date: date
    events_exported: int = 0
    s3_key: str | None = None
    skipped_no_bucket: bool = False
    skipped_empty: bool = False
    dry_run: bool = False
    run_id: str = ""
    new_watermark: str | None = None
    previous_watermark: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "prefix": self.prefix,
            "target_date": self.target_date.isoformat(),
            "events_exported": self.events_exported,
            "s3_key": self.s3_key,
            "skipped_no_bucket": self.skipped_no_bucket,
            "skipped_empty": self.skipped_empty,
            "dry_run": self.dry_run,
            "run_id": self.run_id,
            "new_watermark": self.new_watermark,
            "previous_watermark": self.previous_watermark,
            **self.extras,
        }


# ── S3 helpers ────────────────────────────────────────────────────────────────


def _build_s3_client():
    """Construct a sync boto3 S3 client. Mirrors ``core/email/ses.py``."""
    import boto3

    kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.client("s3", **kwargs)


def _normalize_prefix(prefix: str) -> str:
    """Strip leading slashes and ensure a single trailing slash."""
    cleaned = prefix.strip().lstrip("/")
    if not cleaned:
        return ""
    if not cleaned.endswith("/"):
        cleaned += "/"
    return cleaned


def _partition_path(prefix: str, target_date: date) -> str:
    return (
        f"{prefix}year={target_date.year:04d}/"
        f"month={target_date.month:02d}/"
        f"day={target_date.day:02d}/"
    )


def _ledger_key(prefix: str, target_date: date) -> str:
    return f"{prefix}_runs/{target_date.isoformat()}.json"


def _read_ledger(client, bucket: str, key: str) -> dict[str, Any]:
    """Return the prior run ledger or an empty dict when absent."""
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:  # botocore.exceptions.ClientError NoSuchKey
        # Treat any read failure as "no ledger" — first run, or transient miss.
        # The next successful run will simply pick up from the beginning.
        err_code = getattr(getattr(exc, "response", {}).get("Error", {}), "get", lambda _k, _d=None: None)("Code")
        if err_code in (None, "NoSuchKey", "404", "NoSuchBucket"):
            return {}
        log.warning("audit_export.ledger_read_failed", key=key, error=str(exc))
        return {}
    body = resp["Body"].read()
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.warning("audit_export.ledger_parse_failed", key=key, error=str(exc))
        return {}


def _serialize_event(event: AuditEvent) -> str:
    """Render a single AuditEvent as a single-line JSON string."""
    payload = {
        "id": str(event.id),
        "user_id": str(event.user_id) if event.user_id else None,
        "mailbox_id": str(event.mailbox_id) if event.mailbox_id else None,
        "event_type": event.event_type,
        "actor": event.actor,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "payload": event.payload or {},
        "severity": event.severity,
        "correlation_id": event.correlation_id,
        "created_at": (
            event.created_at.astimezone(timezone.utc).isoformat()
            if event.created_at and event.created_at.tzinfo
            else event.created_at.isoformat()
            if event.created_at
            else None
        ),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


# ── Core export ───────────────────────────────────────────────────────────────


async def _stream_events_for_day(
    target_date: date,
    after_created_at: datetime | None,
    after_id: str | None,
) -> list[AuditEvent]:
    """
    Load all audit events whose ``created_at`` falls on ``target_date`` (UTC),
    excluding any whose ``(created_at, id)`` is <= the prior watermark.

    Rows are ordered by ``(created_at, id)`` so the watermark is monotonic and
    re-runs deterministically pick up new rows only. The full result is
    materialized but the worker chunks DB fetches via ``yield_per`` to keep
    memory bounded.
    """
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    stmt = (
        select(AuditEvent)
        .where(AuditEvent.created_at >= start)
        .where(AuditEvent.created_at < end)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .execution_options(yield_per=_DB_CHUNK_SIZE)
    )

    rows: list[AuditEvent] = []
    async with get_db_session() as session:
        result = await session.stream(stmt)
        async for event in result.scalars():
            if after_created_at is not None and after_id is not None:
                # Compose-watermark filter: keep only rows strictly after
                # (after_created_at, after_id) in (created_at, id) order.
                ev_created = event.created_at
                if ev_created.tzinfo is None:
                    ev_created = ev_created.replace(tzinfo=timezone.utc)
                if (ev_created, str(event.id)) <= (after_created_at, after_id):
                    continue
            rows.append(event)
    return rows


def _write_gzip_ndjson(events: list[AuditEvent]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for event in events:
            gz.write(_serialize_event(event).encode("utf-8"))
            gz.write(b"\n")
    return buf.getvalue()


async def export_audit_events(
    start: datetime,
    end: datetime,
    bucket: str | None,
    prefix: str = "audit/",
    *,
    dry_run: bool = False,
    s3_client=None,
) -> ExportResult:
    """
    Export audit events whose ``created_at`` lies in ``[start, end)`` to S3.

    The window must cover exactly one UTC date — multi-day exports should call
    this function once per day. ``run_daily_export`` does this for the common
    "yesterday" case. Passing a multi-day window raises ``ValueError`` to keep
    partition layout unambiguous.

    Args:
        start: window lower bound (inclusive). Must be at UTC midnight.
        end: window upper bound (exclusive). Must equal ``start + 1 day``.
        bucket: destination S3 bucket. ``None``/empty → worker is a no-op.
        prefix: key prefix (default ``audit/``).
        dry_run: when True, scan and log but do not write to S3.
        s3_client: optional pre-built boto3 client (for tests).

    Returns:
        ExportResult — populated regardless of whether an object was written.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be timezone-aware (UTC)")
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    if end_utc != start_utc + timedelta(days=1):
        raise ValueError(
            "export_audit_events requires a single UTC-day window "
            "(end must equal start + 1 day)"
        )
    if start_utc.time() != time.min:
        raise ValueError("start must be at UTC midnight (00:00:00)")

    target_date = start_utc.date()
    norm_prefix = _normalize_prefix(prefix)
    run_id = uuid.uuid4().hex

    # ── No-op path: bucket unset ──────────────────────────────────────────
    if not bucket:
        log.info(
            "audit_export.skipped_no_bucket",
            target_date=target_date.isoformat(),
            reason="AUDIT_EXPORT_S3_BUCKET is not configured",
        )
        return ExportResult(
            bucket=None,
            prefix=norm_prefix,
            target_date=target_date,
            skipped_no_bucket=True,
            run_id=run_id,
        )

    client = s3_client if s3_client is not None else _build_s3_client()

    # ── Read prior watermark ──────────────────────────────────────────────
    ledger_key = _ledger_key(norm_prefix, target_date)
    prior_ledger = _read_ledger(client, bucket, ledger_key)
    prior_max_event_id: str | None = prior_ledger.get("max_event_id")
    prior_max_created_iso: str | None = prior_ledger.get("max_created_at")
    prior_max_created: datetime | None = None
    if prior_max_created_iso:
        try:
            prior_max_created = datetime.fromisoformat(prior_max_created_iso)
            if prior_max_created.tzinfo is None:
                prior_max_created = prior_max_created.replace(tzinfo=timezone.utc)
        except ValueError:
            log.warning(
                "audit_export.ledger_bad_timestamp",
                value=prior_max_created_iso,
            )
            prior_max_created = None

    # ── Pull rows ──────────────────────────────────────────────────────────
    events = await _stream_events_for_day(
        target_date,
        after_created_at=prior_max_created,
        after_id=prior_max_event_id,
    )

    if not events:
        log.info(
            "audit_export.empty_day",
            bucket=bucket,
            target_date=target_date.isoformat(),
            previous_watermark=prior_max_event_id,
        )
        return ExportResult(
            bucket=bucket,
            prefix=norm_prefix,
            target_date=target_date,
            skipped_empty=True,
            previous_watermark=prior_max_event_id,
            run_id=run_id,
            dry_run=dry_run,
        )

    # Events are already ordered by (created_at, id); the last one is the new
    # watermark. We track both because UUID4 ids are not monotonically
    # ordered by creation time.
    last_event = events[-1]
    new_max_created = last_event.created_at
    if new_max_created.tzinfo is None:
        new_max_created = new_max_created.replace(tzinfo=timezone.utc)
    new_watermark = str(last_event.id)

    object_key = f"{_partition_path(norm_prefix, target_date)}events-{run_id}.ndjson.gz"
    payload_bytes = _write_gzip_ndjson(events)

    if dry_run:
        log.info(
            "audit_export.dry_run",
            bucket=bucket,
            key=object_key,
            events=len(events),
            bytes=len(payload_bytes),
        )
        return ExportResult(
            bucket=bucket,
            prefix=norm_prefix,
            target_date=target_date,
            events_exported=len(events),
            s3_key=object_key,
            dry_run=True,
            run_id=run_id,
            previous_watermark=prior_max_event_id,
            new_watermark=new_watermark,
            extras={"bytes": len(payload_bytes)},
        )

    # Default S3-managed encryption (SSE-S3). KMS is a follow-up — see X.10.
    client.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=payload_bytes,
        ContentType="application/x-ndjson",
        ContentEncoding="gzip",
        ServerSideEncryption="AES256",
    )

    new_ledger = {
        "date": target_date.isoformat(),
        "max_event_id": new_watermark,
        "max_created_at": new_max_created.isoformat(),
        "events_exported_total": prior_ledger.get("events_exported_total", 0) + len(events),
        "last_run_id": run_id,
        "last_run_at": datetime.now(tz=timezone.utc).isoformat(),
        "last_object_key": object_key,
    }
    client.put_object(
        Bucket=bucket,
        Key=ledger_key,
        Body=json.dumps(new_ledger, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )

    log.info(
        "audit_export.complete",
        bucket=bucket,
        key=object_key,
        events=len(events),
        bytes=len(payload_bytes),
        target_date=target_date.isoformat(),
        run_id=run_id,
    )

    return ExportResult(
        bucket=bucket,
        prefix=norm_prefix,
        target_date=target_date,
        events_exported=len(events),
        s3_key=object_key,
        run_id=run_id,
        previous_watermark=prior_max_event_id,
        new_watermark=new_watermark,
        extras={"bytes": len(payload_bytes)},
    )


async def run_daily_export(
    target_date: date | None = None,
    *,
    dry_run: bool = False,
    s3_client=None,
) -> ExportResult:
    """
    Entry point for the scheduled job — exports yesterday (UTC) by default.

    Args:
        target_date: override the day to export (UTC). Defaults to yesterday.
        dry_run: log the plan without writing to S3.
        s3_client: optional pre-built boto3 client (used in tests).
    """
    if target_date is None:
        today = datetime.now(tz=timezone.utc).date()
        target_date = today - timedelta(days=1)

    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return await export_audit_events(
        start=start,
        end=end,
        bucket=settings.audit_export_s3_bucket or None,
        prefix=settings.audit_export_s3_prefix,
        dry_run=dry_run,
        s3_client=s3_client,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="workers.audit_export",
        description="Export audit_events rows to S3 (gzip NDJSON, date-partitioned).",
    )
    parser.add_argument(
        "--date",
        dest="target_date",
        type=lambda v: datetime.strptime(v, "%Y-%m-%d").date(),
        default=None,
        help="UTC date to export (YYYY-MM-DD). Defaults to yesterday.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan rows and log the plan, but do not write to S3.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = asyncio.run(
        run_daily_export(target_date=args.target_date, dry_run=args.dry_run)
    )
    print(json.dumps(result.to_dict(), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
