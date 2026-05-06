from __future__ import annotations
import json
from dataclasses import dataclass, field

from app.agents.base_agent import BaseAgent
from app.ingestion.normalizer import NormalizedMessage
from app.telemetry.events import TelemetryEmitter


@dataclass
class BriefAgentOutput:
    summary_markdown: str
    action_items: list[str]
    skipped_count: int


class BriefAgent(BaseAgent):
    def __init__(self, telemetry: TelemetryEmitter) -> None:
        from app.core.config import settings
        super().__init__(model=settings.llm_model_brief, telemetry=telemetry)

    def _build_system_prompt(self) -> str:
        return (
            "You are an executive briefing assistant. Summarize a batch of non-urgent emails "
            "into a concise digest.\n\n"
            "Rules:\n"
            "- Group related topics\n"
            "- Extract any implicit action items\n"
            "- Skip purely informational items with no follow-up needed\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"summary_markdown": "<markdown>", "action_items": ["<item>"], "skipped_count": <int>}'
        )

    async def generate_brief(
        self,
        messages: list[NormalizedMessage],
        time_window: str,
        workflow_run_id: str,
        user_id: str,
    ) -> BriefAgentOutput:
        msg_lines = "\n".join(
            f"- From {m.sender_name}: {m.subject} — {m.body_preview[:100]}"
            for m in messages
        )
        user_prompt = f"Time window: {time_window}\n\nEmails to brief:\n{msg_lines}"
        raw = await self._call_llm(
            workflow_run_id=workflow_run_id,
            user_id=user_id,
            user_prompt=user_prompt,
            max_tokens=1500,
            input_data={"message_count": len(messages), "time_window": time_window},
        )
        try:
            parsed = json.loads(raw)
            return BriefAgentOutput(
                summary_markdown=parsed["summary_markdown"],
                action_items=parsed.get("action_items", []),
                skipped_count=int(parsed.get("skipped_count", 0)),
            )
        except (json.JSONDecodeError, KeyError):
            return BriefAgentOutput(
                summary_markdown=raw,
                action_items=[],
                skipped_count=0,
            )
