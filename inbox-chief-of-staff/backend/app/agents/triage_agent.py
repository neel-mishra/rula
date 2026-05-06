from __future__ import annotations
import json
from dataclasses import dataclass

from app.agents.base_agent import BaseAgent
from app.ingestion.normalizer import NormalizedMessage
from app.telemetry.events import TelemetryEmitter


@dataclass
class TriageAgentOutput:
    priority: str          # urgent | normal | brief | archive
    confidence: float      # 0.0 – 1.0
    rationale: str
    labels: list[str]


DETERMINISTIC_URGENT_KEYWORDS = frozenset({
    "urgent", "asap", "immediately", "deadline", "critical", "action required",
    "time-sensitive", "overdue", "by eod", "by cob",
})


class TriageAgent(BaseAgent):
    CONFIDENCE_FALLBACK_THRESHOLD = 0.70

    def __init__(self, telemetry: TelemetryEmitter) -> None:
        from app.core.config import settings
        super().__init__(model=settings.llm_model_triage, telemetry=telemetry)

    def _build_system_prompt(self) -> str:
        return (
            "You are an email triage assistant. Classify the email into exactly one priority: "
            "urgent, normal, brief, or archive.\n\n"
            "Rules:\n"
            "- urgent: requires a response within hours; has a hard deadline or high-stakes request\n"
            "- normal: should be responded to within 1-2 days\n"
            "- brief: informational; no reply needed; suitable for digest summary\n"
            "- archive: newsletters, automated notifications, low-value bulk mail\n\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            '{"priority": "<urgent|normal|brief|archive>", "confidence": <0.0-1.0>, '
            '"rationale": "<one sentence>", "labels": ["<label>"]}'
        )

    async def triage(
        self,
        message: NormalizedMessage,
        workflow_run_id: str,
        user_id: str,
    ) -> TriageAgentOutput:
        user_prompt = (
            f"From: {message.sender_name} <{message.sender_email}>\n"
            f"Subject: {message.subject}\n"
            f"Preview: {message.body_preview}"
        )
        raw = await self._call_llm(
            workflow_run_id=workflow_run_id,
            user_id=user_id,
            user_prompt=user_prompt,
            input_data={"message_id": message.message_id, "subject": message.subject},
        )
        try:
            parsed = json.loads(raw)
            output = TriageAgentOutput(
                priority=parsed["priority"],
                confidence=float(parsed["confidence"]),
                rationale=parsed["rationale"],
                labels=parsed.get("labels", []),
            )
        except (json.JSONDecodeError, KeyError):
            output = self._deterministic_fallback(message)

        if output.confidence < self.CONFIDENCE_FALLBACK_THRESHOLD:
            output = self._deterministic_fallback(message)

        return output

    def _deterministic_fallback(self, message: NormalizedMessage) -> TriageAgentOutput:
        """Keyword + sender heuristic when LLM confidence is too low."""
        subject_lower = message.subject.lower()
        body_lower = message.body_preview.lower()
        combined = f"{subject_lower} {body_lower}"

        if any(kw in combined for kw in DETERMINISTIC_URGENT_KEYWORDS):
            return TriageAgentOutput(priority="urgent", confidence=0.60, rationale="Keyword match (fallback)", labels=[])
        return TriageAgentOutput(priority="normal", confidence=0.55, rationale="Default fallback", labels=[])
