from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GenerationRequest:
    content_type: str
    prompt: str
    system: str = ""
    temperature: float = 0.3
    max_tokens: int = 2048


@dataclass
class GenerationResponse:
    text: str
    provider: str
    model: str
    prompt_version: str
    fallback_used: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResponse: ...
