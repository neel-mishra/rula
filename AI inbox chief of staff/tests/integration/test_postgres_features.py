"""
Postgres-specific integration tests.
These tests exercise features that only work on real Postgres (not SQLite):
  - pgvector embedding insert + cosine similarity
  - JSONB operators and indexing
  - Enum types (TriageOutcome, DraftStatus, etc.)
  - Cascading deletes (user → mailbox → email → triage/draft)
  - Audit event immutability trigger

Skipped automatically when running against SQLite.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text, delete

from core.models.audit import AuditEvent
from core.models.brief import Brief, BriefItem, BriefStatus, BriefWindow
from core.models.draft import Draft, DraftStatus
from core.models.email import Email
from core.models.mailbox import Mailbox
from core.models.memory import Memory, MemoryScope, MemoryType
from core.models.mutation_ledger import MutationLedger, MutationStatus, MutationType
from core.models.triage import TriageDecision, TriageMethod, TriageOutcome
from core.models.user import User

_is_postgres = "postgresql" in os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _is_postgres, reason="Requires real Postgres (pgvector, enums, triggers)"
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def user(db_session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Integration Test User",
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.fixture
async def mailbox(db_session, user) -> Mailbox:
    mb = Mailbox(
        id=uuid.uuid4(),
        user_id=user.id,
        gmail_email=f"test-{uuid.uuid4().hex[:8]}@gmail.com",
        gmail_user_id=f"user_{uuid.uuid4().hex[:8]}",
        is_active=True,
        is_connected=True,
    )
    db_session.add(mb)
    await db_session.flush()
    return mb


@pytest.fixture
async def email(db_session, user, mailbox) -> Email:
    e = Email(
        id=uuid.uuid4(),
        mailbox_id=mailbox.id,
        user_id=user.id,
        gmail_message_id=f"msg_{uuid.uuid4().hex[:8]}",
        gmail_thread_id=f"thread_{uuid.uuid4().hex[:8]}",
        subject="Integration test email",
        from_address="sender@example.com",
        to_addresses=["recipient@example.com"],
        body_text="This is a test email body for integration testing.",
        features={"is_newsletter": False, "is_reply": True},
    )
    db_session.add(e)
    await db_session.flush()
    return e


# ── pgvector Embedding Tests ────────────────────────────────────────────────

class TestPgvectorEmbeddings:
    async def test_insert_email_embedding(self, db_session, email):
        """Embedding column accepts a 1536-dim vector."""
        embedding = [0.01 * i for i in range(1536)]
        await db_session.execute(
            text("UPDATE emails SET embedding = :emb WHERE id = :id"),
            {"emb": str(embedding), "id": str(email.id)},
        )
        await db_session.flush()

        row = await db_session.execute(
            text("SELECT embedding IS NOT NULL as has_emb FROM emails WHERE id = :id"),
            {"id": str(email.id)},
        )
        assert row.scalar() is True

    async def test_cosine_similarity_search(self, db_session, user, mailbox):
        """Cosine distance ordering returns nearest neighbor correctly."""
        emails = []
        for i in range(3):
            e = Email(
                id=uuid.uuid4(),
                mailbox_id=mailbox.id,
                user_id=user.id,
                gmail_message_id=f"sim_msg_{i}_{uuid.uuid4().hex[:6]}",
                gmail_thread_id=f"sim_thread_{i}",
                subject=f"Similarity test {i}",
                from_address="test@example.com",
                features={},
            )
            db_session.add(e)
            emails.append(e)
        await db_session.flush()

        # Set embeddings: e0 = [1,0,...], e1 = [0.9,0.1,...], e2 = [0,1,...]
        base = [0.0] * 1536
        for idx, vals in [(0, (1.0, 0.0)), (1, (0.9, 0.1)), (2, (0.0, 1.0))]:
            emb = base.copy()
            emb[0], emb[1] = vals
            await db_session.execute(
                text("UPDATE emails SET embedding = :emb WHERE id = :id"),
                {"emb": str(emb), "id": str(emails[idx].id)},
            )
        await db_session.flush()

        # Query: find nearest to [1,0,...] — should return e0 first, then e1
        query_emb = base.copy()
        query_emb[0] = 1.0
        result = await db_session.execute(
            text(
                "SELECT id, embedding <=> :qemb AS distance FROM emails "
                "WHERE mailbox_id = :mb AND embedding IS NOT NULL "
                "ORDER BY distance LIMIT 3"
            ),
            {"qemb": str(query_emb), "mb": str(mailbox.id)},
        )
        rows = result.all()
        assert len(rows) == 3
        assert rows[0][0] == emails[0].id  # exact match first
        assert rows[1][0] == emails[1].id  # close second
        assert rows[2][0] == emails[2].id  # orthogonal last
        assert rows[0][1] < rows[1][1] < rows[2][1]  # distances ascending

    async def test_memory_embedding_insert(self, db_session, user):
        """Memory embedding column works."""
        mem = Memory(
            id=uuid.uuid4(),
            user_id=user.id,
            scope=MemoryScope.USER_GLOBAL,
            applies_to_all_mailboxes=True,
            memory_type=MemoryType.PREFERENCE,
            content="Test memory with embedding",
            structured_data={},
            source="test",
            confidence=0.9,
        )
        db_session.add(mem)
        await db_session.flush()

        emb = [0.001 * i for i in range(1536)]
        await db_session.execute(
            text("UPDATE memories SET embedding = :emb WHERE id = :id"),
            {"emb": str(emb), "id": str(mem.id)},
        )
        await db_session.flush()

        row = await db_session.execute(
            text("SELECT embedding IS NOT NULL FROM memories WHERE id = :id"),
            {"id": str(mem.id)},
        )
        assert row.scalar() is True


# ── JSONB Tests ──────────────────────────────────────────────────────────────

class TestJsonbOperations:
    async def test_jsonb_features_query(self, db_session, user, mailbox):
        """JSONB features column supports containment queries."""
        e = Email(
            id=uuid.uuid4(),
            mailbox_id=mailbox.id,
            user_id=user.id,
            gmail_message_id=f"jsonb_msg_{uuid.uuid4().hex[:6]}",
            gmail_thread_id="jsonb_thread",
            features={"is_newsletter": True, "list_unsubscribe": True, "sender_score": 0.3},
        )
        db_session.add(e)
        await db_session.flush()

        result = await db_session.execute(
            text(
                "SELECT id FROM emails WHERE features @> :filter AND mailbox_id = :mb"
            ),
            {"filter": '{"is_newsletter": true}', "mb": str(mailbox.id)},
        )
        rows = result.scalars().all()
        assert e.id in rows

    async def test_jsonb_nested_update(self, db_session, user, mailbox):
        """JSONB path update via Postgres jsonb_set."""
        e = Email(
            id=uuid.uuid4(),
            mailbox_id=mailbox.id,
            user_id=user.id,
            gmail_message_id=f"jsonb_upd_{uuid.uuid4().hex[:6]}",
            gmail_thread_id="jsonb_upd_thread",
            features={"sender_score": 0.5},
        )
        db_session.add(e)
        await db_session.flush()

        await db_session.execute(
            text(
                "UPDATE emails SET features = jsonb_set(features, '{sender_score}', '0.8') "
                "WHERE id = :id"
            ),
            {"id": str(e.id)},
        )
        await db_session.flush()

        await db_session.refresh(e)
        assert e.features["sender_score"] == 0.8


# ── Enum Tests ───────────────────────────────────────────────────────────────

class TestPostgresEnums:
    async def test_triage_outcome_enum_values(self, db_session, email, user, mailbox):
        """All TriageOutcome enum values round-trip through Postgres."""
        for outcome in TriageOutcome:
            td = TriageDecision(
                id=uuid.uuid4(),
                email_id=email.id,
                mailbox_id=mailbox.id,
                user_id=user.id,
                outcome=outcome,
                confidence=0.9,
                method=TriageMethod.DETERMINISTIC,
                policy_version="v1",
                correlation_id=str(uuid.uuid4()),
            )
            db_session.add(td)
            await db_session.flush()

            loaded = await db_session.get(TriageDecision, td.id)
            assert loaded.outcome == outcome

            await db_session.delete(loaded)
            await db_session.flush()

    async def test_draft_status_enum(self, db_session, email, user, mailbox):
        """DraftStatus enum round-trips."""
        d = Draft(
            id=uuid.uuid4(),
            email_id=email.id,
            mailbox_id=mailbox.id,
            user_id=user.id,
            status=DraftStatus.GENERATED,
            draft_body="Test draft",
            subject_line="Re: Test",
            grounding_score=0.85,
            policy_version="v1",
            correlation_id=str(uuid.uuid4()),
        )
        db_session.add(d)
        await db_session.flush()

        loaded = await db_session.get(Draft, d.id)
        assert loaded.status == DraftStatus.GENERATED

        loaded.status = DraftStatus.ACCEPTED
        await db_session.flush()
        await db_session.refresh(loaded)
        assert loaded.status == DraftStatus.ACCEPTED

    async def test_brief_status_delivery_failed(self, db_session, user, mailbox):
        """The delivery_failed enum value (added in migration 002) works."""
        b = Brief(
            id=uuid.uuid4(),
            mailbox_id=mailbox.id,
            user_id=user.id,
            window=BriefWindow.MORNING,
            status=BriefStatus.DELIVERY_FAILED,
            policy_version="v1",
            correlation_id=str(uuid.uuid4()),
        )
        db_session.add(b)
        await db_session.flush()

        loaded = await db_session.get(Brief, b.id)
        assert loaded.status == BriefStatus.DELIVERY_FAILED


# ── Cascading Delete Tests ───────────────────────────────────────────────────

class TestCascadingDeletes:
    async def test_delete_user_cascades_all(self, db_session):
        """Deleting a user cascades to mailbox → email → triage → draft."""
        user = User(
            id=uuid.uuid4(),
            email=f"cascade-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Cascade Test",
        )
        db_session.add(user)
        await db_session.flush()

        mailbox = Mailbox(
            id=uuid.uuid4(),
            user_id=user.id,
            gmail_email=f"cascade-{uuid.uuid4().hex[:8]}@gmail.com",
            gmail_user_id=f"cascade_{uuid.uuid4().hex[:8]}",
        )
        db_session.add(mailbox)
        await db_session.flush()

        email = Email(
            id=uuid.uuid4(),
            mailbox_id=mailbox.id,
            user_id=user.id,
            gmail_message_id=f"cascade_msg_{uuid.uuid4().hex[:6]}",
            gmail_thread_id="cascade_thread",
            features={},
        )
        db_session.add(email)
        await db_session.flush()

        triage = TriageDecision(
            id=uuid.uuid4(),
            email_id=email.id,
            mailbox_id=mailbox.id,
            user_id=user.id,
            outcome=TriageOutcome.BRIEF_ONLY,
            confidence=0.8,
            method=TriageMethod.LLM,
            policy_version="v1",
            correlation_id=str(uuid.uuid4()),
        )
        draft = Draft(
            id=uuid.uuid4(),
            email_id=email.id,
            mailbox_id=mailbox.id,
            user_id=user.id,
            status=DraftStatus.GENERATED,
            draft_body="Cascade draft",
            subject_line="Re: Cascade",
            grounding_score=0.9,
            policy_version="v1",
            correlation_id=str(uuid.uuid4()),
        )
        memory = Memory(
            id=uuid.uuid4(),
            user_id=user.id,
            mailbox_id=mailbox.id,
            scope=MemoryScope.MAILBOX_SPECIFIC,
            applies_to_all_mailboxes=False,
            memory_type=MemoryType.POLICY,
            content="Cascade test memory",
            structured_data={},
            source="test",
            confidence=0.9,
        )
        db_session.add_all([triage, draft, memory])
        await db_session.flush()

        saved_ids = {
            "mailbox": mailbox.id,
            "email": email.id,
            "triage": triage.id,
            "draft": draft.id,
            "memory": memory.id,
        }

        await db_session.delete(user)
        await db_session.flush()

        assert await db_session.get(Mailbox, saved_ids["mailbox"]) is None
        assert await db_session.get(Email, saved_ids["email"]) is None
        assert await db_session.get(TriageDecision, saved_ids["triage"]) is None
        assert await db_session.get(Draft, saved_ids["draft"]) is None
        assert await db_session.get(Memory, saved_ids["memory"]) is None

    async def test_delete_mailbox_preserves_user(self, db_session):
        """Deleting a mailbox doesn't delete the user."""
        user = User(
            id=uuid.uuid4(),
            email=f"preserve-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Preserve Test",
        )
        db_session.add(user)
        await db_session.flush()

        mailbox = Mailbox(
            id=uuid.uuid4(),
            user_id=user.id,
            gmail_email=f"preserve-{uuid.uuid4().hex[:8]}@gmail.com",
            gmail_user_id=f"preserve_{uuid.uuid4().hex[:8]}",
        )
        db_session.add(mailbox)
        await db_session.flush()

        await db_session.delete(mailbox)
        await db_session.flush()

        loaded_user = await db_session.get(User, user.id)
        assert loaded_user is not None
        assert loaded_user.email == user.email


