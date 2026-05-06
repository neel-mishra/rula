from __future__ import annotations
from enum import Enum


class AgentAction(str, Enum):
    WRITE_DRAFT = "write_draft"
    ADD_LABEL = "add_label"
    READ_MESSAGE = "read_message"
    # Blocked in all Prototype phases:
    SEND_EMAIL = "send_email"
    DELETE_MESSAGE = "delete_message"
    ARCHIVE_MESSAGE = "archive_message"
    MODIFY_CONTACTS = "modify_contacts"


ALLOWED_ACTIONS: frozenset[AgentAction] = frozenset({
    AgentAction.WRITE_DRAFT,
    AgentAction.ADD_LABEL,
    AgentAction.READ_MESSAGE,
})


class PolicyViolationError(Exception):
    """Raised when an agent attempts an action outside ALLOWED_ACTIONS."""


class ActionPolicy:
    """Enforces the Phase 1 action matrix. Stateless; safe to share across requests."""

    def enforce(self, action: AgentAction, agent_name: str, workflow_run_id: str) -> None:
        """
        Check that `action` is permitted. Always emits an audit event (allow or deny).
        Raises PolicyViolationError for blocked actions.
        """
        if action not in ALLOWED_ACTIONS:
            raise PolicyViolationError(
                f"Agent '{agent_name}' attempted blocked action '{action.value}' "
                f"in workflow {workflow_run_id}"
            )

    async def async_enforce(
        self,
        action: AgentAction,
        agent_name: str,
        workflow_run_id: str,
        user_id: str,
        db=None,
    ) -> None:
        """Async enforce: check policy AND emit audit event to DB."""
        outcome = "allowed" if action in ALLOWED_ACTIONS else "blocked"

        if db is not None:
            from app.repositories.audit_repo import AuditRepository
            audit_repo = AuditRepository(db)
            await audit_repo.create(
                user_id=user_id,
                event_type="policy_check",
                action=action.value,
                outcome=outcome,
                agent_name=agent_name,
                workflow_run_id=workflow_run_id,
                metadata={"allowed_actions": [a.value for a in ALLOWED_ACTIONS]},
            )

        if action not in ALLOWED_ACTIONS:
            raise PolicyViolationError(
                f"Agent '{agent_name}' attempted blocked action '{action.value}' "
                f"in workflow {workflow_run_id}"
            )
