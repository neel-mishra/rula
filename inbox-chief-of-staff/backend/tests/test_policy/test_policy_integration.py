"""Integration test: verify no send/delete can leak through to Gmail."""
import pytest
from app.policy.action_policy import ActionPolicy, AgentAction, PolicyViolationError


def test_all_blocked_actions_raise():
    """Every action outside ALLOWED_ACTIONS must raise PolicyViolationError."""
    policy = ActionPolicy()
    blocked = [
        AgentAction.SEND_EMAIL,
        AgentAction.DELETE_MESSAGE,
        AgentAction.ARCHIVE_MESSAGE,
        AgentAction.MODIFY_CONTACTS,
    ]
    for action in blocked:
        with pytest.raises(PolicyViolationError):
            policy.enforce(action, "TestAgent", "run_test")


def test_policy_error_message_includes_action_name():
    policy = ActionPolicy()
    with pytest.raises(PolicyViolationError, match="send_email"):
        policy.enforce(AgentAction.SEND_EMAIL, "TestAgent", "run_001")


def test_policy_error_message_includes_agent_name():
    policy = ActionPolicy()
    with pytest.raises(PolicyViolationError, match="DraftAgent"):
        policy.enforce(AgentAction.SEND_EMAIL, "DraftAgent", "run_001")