# ── Audit Immutability Trigger Test ──────────────────────────────────────────

class TestAuditImmutability:
    async def test_audit_event_insert_succeeds(self, db_session, user, mailbox):
        """Audit events can be inserted."""
        ae = AuditEvent(
            id=uuid.uuid4(),
            event_type="test.integration",
            actor="integration_test",
            user_id=user.id,
            mailbox_id=mailbox.id,
            correlation_id=str(uuid.uuid4()),
            payload={"test": True},
        )
        db_session.add(ae)
        await db_session.flush()

        loaded = await db_session.get(AuditEvent, ae.id)
        assert loaded is not None
        assert loaded.event_type == "test.integration"

    async def test_audit_event_update_blocked(self, db_session, user, mailbox):
        """Audit events cannot be updated (immutable trigger)."""
        ae = AuditEvent(
            id=uuid.uuid4(),
            event_type="test.immutable",
            actor="integration_test",
            user_id=user.id,
            mailbox_id=mailbox.id,
            correlation_id=str(uuid.uuid4()),
            payload={"original": True},
        )
        db_session.add(ae)
        await db_session.flush()

        with pytest.raises(Exception, match="(?i)immutable|cannot|update"):
            await db_session.execute(
                text(
                    "UPDATE audit_events SET event_type = 'tampered' WHERE id = :id"
                ),
                {"id": str(ae.id)},
            )

    async def test_audit_event_delete_blocked(self, db_session, user, mailbox):
        """Audit events cannot be deleted (immutable trigger)."""
        ae = AuditEvent(
            id=uuid.uuid4(),
            event_type="test.nodelete",
            actor="integration_test",
            user_id=user.id,
            mailbox_id=mailbox.id,
            correlation_id=str(uuid.uuid4()),
            payload={},
        )
        db_session.add(ae)
        await db_session.flush()

        with pytest.raises(Exception, match="(?i)immutable|cannot|delete"):
            await db_session.execute(
                text("DELETE FROM audit_events WHERE id = :id"),
                {"id": str(ae.id)},
            )


