from __future__ import annotations
import time
from abc import ABC, abstractmethod
from typing import Any
import anthropic

from app.core.config import settings
from app.telemetry.events import TelemetryEmitter


class BaseAgent(ABC):
    """Stateless base for all LLM-backed agents. Handles API calls and telemetry."""

    def __init__(self, model: str, telemetry: TelemetryEmitter) -> None:
        self.model = model
        self.telemetry = telemetry
        self._client = anthropic.Anthropic(api_key=settings.llm_api_key)

    @abstractmethod
    def _build_system_prompt(self) -> str:
        ...

    async def _call_llm(
        self,
        workflow_run_id: str,
        user_id: str,
        user_prompt: str,
        max_tokens: int = 1024,
        input_data: dict[str, Any] | None = None,
    ) -> str:
        """Call the Anthropic API, emit telemetry, return response text."""
        start = time.monotonic()
        message = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=self._build_system_prompt(),
            messages=[{"role": "user", "content": user_prompt}],
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        response_text = message.content[0].text

        await self.telemetry.emit_agent_call(
            agent_name=self.__class__.__name__,
            workflow_run_id=workflow_run_id,
            user_id=user_id,
            input_data=input_data or {"prompt": user_prompt},
            output_data={"response": response_text},
            confidence=0.0,  # overridden by subclass after parsing
            model=self.model,
            duration_ms=duration_ms,
        )
        return response_text
