"""Load gold-eval samples from on-disk `.eml` / `.json` fixtures.

This is the no-OAuth path that lets nightly_eval score against real
inbox data the operator has dropped into a directory. It reuses the
same stratifier + scrubber that `gold_sample_extraction.py` would use
in the live-Gmail path so downstream consumers cannot tell the source
apart.

Idempotency is keyed on a content-hash stored in
`source_gmail_message_id` (prefixed `fixture:`) so re-running the
loader against the same directory produces zero new rows.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from typing import Any, TypedDict

import structlog
from sqlalchemy import select

from core.config import settings
from core.db import get_db_session
from core.gold_eval.scrubber import SCRUB_VERSION, scrub_email_for_gold
from core.gold_eval.stratifier import classify_stratum
from core.models.gold_sample import GoldFixtureType, GoldSample
from core.models.mailbox import Mailbox

log = structlog.get_logger(__name__)

_FIXTURE_PREFIX = "fixture:"
_DEFAULT_FIXTURE_TYPES: tuple[GoldFixtureType, ...] = (
    GoldFixtureType.TRIAGE,
    GoldFixtureType.DRAFT,
    GoldFixtureType.BRIEF,
    GoldFixtureType.MEMORY,
)


class FixtureJSON(TypedDict, total=False):
    """Schema for `.json` fixture files. Mirrors stratifier-friendly shape."""

    subject: str
    from_: str  # operator may write either "from" or "from_"
    to: str | list[str]
    body_text: str
    body_html: str
    received_at: str  # ISO-8601
    headers: dict[str, str] | list[dict[str, str]]


@dataclass
class LoadResult:
    persisted: int = 0
    skipped_existing: int = 0
    skipped_invalid: int = 0
    per_stratum: dict[str, int] = field(default_factory=dict)
    skip_reasons: list[dict[str, str]] = field(default_factory=list)
    files_seen: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_seen": self.files_seen,
            "persisted": self.persisted,
            "skipped_existing": self.skipped_existing,
            "skipped_invalid": self.skipped_invalid,
            "per_stratum": self.per_stratum,
            "skip_reasons": self.skip_reasons,
        }


# ── Parsing ────────────────────────────────────────────────────────────────


def _parse_eml(path: Path) -> dict[str, Any]:
    """Parse a `.eml` into the internal dict shape stratifier+scrubber expect."""
    with path.open("rb") as fh:
        msg: EmailMessage = BytesParser(policy=policy.default).parse(fh)

    headers_list: list[dict[str, str]] = [
        {"name": k, "value": str(v)} for k, v in msg.items()
    ]

    body_text = ""
    body_html = ""
    parts_meta: list[dict[str, Any]] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            filename = part.get_filename() or ""
            if filename or ctype in ("text/calendar", "application/ics"):
                parts_meta.append({"mimeType": ctype, "filename": filename})
            if ctype == "text/plain" and not body_text:
                body_text = part.get_content() if isinstance(part.get_content(), str) else ""
            elif ctype == "text/html" and not body_html:
                body_html = part.get_content() if isinstance(part.get_content(), str) else ""
    else:
        ctype = (msg.get_content_type() or "").lower()
        content = msg.get_content() if isinstance(msg.get_content(), str) else ""
        if ctype == "text/html":
            body_html = content
        else:
            body_text = content

    sender = msg.get("From", "") or ""
    from_name = ""
    if "<" in sender and ">" in sender:
        from_name = sender.split("<", 1)[0].strip().strip('"')

    received_at = msg.get("Date", "") or ""
    subject = msg.get("Subject", "") or ""

    return {
        "id": _FIXTURE_PREFIX + path.name,
        "subject": subject,
        "from_name": from_name,
        "snippet": (body_text or _strip_html(body_html))[:200],
        "body_text": body_text,
        "body_html": body_html,
        "received_at": received_at,
        "payload": {"headers": headers_list, "parts": parts_meta},
        "headers": headers_list,
    }


def _parse_json(path: Path) -> dict[str, Any]:
    """Parse a fixture JSON into the same internal shape as `_parse_eml`."""
    with path.open("rb") as fh:
        raw: dict[str, Any] = json.load(fh)

    sender = raw.get("from") or raw.get("from_") or ""
    to = raw.get("to") or ""
    if isinstance(to, list):
        to_str = ", ".join(to)
    else:
        to_str = str(to)

    raw_headers = raw.get("headers") or {}
    if isinstance(raw_headers, dict):
        headers_list = [{"name": k, "value": v} for k, v in raw_headers.items()]
    else:
        headers_list = list(raw_headers)

    # Ensure From/To are present in the headers list — stratifier reads them there.
    have_names = {h.get("name", "").lower() for h in headers_list}
    if sender and "from" not in have_names:
        headers_list.append({"name": "From", "value": sender})
    if to_str and "to" not in have_names:
        headers_list.append({"name": "To", "value": to_str})

    body_text = raw.get("body_text") or ""
    body_html = raw.get("body_html") or ""

    from_name = ""
    if "<" in sender and ">" in sender:
        from_name = sender.split("<", 1)[0].strip().strip('"')

    return {
        "id": _FIXTURE_PREFIX + path.name,
        "subject": raw.get("subject", "") or "",
        "from_name": from_name,
        "snippet": (body_text or _strip_html(body_html))[:200],
        "body_text": body_text,
        "body_html": body_html,
        "received_at": raw.get("received_at", "") or "",
        "payload": {"headers": headers_list, "parts": []},
        "headers": headers_list,
    }


def _strip_html(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def _content_hash(internal: dict[str, Any]) -> str:
    """Stable hash for idempotency — survives scrubbing because it uses raw."""
    parts = [
        internal.get("subject") or "",
        internal.get("from_name") or "",
        (internal.get("body_text") or internal.get("body_html") or "")[:4000],
    ]
    h = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{_FIXTURE_PREFIX}{h[:32]}"


# ── Persistence ────────────────────────────────────────────────────────────


async def load_fixtures_from_dir(
    fixtures_dir: Path,
    mailbox_id: uuid.UUID,
    *,
    fixture_types: list[GoldFixtureType] | None = None,
    session_factory: Any = None,
) -> LoadResult:
    """Walk `fixtures_dir`, ingest every .eml/.json into GoldSample rows."""
    fixture_types = fixture_types or list(_DEFAULT_FIXTURE_TYPES)
    session_cm = session_factory or get_db_session

    result = LoadResult()
    fixtures_dir = Path(fixtures_dir)
    if not fixtures_dir.exists() or not fixtures_dir.is_dir():
        result.skip_reasons.append(
            {"file": str(fixtures_dir), "reason": "directory not found"}
        )
        return result

    files = sorted(
        [p for p in fixtures_dir.rglob("*") if p.suffix.lower() in (".eml", ".json")]
    )
    result.files_seen = len(files)

    async with session_cm() as session:
        mailbox = await session.get(Mailbox, mailbox_id)
        if not mailbox:
            result.skip_reasons.append(
                {"file": "<mailbox>", "reason": f"mailbox {mailbox_id} not found"}
            )
            return result
        mailbox_user_id = mailbox.user_id

        for path in files:
            try:
                if path.suffix.lower() == ".eml":
                    internal = _parse_eml(path)
                else:
                    internal = _parse_json(path)
            except Exception as exc:
                result.skipped_invalid += 1
                result.skip_reasons.append({"file": path.name, "reason": f"parse: {exc}"})
                continue

            content_hash = _content_hash(internal)

            existing_q = await session.execute(
                select(GoldSample.id).where(
                    GoldSample.mailbox_id == mailbox_id,
                    GoldSample.source_gmail_message_id == content_hash,
                )
            )
            if existing_q.first() is not None:
                result.skipped_existing += 1
                continue

            stratum = classify_stratum(internal, user_email=mailbox.gmail_email)
            try:
                scrubbed = scrub_email_for_gold(
                    internal, mailbox_salt=settings.gold_sample_name_hash_salt
                )
            except Exception as exc:
                result.skipped_invalid += 1
                result.skip_reasons.append(
                    {"file": path.name, "reason": f"scrub: {exc}"}
                )
                continue

            for fixture_type in fixture_types:
                session.add(
                    GoldSample(
                        id=uuid.uuid4(),
                        mailbox_id=mailbox_id,
                        user_id=mailbox_user_id,
                        fixture_type=fixture_type,
                        stratum=stratum,
                        source_gmail_message_id=content_hash,
                        raw_payload=internal,
                        scrubbed_payload=scrubbed,
                        scrub_version=SCRUB_VERSION,
                        consented_at=datetime.now(tz=timezone.utc),
                        is_active=True,
                    )
                )
                result.persisted += 1

            result.per_stratum[stratum.value] = (
                result.per_stratum.get(stratum.value, 0) + 1
            )

    log.info(
        "gold_fixture_loader.complete",
        mailbox_id=str(mailbox_id),
        **result.to_dict(),
    )
    return result


# ── CLI ────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m workers.gold_fixture_loader",
        description=(
            "Load gold-eval samples from .eml/.json fixtures on disk. "
            "Idempotent: re-running against the same directory inserts 0 new rows."
        ),
    )
    parser.add_argument(
        "--dir", required=True,
        help="Directory containing .eml and/or .json fixture files (recursively walked).",
    )
    parser.add_argument(
        "--mailbox-id", required=True,
        help="UUID of the Mailbox row these fixtures should be attributed to.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = asyncio.run(
        load_fixtures_from_dir(Path(args.dir), uuid.UUID(args.mailbox_id))
    )
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0 if result.skipped_invalid == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