# ── Mutation Ledger Tests ────────────────────────────────────────────────────

class TestMutationLedger:
    async def test_mutation_undo_token_unique(self, db_session, email, user, mailbox):
        """Undo tokens must be unique across mutations."""
        token = str(uuid.uuid4())
        m1 = MutationLedger(
            id=uuid.uuid4(),
            email_id=email.id,
            mailbox_id=mailbox.id,
            user_id=user.id,
            mutation_type=MutationType.ARCHIVE,
            status=MutationStatus.APPLIED,
            prior_state={"labels": ["INBOX"]},
            new_state={"labels": []},
            confidence=0.9,
            reason_trace="test",
            undo_token=token,
            policy_version="v1",
            correlation_id=str(uuid.uuid4()),
        )
        db_session.add(m1)
        await db_session.flush()

        from sqlalchemy.exc import IntegrityError

        m2 = MutationLedger(
            id=uuid.uuid4(),
            email_id=email.id,
            mailbox_id=mailbox.id,
            user_id=user.id,
            mutation_type=MutationType.LABEL,
            status=MutationStatus.APPLIED,
            prior_state={},
            new_state={},
            confidence=0.8,
            reason_trace="test dupe",
            undo_token=token,
            policy_version="v1",
            correlation_id=str(uuid.uuid4()),
        )
        db_session.add(m2)
        with pytest.raises(IntegrityError):
            await db_session.flush()


