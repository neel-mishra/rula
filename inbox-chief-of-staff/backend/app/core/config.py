"""Application configuration loaded from environment variables.

All settings are validated at startup via Pydantic BaseSettings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # App
    # -------------------------------------------------------------------------
    node_env: Literal["development", "staging", "production"] = "development"
    app_base_url: str = "http://localhost:3000"
    extra_cors_origins: str = ""  # comma-separated additional allowed origins
    api_base_url: str = "http://localhost:8000"

    @property
    def cors_origins(self) -> list[str]:
        origins = [self.app_base_url]
        if self.extra_cors_origins:
            origins += [o.strip() for o in self.extra_cors_origins.split(",") if o.strip()]
        return origins
    webhook_base_url: str = "https://your-ngrok-or-domain.ngrok.io"

    # -------------------------------------------------------------------------
    # Google / Gmail
    # -------------------------------------------------------------------------
    google_client_id: str = Field(..., description="Google OAuth2 client ID")
    google_client_secret: str = Field(..., description="Google OAuth2 client secret")
    google_oauth_redirect_uri: str = "http://localhost:8000/auth/callback"
    gmail_scopes: str = (
        "https://www.googleapis.com/auth/gmail.readonly,"
        "https://www.googleapis.com/auth/gmail.labels,"
        "https://www.googleapis.com/auth/gmail.compose"
    )
    gmail_watch_labels: str = "INBOX"

    @property
    def gmail_scopes_list(self) -> list[str]:
        """Return Gmail OAuth scopes as a list."""
        return [s.strip() for s in self.gmail_scopes.split(",") if s.strip()]

    @property
    def gmail_watch_labels_list(self) -> list[str]:
        """Return Gmail watch labels as a list."""
        return [lbl.strip() for lbl in self.gmail_watch_labels.split(",") if lbl.strip()]

    # -------------------------------------------------------------------------
    # LLM
    # -------------------------------------------------------------------------
    llm_provider: Literal["anthropic"] = "anthropic"
    llm_api_key: str = Field(..., description="Anthropic API key")
    llm_model_triage: str = "claude-haiku-4-5-20251001"
    llm_model_draft: str = "claude-sonnet-4-6"
    llm_model_brief: str = "claude-haiku-4-5-20251001"

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/inbox_chief",
        description="Async SQLAlchemy database URL",
    )
    database_pool_size: int = 10
    vector_store_mode: Literal["pgvector"] = "pgvector"
    pgvector_embedding_dim: int = 1536

    # -------------------------------------------------------------------------
    # Queue
    # -------------------------------------------------------------------------
    queue_provider: Literal["inline", "cloud_tasks"] = "inline"
    queue_url: str = ""
    # Shared secret checked by the /worker endpoint to reject unauthenticated calls.
    # Set to a strong random value in staging/production.
    worker_auth_secret: str = "change-me-worker-secret"
    # GCP project and queue name used when queue_provider=cloud_tasks.
    cloud_tasks_project: str = ""
    cloud_tasks_location: str = "us-central1"
    cloud_tasks_queue: str = "agent-dispatch"

    # -------------------------------------------------------------------------
    # Gmail Pub/Sub push (required for webhook ingestion)
    # Format: projects/{gcp_project_id}/topics/{topic_name}
    # Leave empty to skip watch registration (manual webhook testing only).
    # -------------------------------------------------------------------------
    pubsub_topic: str = ""

    # -------------------------------------------------------------------------
    # Object storage
    # -------------------------------------------------------------------------
    object_storage_bucket: str = ""
    object_storage_region: str = "us-central1"

    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------
    encryption_key_id: str = Field(
        "", description="Fernet key used for token encryption at rest"
    )
    session_secret: str = Field(
        "change-me-in-production", description="Secret for signing session tokens"
    )

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    error_tracking_dsn: str = ""
    eval_dataset_version: str = "v1"

    @field_validator("session_secret")
    @classmethod
    def warn_insecure_session_secret(cls, v: str) -> str:
        if v == "change-me-in-production":
            import warnings

            warnings.warn(
                "SESSION_SECRET is set to the default insecure value. "
                "Set a strong random value in production.",
                stacklevel=2,
            )
        return v


settings = Settings()  # type: ignore[call-arg]
