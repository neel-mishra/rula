from __future__ import annotations
import json
from dataclasses import dataclass

from app.agents.base_agent import BaseAgent
from app.ingestion.normalizer import NormalizedMessage
from app.telemetry.events import TelemetryEmitter


@dataclass
class DraftAgentOutput:
    draft_body: str
    subject_line: str
    confidence: float
    # draft_only is always True in Phase 1; enforced by policy layer, not this agent.
    draft_only: bool = True


class DraftAgent(BaseAgent):
    def __init__(self, telemetry: TelemetryEmitter) -> None:
        from app.core.config import settings
        super().__init__(model=settings.llm_model_draft, telemetry=telemetry)

    def _build_system_prompt(self) -> str:
        return (
            "You are a professional email drafting assistant. Write a reply in the user's voice.\n\n"
            "Rules:\n"
            "- Match the tone of the original thread\n"
            "- Be concise and direct\n"
            "- Never promise actions the user hasn't confirmed\n"
            "- Always end with a clear next step or question\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"draft_body": "<full reply>", "subject_line": "<Re: ...>", "confidence": <0.0-1.0>}'
        )

    async def generate_draft(
        self,
        message: NormalizedMessage,
        thread_context: list[dict],
        workflow_run_id: str,
        user_id: str,
    ) -> DraftAgentOutput:
        # TODO: implement full thread context formatting - ICE-P1-005
        user_prompt = (
            f"Original email:\nFrom: {message.sender_name} <{message.sender_email}>\n"
            f"Subject: {message.subject}\n"
            f"Body: {message.body_preview}\n\n"
            "Please draft a reply."
        )
        raw = await self._call_llm(
            workflow_run_id=workflow_run_id,
            user_id=user_id,
            user_prompt=user_prompt,
            max_tokens=2048,
            input_data={"message_id": message.message_id},
        )
        try:
            parsed = json.loads(raw)
            return DraftAgentOutput(
                draft_body=parsed["draft_body"],
                subject_line=parsed["subject_line"],
                confidence=float(parsed["confidence"]),
            )
        except (json.JSONDecodeError, KeyError):
            return DraftAgentOutput(
                draft_body=raw,
                subject_line=f"Re: {message.subject}",
                confidence=0.50,
            )