# ── ARRAY Column Tests ───────────────────────────────────────────────────────

class TestArrayColumns:
    async def test_to_addresses_array_roundtrip(self, db_session, user, mailbox):
        """ARRAY(String) columns store and retrieve lists correctly."""
        e = Email(
            id=uuid.uuid4(),
            mailbox_id=mailbox.id,
            user_id=user.id,
            gmail_message_id=f"arr_msg_{uuid.uuid4().hex[:6]}",
            gmail_thread_id="arr_thread",
            to_addresses=["alice@example.com", "bob@example.com"],
            cc_addresses=["charlie@example.com"],
            features={},
        )
        db_session.add(e)
        await db_session.flush()

        loaded = await db_session.get(Email, e.id)
        assert loaded.to_addresses == ["alice@example.com", "bob@example.com"]
        assert loaded.cc_addresses == ["charlie@example.com"]

    async def test_array_contains_query(self, db_session, user, mailbox):
        """Postgres array containment operator works."""
        e = Email(
            id=uuid.uuid4(),
            mailbox_id=mailbox.id,
            user_id=user.id,
            gmail_message_id=f"arr_q_{uuid.uuid4().hex[:6]}",
            gmail_thread_id="arr_q_thread",
            to_addresses=["target@example.com", "other@example.com"],
            features={},
        )
        db_session.add(e)
        await db_session.flush()

        result = await db_session.execute(
            text(
                "SELECT id FROM emails WHERE to_addresses @> ARRAY[:addr]::text[] "
                "AND mailbox_id = :mb"
            ),
            {"addr": "target@example.com", "mb": str(mailbox.id)},
        )
        rows = result.scalars().all()
        assert e.id in rows


# ── Migration Validation ─────────────────────────────────────────────────────

class TestMigrationArtifacts:
    async def test_pgvector_extension_exists(self, db_session):
        """pgvector extension is installed."""
        result = await db_session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        assert result.scalar() == "vector"

    async def test_ivfflat_indexes_exist(self, db_session):
        """IVFFlat embedding indexes are created."""
        result = await db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE indexname IN ('ix_memories_embedding', 'ix_emails_embedding')"
            )
        )
        indexes = {row[0] for row in result.all()}
        assert "ix_memories_embedding" in indexes
        assert "ix_emails_embedding" in indexes

    async def test_activation_mode_column_exists(self, db_session):
        """Migration 002 added activation_mode with default 'shadow'."""
        result = await db_session.execute(
            text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'mailboxes' AND column_name = 'activation_mode'"
            )
        )
        default = result.scalar()
        assert default is not None
        assert "shadow" in default
