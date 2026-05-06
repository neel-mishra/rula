import pytest
from app.policy.action_policy import ActionPolicy, AgentAction, PolicyViolationError


@pytest.fixture
def policy() -> ActionPolicy:
    return ActionPolicy()


def test_write_draft_allowed(policy: ActionPolicy) -> None:
    policy.enforce(AgentAction.WRITE_DRAFT, "DraftAgent", "run_001")


def test_add_label_allowed(policy: ActionPolicy) -> None:
    policy.enforce(AgentAction.ADD_LABEL, "TriageAgent", "run_001")


def test_read_message_allowed(policy: ActionPolicy) -> None:
    policy.enforce(AgentAction.READ_MESSAGE, "OrchestratorAgent", "run_001")


def test_send_email_raises(policy: ActionPolicy) -> None:
    with pytest.raises(PolicyViolationError, match="send_email"):
        policy.enforce(AgentAction.SEND_EMAIL, "DraftAgent", "run_001")


def test_delete_message_raises(policy: ActionPolicy) -> None:
    with pytest.raises(PolicyViolationError, match="delete_message"):
        policy.enforce(AgentAction.DELETE_MESSAGE, "TriageAgent", "run_001")


def test_archive_message_raises(policy: ActionPolicy) -> None:
    with pytest.raises(PolicyViolationError, match="archive_message"):
        policy.enforce(AgentAction.ARCHIVE_MESSAGE, "OrchestratorAgent", "run_001")


def test_modify_contacts_raises(policy: ActionPolicy) -> None:
    with pytest.raises(PolicyViolationError, match="modify_contacts"):
        policy.enforce(AgentAction.MODIFY_CONTACTS, "AnyAgent", "run_001")
