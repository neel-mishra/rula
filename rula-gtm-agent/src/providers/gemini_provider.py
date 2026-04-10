from __future__ import annotations

import logging
import os

from src.integrations.connector_policy import LLM_PROVIDER, get_connector_policy
from src.providers.base import GenerationRequest, GenerationResponse, LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        self._api_key = os.environ.get("GOOGLE_API_KEY", "")

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        try:
            from google import genai
        except ImportError:
            return GenerationResponse(
                text="",
                provider=self.name,
                model="gemini-2.5-flash",
                prompt_version="v1",
                error="google-genai package not installed",
            )
        try:
            from google.genai import types as genai_types

            policy = get_connector_policy(LLM_PROVIDER)
            # google-genai HttpOptions.timeout is request timeout in milliseconds.
            timeout_ms = max(1, int(policy.timeout_seconds * 1000))
            client = genai.Client(
                api_key=self._api_key,
                http_options=genai_types.HttpOptions(timeout=timeout_ms),
            )
            full_prompt = f"{request.system}\n\n{request.prompt}" if request.system else request.prompt
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
            )
            text = response.text or ""
            return GenerationResponse(
                text=text,
                provider=self.name,
                model="gemini-2.5-flash",
                prompt_version="v1",
            )
        except Exception as e:
            logger.warning("Gemini generation failed: %s", e)
            return GenerationResponse(
                text="",
                provider=self.name,
                model="gemini-2.5-flash",
                prompt_version="v1",
                error=str(e),
            )
