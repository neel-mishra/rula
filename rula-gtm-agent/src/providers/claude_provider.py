from __future__ import annotations

import logging
import os

from src.integrations.connector_policy import LLM_PROVIDER, get_connector_policy
from src.providers.base import GenerationRequest, GenerationResponse, LLMProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self) -> None:
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        try:
            import anthropic
        except ImportError:
            return GenerationResponse(
                text="",
                provider=self.name,
                model="claude-sonnet-4-20250514",
                prompt_version="v1",
                error="anthropic package not installed",
            )
        try:
            policy = get_connector_policy(LLM_PROVIDER)
            # Anthropic SDK: timeout is total request time in seconds (float).
            client = anthropic.Anthropic(
                api_key=self._api_key,
                timeout=policy.timeout_seconds,
            )
            messages = [{"role": "user", "content": request.prompt}]
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=request.max_tokens,
                system=request.system or "You are a helpful sales assistant for Rula Health.",
                messages=messages,
                temperature=request.temperature,
            )
            text = response.content[0].text if response.content else ""
            return GenerationResponse(
                text=text,
                provider=self.name,
                model="claude-sonnet-4-20250514",
                prompt_version="v1",
            )
        except Exception as e:
            logger.warning("Claude generation failed: %s", e)
            return GenerationResponse(
                text="",
                provider=self.name,
                model="claude-sonnet-4-20250514",
                prompt_version="v1",
                error=str(e),
            )
