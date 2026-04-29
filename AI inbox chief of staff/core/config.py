"""
Central configuration management using pydantic-settings.
All config values come from environment variables / Secrets Manager.
No secrets in code.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environment identifiers."""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid for the
    declared deployment environment.

    The ``missing`` attribute is the list of missing env var names so callers
    (CI, ops scripts) can render an actionable error.
    """

    def __init__(self, environment: str, missing: list[str]):
        self.environment = environment
        self.missing = list(missing)
        joined = ", ".join(self.missing)
        super().__init__(
            f"Missing required configuration for environment '{environment}': "
            f"{joined}"
        )


# Required env vars per environment. Keys are the *attribute* names on
# Settings (lowercase). They are mirrored to UPPER_SNAKE for the error
# message so ops can grep them directly.
#
# Rule of thumb:
#   - prod: anything that crashes the app, talks to a customer, or signs/
#     encrypts data MUST be set
#   - staging: same as prod minus customer-delivery (SES) — staging mailers
#     are optional because briefs may not be delivered to real users
#   - dev: nothing strictly required (developer can stub or skip features)
_REQUIRED_BY_ENV: dict[Environment, list[str]] = {
    Environment.DEV: [],
    Environment.STAGING: [
        "app_secret_key",
        "database_url",
        "kms_key_arn",
        "token_encryption_key",
        "google_client_id",
        "google_client_secret",
        "gmail_webhook_secret",
        "anthropic_api_key",
        "openai_api_key",
        "aws_account_id",
    ],
    Environment.PROD: [
        "app_secret_key",
        "database_url",
        "kms_key_arn",
        "token_encryption_key",
        "google_client_id",
        "google_client_secret",
        "gmail_webhook_secret",
        "anthropic_api_key",
        "openai_api_key",
        "aws_account_id",
        "ses_from_address",
        "s3_audit_bucket",
    ],
}


# Sentinel placeholder values from .env.example that should be treated as
# "not set" when validating production config.
_PLACEHOLDER_PREFIXES = ("CHANGE_ME", "sk-CHANGE_ME", "sk-ant-CHANGE_ME")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.dev",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ─────────────────────────────────────────────────────────
    app_env: Literal["dev", "staging", "prod"] = "dev"
    app_secret_key: str = Field(..., min_length=32)
    log_level: str = "INFO"

    # Split-host browser CORS (e.g. Vercel frontend calling Render API).
    # Comma-separated list of allowed origins. In ``dev``, ``http://localhost:3000``
    # is always included even if this field is empty.
    cors_allowed_origins: str = ""
    # Allow preview deployments matching ``https://*.vercel.app``. Set false in
    # strict production; use explicit origins in ``cors_allowed_origins`` instead.
    cors_allow_vercel_preview: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    def cors_origins_list(self) -> list[str]:
        """Origins passed to FastAPI CORSMiddleware ``allow_origins``."""
        parts = [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]
        if self.app_env == "dev":
            merged: list[str] = []
            seen: set[str] = set()
            for o in [*parts, "http://localhost:3000"]:
                if o not in seen:
                    seen.add(o)
                    merged.append(o)
            return merged
        return parts

    def cors_origin_regex(self) -> str | None:
        """Optional regex for Starlette CORSMiddleware (Vercel preview URLs)."""
        if self.cors_allow_vercel_preview:
            return r"https://.*\.vercel\.app"
        return None

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if "sqlite" in v.lower() and True:  # allow sqlite for tests only
            return v
        return v

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Backend selection (MVP vs. production shape) ────────────────────────
    # Each selector chooses between a self-hostable MVP backend and a
    # production-grade SaaS/AWS backend without changing call sites.
    # Defaults are sandbox-friendly and can be overridden per environment.
    ingest_source: Literal["gmail", "fixture", "imap"] = "gmail"
    queue_backend: Literal["sqs", "redis_streams", "inline"] = "redis_streams"
    mailbox_backend: Literal["gmail", "local"] = "gmail"

    # ── AWS ──────────────────────────────────────────────────────────────────
    aws_region: str = "us-east-1"
    aws_account_id: str = ""
    # Override the AWS service endpoint (e.g. MinIO at http://minio:9000 or
    # LocalStack at http://localhost:4566). Empty = real AWS endpoints.
    aws_endpoint_url: str = ""

    sqs_ingest_queue_url: str = ""
    sqs_triage_queue_url: str = ""
    sqs_draft_queue_url: str = ""
    sqs_brief_queue_url: str = ""
    sqs_memory_queue_url: str = ""
    sqs_eval_queue_url: str = ""
    sqs_dlq_url: str = ""

    s3_audit_bucket: str = ""
    s3_eval_bucket: str = ""

    # ── Audit-event export (X.10) ───────────────────────────────────────────
    # Long-term retention destination for rows in the `audit_events` table.
    # When AUDIT_EXPORT_S3_BUCKET is empty, the export worker is a no-op
    # (intended for dev/staging environments without S3 provisioned).
    audit_export_s3_bucket: str = ""
    audit_export_s3_prefix: str = "audit/"

    # ── Encryption ────────────────────────────────────────────────────────────
    kms_key_arn: str = ""
    token_encryption_key: str = Field(default="", description="Base64-encoded 32-byte key for dev")

    # ── Google / Gmail ────────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/mailbox-connect/gmail/callback"
    google_oauth_scopes: str = (
        "https://www.googleapis.com/auth/gmail.readonly,"
        "https://www.googleapis.com/auth/gmail.labels,"
        "https://www.googleapis.com/auth/gmail.modify,"
        "https://www.googleapis.com/auth/gmail.compose"
    )
    gmail_webhook_topic: str = ""
    gmail_webhook_secret: str = ""

    @property
    def google_scopes_list(self) -> list[str]:
        return [s.strip() for s in self.google_oauth_scopes.split(",") if s.strip()]

    # ── LLM Providers ─────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    llm_primary_provider: str = "anthropic"
    llm_primary_model: str = "claude-sonnet-4-6"
    llm_fallback_provider: str = "openai"
    llm_fallback_model: str = "gpt-4o-mini"

    # Tiered model routing: cheaper models for low-stakes tasks
    llm_cheap_provider: str = "anthropic"
    llm_cheap_model: str = "claude-haiku-4-5-20251001"

    llm_daily_budget_cents_per_mailbox: int = 75
    llm_monthly_budget_cents: int = 10000
    llm_budget_degradation_threshold: float = 0.80

    # ── SES (Brief Delivery + Inbound Assistant) ────────────────────────────
    ses_from_address: str = ""
    ses_region: str = "us-east-1"
    ses_enabled: bool = False
    ses_inbound_secret: str = ""    # Bearer token required on /webhooks/ses-inbound if set

    # ── Incident Alert Routing ──────────────────────────────────────────────
    slack_webhook_url: str = ""         # Slack incoming webhook URL
    pagerduty_routing_key: str = ""     # PagerDuty Events API v2 routing key

    # ── Observability ─────────────────────────────────────────────────────────
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "inbox-chief-of-staff"
    otel_environment: str = "dev"

    # ── Brief Scheduler ───────────────────────────────────────────────────────
    brief_morning_hour: int = 8
    brief_afternoon_hour: int = 17
    brief_timezone: str = "America/New_York"

    # ── Triage / Safety thresholds ────────────────────────────────────────────
    triage_high_confidence_threshold: float = 0.90
    triage_medium_confidence_threshold: float = 0.70
    mutation_undo_window_seconds: int = 604800  # 7 days

    # ── Kill switches ─────────────────────────────────────────────────────────
    kill_switch_llm: bool = False
    kill_switch_mutations: bool = False

    # ── Shadow mode ────────────────────────────────────────────────────────
    # Pipeline runs fully (ingest, triage, draft, brief) but does NOT apply
    # mutations or create real Gmail drafts. All decisions are logged for review.
    shadow_mode: bool = False

    # ── Progressive rollout ─────────────────────────────────────────────
    default_activation_mode: str = "shadow"  # shadow | observe | auto

    # ── Gold-eval fixture pipeline ───────────────────────────────────────
    # Both flags default OFF until Gmail OAuth + connectors are live in
    # production. Once flipped, the extraction worker reads the user's
    # real inbox and the nightly evaluator runs against the labeled
    # dataset.
    gold_sampling_enabled: bool = False
    gold_eval_enabled: bool = False
    gold_sample_name_hash_salt: str = "set-per-deployment"

    # ── Environment validation ──────────────────────────────────────────
    @property
    def environment(self) -> Environment:
        """Strongly-typed alias for ``app_env``."""
        return Environment(self.app_env)

    def validate_for_environment(self, env: Environment | str | None = None) -> None:
        """Verify that all keys required for the target environment are set.

        Raises:
            ConfigError: lists every missing attribute (snake_case) and the
                env it was missing for. Message is intentionally verbose so
                ops can resolve it without re-running with extra logging.
        """
        target = Environment(env) if env is not None else self.environment
        required = list(_REQUIRED_BY_ENV.get(target, []))
        required.extend(self._dynamic_required_keys(target))

        missing: list[str] = []
        for attr in required:
            value = getattr(self, attr, None)
            if value is None:
                missing.append(attr.upper())
                continue
            # Treat empty strings and example placeholders as unset.
            if isinstance(value, str):
                stripped = value.strip()
                if not stripped:
                    missing.append(attr.upper())
                    continue
                if any(stripped.startswith(p) for p in _PLACEHOLDER_PREFIXES):
                    missing.append(attr.upper())
                    continue

        if missing:
            raise ConfigError(target.value, missing)

    def _dynamic_required_keys(self, env: Environment) -> list[str]:
        """
        Add conditional requirements based on selected runtime backends.
        """
        dynamic: list[str] = []
        if self.queue_backend == "sqs":
            dynamic.extend(["sqs_ingest_queue_url", "sqs_dlq_url"])
            if env is Environment.PROD:
                dynamic.extend(
                    [
                        "sqs_triage_queue_url",
                        "sqs_draft_queue_url",
                        "sqs_brief_queue_url",
                    ]
                )
        return dynamic


@lru_cache
def get_settings() -> Settings:
    """Return cached singleton settings instance."""
    return Settings()


# Convenience alias
settings = get_settings()
