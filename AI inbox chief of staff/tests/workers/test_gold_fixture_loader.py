"""Tests for `workers.gold_fixture_loader`."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio

from core.models.gold_sample import GoldSample, GoldStratum
from core.models.mailbox import Mailbox
from core.models.user import User
from workers.gold_fixture_loader import (
    LoadResult,
    _content_hash,
    _parse_eml,
    _parse_json,
    load_fixtures_from_dir,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "gold_emails"


@pytest_asyncio.fixture
async def seeded_mailbox(db_session) -> Mailbox:
    user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="neel@test.com",
        display_name="Neel",
    )
    mailbox = Mailbox(
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        user_id=user.id,
        gmail_email="user@example.com",
        gmail_user_id="work_user_123",
        is_active=True,
        is_connected=True,
    )
    db_session.add(user)
    db_session.add(mailbox)
    await db_session.flush()
    return mailbox


@pytest.fixture
def session_factory(db_session):
    """Yield the same `db_session` from the loader's session_factory call."""

    @asynccontextmanager
    async def _factory():
        yield db_session

    return _factory


# ── Pure parsing checks ────────────────────────────────────────────────────


def test_parse_eml_extracts_headers_and_body():
    parsed = _parse_eml(FIXTURES_DIR / "newsletter.eml")
    assert parsed["subject"] == "Your weekly digest"
    header_names = {h["name"].lower() for h in parsed["headers"]}
    assert "list-unsubscribe" in header_names
    assert "Click here" in parsed["body_text"]


def test_parse_json_normalizes_from_and_to_into_headers():
    parsed = _parse_json(FIXTURES_DIR / "action_required.json")
    header_names = {h["name"].lower() for h in parsed["headers"]}
    assert "from" in header_names
    assert "to" in header_names
    assert parsed["body_text"].startswith("Could you review")


def test_content_hash_is_stable_and_distinct():
    a = _parse_eml(FIXTURES_DIR / "newsletter.eml")
    b = _parse_eml(FIXTURES_DIR / "direct_reply.eml")
    assert _content_hash(a) == _content_hash(a)
    assert _content_hash(a) != _content_hash(b)


# ── DB-backed loader tests ─────────────────────────────────────────────────


async def test_loads_n_fixtures_persists_n_rows_per_fixture_type(
    db_session, seeded_mailbox, session_factory
):
    result = await load_fixtures_from_dir(
        FIXTURES_DIR,
        seeded_mailbox.id,
        session_factory=session_factory,
    )

    # N fixture files * 4 default fixture types
    expected_files = sum(
        1 for p in FIXTURES_DIR.rglob("*") if p.suffix.lower() in (".eml", ".json")
    )
    assert isinstance(result, LoadResult)
    assert result.files_seen == expected_files
    assert result.persisted == expected_files * 4
    assert result.skipped_existing == 0
    assert result.skipped_invalid == 0

    from sqlalchemy import select
    rows = (
        await db_session.execute(
            select(GoldSample).where(GoldSample.mailbox_id == seeded_mailbox.id)
        )
    ).scalars().all()
    assert len(rows) == expected_files * 4


async def test_idempotent_rerun_inserts_zero(
    db_session, seeded_mailbox, session_factory
):
    first = await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    assert first.persisted > 0
    await db_session.flush()

    second = await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    assert second.persisted == 0
    assert second.skipped_existing == first.files_seen


async def test_mixed_eml_and_json_both_load(
    db_session, seeded_mailbox, session_factory
):
    result = await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    # Confirm both file types contributed by checking distinct source ids.
    from sqlalchemy import select
    rows = (
        await db_session.execute(
            select(GoldSample.source_gmail_message_id).where(
                GoldSample.mailbox_id == seeded_mailbox.id
            )
        )
    ).all()
    distinct_ids = {r[0] for r in rows}
    expected_files = sum(
        1 for p in FIXTURES_DIR.rglob("*") if p.suffix.lower() in (".eml", ".json")
    )
    assert len(distinct_ids) == expected_files  # one per source file


async def test_stratification_assigns_expected_labels(
    db_session, seeded_mailbox, session_factory
):
    await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    from sqlalchemy import select
    rows = (
        await db_session.execute(
            select(GoldSample).where(GoldSample.mailbox_id == seeded_mailbox.id)
        )
    ).scalars().all()

    by_subject: dict[str, GoldStratum] = {}
    for r in rows:
        subject = (r.raw_payload or {}).get("subject", "")
        by_subject[subject] = r.stratum

    assert by_subject["Your weekly digest"] == GoldStratum.NEWSLETTER
    assert by_subject["Re: Project plan"] == GoldStratum.DIRECT_REPLY
    assert by_subject["Quick question about the spec"] == GoldStratum.ACTION_REQUIRED
    assert by_subject["Your receipt for order #1234"] == GoldStratum.UPDATE


async def test_missing_mailbox_returns_skip_reason(db_session, session_factory):
    result = await load_fixtures_from_dir(
        FIXTURES_DIR,
        uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        session_factory=session_factory,
    )
    assert result.persisted == 0
    assert any("mailbox" in r["reason"] for r in result.skip_reasons)


async def test_missing_directory_returns_skip_reason(seeded_mailbox, session_factory):
    result = await load_fixtures_from_dir(
        Path("/no/such/dir"), seeded_mailbox.id, session_factory=session_factory,
    )
    assert result.files_seen == 0
    assert result.persisted == 0
    assert any("directory not found" in r["reason"] for r in result.skip_reasons)
