from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_LOADED = False


def _load_dotenv() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class AppConfig:
    anthropic_api_key: str
    google_api_key: str
    model_primary: str
    model_fallback: str
    generation_mode: str
    environment: str
    log_level: str
    clay_webhook_url: str = ""
    clay_workspace_id: str = ""
    clay_list_id: str = ""
    repo_output_dir: str = "out/runs"
    human_review_dir: str = "out/review_queue"
    run_archive_dir: str = "out/runs"
    business_dna_enabled: bool = True
    business_dna_path: str = ""
    min_discovery_questions: int = 3
    dq_policy_path: str = ""
    export_lineage_enabled: bool = True
    bulk_default_queue: str = "file_order"

    @property
    def has_claude(self) -> bool:
        return bool(self.anthropic_api_key) and self.anthropic_api_key not in {
            "",
            "your_anthropic_api_key_here",
        }

    @property
    def has_gemini(self) -> bool:
        return bool(self.google_api_key) and self.google_api_key not in {
            "",
            "your_google_gemini_api_key_here",
        }

    @property
    def any_provider_available(self) -> bool:
        return self.has_claude or self.has_gemini

    def resolve_provider(self, preferred: str | None = None) -> str | None:
        pref = preferred or self.model_primary
        if pref == "claude" and self.has_claude:
            return "claude"
        if pref == "gemini" and self.has_gemini:
            return "gemini"
        if self.has_claude:
            return "claude"
        if self.has_gemini:
            return "gemini"
        return None

    def resolve_fallback(self, failed_provider: str) -> str | None:
        if failed_provider == "claude" and self.has_gemini:
            return "gemini"
        if failed_provider == "gemini" and self.has_claude:
            return "claude"
        return None


def load_config() -> AppConfig:
    _load_dotenv()
    return AppConfig(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
        model_primary=os.environ.get("MODEL_PRIMARY", "claude"),
        model_fallback=os.environ.get("MODEL_FALLBACK", "gemini"),
        generation_mode=os.environ.get("GENERATION_MODE", "fast_mode"),
        environment=os.environ.get("ENVIRONMENT", "local"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        clay_webhook_url=os.environ.get("CLAY_WEBHOOK_URL", ""),
        clay_workspace_id=os.environ.get("CLAY_WORKSPACE_ID", ""),
        clay_list_id=os.environ.get("CLAY_LIST_ID", ""),
        repo_output_dir=os.environ.get("RULA_REPO_OUTPUT_DIR", "out/runs"),
        human_review_dir=os.environ.get("RULA_HUMAN_REVIEW_DIR", "out/review_queue"),
        run_archive_dir=os.environ.get("RULA_RUN_ARCHIVE_DIR", "out/runs"),
        business_dna_enabled=os.environ.get("RULA_BUSINESS_DNA_ENABLED", "1") == "1",
        business_dna_path=os.environ.get("RULA_BUSINESS_DNA_PATH", ""),
        min_discovery_questions=max(
            1, min(10, int(os.environ.get("RULA_MIN_DISCOVERY_QUESTIONS", "3")))
        ),
        dq_policy_path=os.environ.get("RULA_DQ_POLICY_PATH", "").strip(),
        export_lineage_enabled=os.environ.get("RULA_EXPORT_LINEAGE", "1") != "0",
        bulk_default_queue=os.environ.get("RULA_BULK_DEFAULT_QUEUE", "file_order").strip()
        or "file_order",
    )


def validate_startup(config: AppConfig) -> list[str]:
    warnings: list[str] = []
    if not config.has_claude:
        warnings.append("ANTHROPIC_API_KEY missing or placeholder; Claude generation unavailable.")
    if not config.has_gemini:
        warnings.append("GOOGLE_API_KEY missing or placeholder; Gemini generation unavailable.")
    if not config.any_provider_available:
        warnings.append("No LLM provider keys configured; generative features disabled, deterministic fallback only.")
    if config.environment == "production" and not config.any_provider_available:
        raise RuntimeError("Production requires at least one LLM provider key.")
    for w in warnings:
        logger.warning(w)
    return warnings
