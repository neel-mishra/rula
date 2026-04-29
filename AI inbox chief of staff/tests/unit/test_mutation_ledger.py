"""Unit tests for mutation ledger and undo mechanics."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.models.mutation_ledger import MutationLedger, MutationStatus, MutationType


class TestMutationLedger:
    def _make_ledger(self, **kwargs) -> MutationLedger:
        defaults = dict(
            id=uuid.uuid4(),
            email_id=uuid.uuid4(),
            mailbox_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            mutation_type=MutationType.LABEL_ADD,
            status=MutationStatus.APPLIED,
            prior_state={"labels": ["INBOX"]},
            new_state={"labels": ["INBOX", "next_brief_label_id"]},
            label_id="next_brief_label_id",
            reason_trace="Newsletter detected; confidence=0.95",
            policy_version="v1",
            undo_token=secrets.token_urlsafe(32),
            undo_expires_at=datetime.now(tz=timezone.utc) + timedelta(days=7),
            correlation_id=str(uuid.uuid4()),
        )
        defaults.update(kwargs)
        return MutationLedger(**defaults)

    def test_ledger_has_all_required_fields(self):
        ledger = self._make_ledger()
        assert ledger.prior_state is not None
        assert ledger.new_state is not None
        assert ledger.reason_trace is not None
        assert ledger.policy_version is not None
        assert ledger.undo_token is not None
        assert ledger.undo_expires_at is not None
        assert ledger.correlation_id is not None

    def test_undo_token_is_unique(self):
        tokens = {secrets.token_urlsafe(32) for _ in range(100)}
        assert len(tokens) == 100  # All unique

    def test_undo_window_not_expired(self):
        ledger = self._make_ledger()
        now = datetime.now(tz=timezone.utc)
        assert now < ledger.undo_expires_at

    def test_expired_ledger_detection(self):
        ledger = self._make_ledger(
            undo_expires_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1)
        )
        now = datetime.now(tz=timezone.utc)
        assert now > ledger.undo_expires_at  # expired

    def test_prior_and_new_state_differ(self):
        ledger = self._make_ledger()
        assert ledger.prior_state != ledger.new_state

    def test_status_transitions(self):
        ledger = self._make_ledger(status=MutationStatus.PENDING)
        assert ledger.status == MutationStatus.PENDING
        ledger.status = MutationStatus.APPLIED
        assert ledger.status == MutationStatus.APPLIED
        ledger.status = MutationStatus.UNDONE
        assert ledger.status == MutationStatus.UNDONE


class TestMutationGuardThresholds:
    """Confirm confidence threshold enforcement — no mutation below medium threshold."""

    @pytest.mark.asyncio
    async def test_low_confidence_blocks_mutation(self):
        from subagents.safety import MutationGuardAgent
        from core.schemas.contracts import MutationGuardTask

        agent = MutationGuardAgent()
        task = MutationGuardTask(
            user_id=uuid.uuid4(),
            mailbox_id=uuid.uuid4(),
            correlation_id="test-corr",
            policy_version="v1",
            email_id=uuid.uuid4(),
            mutation_type="label_add",
            confidence=0.50,  # Below medium threshold (0.70)
            reason_trace="Low confidence classification",
        )
        response = await agent.run(task)
        assert response.ok is True
        assert response.payload.allowed is False
        assert response.payload.block_reason is not None

    @pytest.mark.asyncio
    async def test_high_confidence_allows_mutation(self):
        from subagents.safety import MutationGuardAgent
        from core.schemas.contracts import MutationGuardTask

        agent = MutationGuardAgent()
        task = MutationGuardTask(
            user_id=uuid.uuid4(),
            mailbox_id=uuid.uuid4(),
            correlation_id="test-corr",
            policy_version="v1",
            email_id=uuid.uuid4(),
            mutation_type="label_add",
            confidence=0.95,  # Above high threshold
            reason_trace="High confidence newsletter",
        )
        response = await agent.run(task)
        assert response.ok is True
        assert response.payload.allowed is True
        assert response.payload.undo_token is not None
        assert len(response.payload.undo_token) > 20
