import pytest
from unittest.mock import AsyncMock, patch
import json

from app.agents.triage_agent import TriageAgent, TriageAgentOutput
from app.ingestion.normalizer import NormalizedMessage
from tests.conftest import sample_message, mock_telemetry


@pytest.mark.asyncio
async def test_triage_urgent_from_llm(mock_telemetry, sample_message):
    agent = TriageAgent(telemetry=mock_telemetry)
    llm_response = json.dumps({
        "priority": "urgent",
        "confidence": 0.92,
        "rationale": "Deadline keyword and VIP sender",
        "labels": ["urgent"],
    })
    with patch.object(agent, "_call_llm", new=AsyncMock(return_value=llm_response)):
        result = await agent.triage(sample_message, "run_001", "user_001")
    assert result.priority == "urgent"
    assert result.confidence == 0.92


@pytest.mark.asyncio
async def test_triage_falls_back_on_low_confidence(mock_telemetry, sample_message):
    agent = TriageAgent(telemetry=mock_telemetry)
    llm_response = json.dumps({
        "priority": "archive",
        "confidence": 0.40,  # below fallback threshold
        "rationale": "Seems low priority",
        "labels": [],
    })
    with patch.object(agent, "_call_llm", new=AsyncMock(return_value=llm_response)):
        result = await agent.triage(sample_message, "run_001", "user_001")
    # Deterministic fallback should fire due to "urgent" and "action required" in body
    assert result.priority == "urgent"


@pytest.mark.asyncio
async def test_triage_falls_back_on_invalid_json(mock_telemetry, sample_message):
    agent = TriageAgent(telemetry=mock_telemetry)
    with patch.object(agent, "_call_llm", new=AsyncMock(return_value="not json at all")):
        result = await agent.triage(sample_message, "run_001", "user_001")
    assert result.priority in {"urgent", "normal"}  # deterministic fallback
