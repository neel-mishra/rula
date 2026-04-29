"""
Config / secret loading tests for dev, staging, and prod environments.

These tests guard the Gate 0 promise that production cannot boot with
missing required secrets, while keeping dev permissive so engineers can
run the stack locally without filling in every key.
"""

from __future__ import annotations

import pytest

from core.config import (
    ConfigError,
    Environment,
    Settings,
    _REQUIRED_BY_ENV,
)


# A minimal "kitchen sink" set of env values that satisfies *every*
# required key for any environment. Tests that want to exercise the
# happy path start from a copy of this dict and selectively unset keys.
_FULL_ENV: dict[str, str] = {
    "APP_SECRET_KEY": "x" * 32,  # Field(min_length=32)
    "DATABASE_URL": "postgresql+asyncpg://u:p@db:5432/inbox",
    "KMS_KEY_ARN": "arn:aws:kms:us-east-1:111122223333:key/abcd-1234",
    "TOKEN_ENCRYPTION_KEY": "dGVzdC10b2tlbi1lbmNyeXB0aW9uLWtleS0zMmJ5dGVzIQ==",
    "GOOGLE_CLIENT_ID": "real-client.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "real-google-secret",
    "GMAIL_WEBHOOK_SECRET": "real-webhook-secret",
    "ANTHROPIC_API_KEY": "sk-ant-real-key",
    "OPENAI_API_KEY": "sk-real-openai-key",
    "AWS_ACCOUNT_ID": "111122223333",
    "SQS_INGEST_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/111122223333/inbox-ingest",
    "SQS_TRIAGE_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/111122223333/inbox-triage",
    "SQS_DRAFT_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/111122223333/inbox-draft",
    "SQS_BRIEF_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/111122223333/inbox-brief",
    "SQS_DLQ_URL": "https://sqs.us-east-1.amazonaws.com/111122223333/inbox-dlq",
    "SES_FROM_ADDRESS": "briefs@example.com",
    "S3_AUDIT_BUCKET": "inbox-audit-prod",
}


def _build_settings() -> Settings:
    """Construct Settings while ignoring the on-disk .env.dev file so that
    tests are fully driven by monkeypatch.setenv."""
    return Settings(_env_file=None)


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every key that any environment lists as required, plus the
    APP_ENV switch, so each test starts from a known empty baseline."""
    keys = {k.upper() for keys in _REQUIRED_BY_ENV.values() for k in keys}
    keys.add("APP_ENV")
    for key in keys:
        monkeypatch.delenv(key, raising=False)


class TestDevEnvironmentLoads:
    """Dev mode is permissive: minimal env set should validate cleanly."""

    def test_dev_with_minimal_env_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_settings_env(monkeypatch)
        # Only the always-required-by-pydantic fields need values.
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

        settings = _build_settings()
        assert settings.environment is Environment.DEV
        # Should not raise — dev requires nothing extra.
        settings.validate_for_environment()

    def test_dev_environment_property_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        settings = _build_settings()
        assert settings.environment is Environment.DEV
        assert settings.app_env == "dev"


class TestStagingEnvironmentValidation:
    def test_staging_missing_required_keys_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "staging")
        monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")

        settings = _build_settings()
        with pytest.raises(ConfigError) as exc_info:
            settings.validate_for_environment()

        err = exc_info.value
        assert err.environment == "staging"
        # Each missing key must be present in the error message so ops can
        # resolve it without re-running with extra logging.
        assert "KMS_KEY_ARN" in str(err)
        assert "ANTHROPIC_API_KEY" in str(err)
        assert "GOOGLE_CLIENT_SECRET" in str(err)
        # Sanity: at least 3 distinct keys called out.
        assert len(err.missing) >= 3

    def test_staging_with_full_env_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "staging")
        for k, v in _FULL_ENV.items():
            monkeypatch.setenv(k, v)
        settings = _build_settings()
        # Must not raise.
        settings.validate_for_environment()

    def test_staging_redis_streams_does_not_require_sqs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "staging")
        for k, v in _FULL_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("QUEUE_BACKEND", "redis_streams")
        monkeypatch.delenv("SQS_INGEST_QUEUE_URL", raising=False)
        monkeypatch.delenv("SQS_DLQ_URL", raising=False)

        settings = _build_settings()
        settings.validate_for_environment()


class TestProdEnvironmentValidation:
    def test_prod_missing_required_keys_raises_with_actionable_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")

        settings = _build_settings()
        with pytest.raises(ConfigError) as exc_info:
            settings.validate_for_environment()

        err = exc_info.value
        assert err.environment == "prod"
        msg = str(err)
        assert "KMS_KEY_ARN" in msg
        assert "ANTHROPIC_API_KEY" in msg
        assert "SES_FROM_ADDRESS" in msg
        assert len(err.missing) >= 3

    def test_prod_treats_change_me_placeholders_as_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Copying .env.example verbatim to .env.prod must not pass the
        validator — placeholders are recognised as 'unset'."""
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "prod")
        for k, v in _FULL_ENV.items():
            monkeypatch.setenv(k, v)
        # Now poison three values with placeholders
        monkeypatch.setenv("KMS_KEY_ARN", "CHANGE_ME")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-CHANGE_ME")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-CHANGE_ME")

        settings = _build_settings()
        with pytest.raises(ConfigError) as exc_info:
            settings.validate_for_environment()
        missing = exc_info.value.missing
        assert "KMS_KEY_ARN" in missing
        assert "ANTHROPIC_API_KEY" in missing
        assert "OPENAI_API_KEY" in missing

    def test_prod_with_full_env_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "prod")
        for k, v in _FULL_ENV.items():
            monkeypatch.setenv(k, v)
        settings = _build_settings()
        # Must not raise — every required prod key is populated.
        settings.validate_for_environment()
        assert settings.environment is Environment.PROD

    def test_prod_sqs_backend_requires_queue_urls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "prod")
        for k, v in _FULL_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("QUEUE_BACKEND", "sqs")
        monkeypatch.delenv("SQS_BRIEF_QUEUE_URL", raising=False)

        settings = _build_settings()
        with pytest.raises(ConfigError) as exc_info:
            settings.validate_for_environment()
        assert "SQS_BRIEF_QUEUE_URL" in exc_info.value.missing


class TestCorsSplitHostSettings:
    """CORS wiring for Vercel frontend + API on another host."""

    def test_dev_includes_localhost_3000(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        settings = _build_settings()
        assert "http://localhost:3000" in settings.cors_origins_list()

    def test_dev_merges_explicit_origins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS",
            "https://my-app.vercel.app,https://prod.example.com",
        )
        settings = _build_settings()
        origins = settings.cors_origins_list()
        assert "http://localhost:3000" in origins
        assert "https://my-app.vercel.app" in origins
        assert "https://prod.example.com" in origins

    def test_staging_only_configured_origins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "staging")
        for k, v in _FULL_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("QUEUE_BACKEND", "redis_streams")
        monkeypatch.delenv("SQS_INGEST_QUEUE_URL", raising=False)
        monkeypatch.delenv("SQS_DLQ_URL", raising=False)
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com")
        settings = _build_settings()
        assert settings.cors_origins_list() == ["https://app.example.com"]
        assert settings.cors_origin_regex() is None

    def test_vercel_preview_regex_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv("CORS_ALLOW_VERCEL_PREVIEW", "true")
        settings = _build_settings()
        assert settings.cors_origin_regex() == r"https://.*\.vercel\.app"


class TestExplicitEnvironmentArgument:
    """``validate_for_environment`` accepts an explicit env override so
    deploy scripts can dry-run a staging config against prod rules."""

    def test_validate_against_explicit_prod_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        settings = _build_settings()

        # Even though APP_ENV=dev, validating against prod should fail.
        with pytest.raises(ConfigError) as exc_info:
            settings.validate_for_environment(Environment.PROD)
        assert exc_info.value.environment == "prod"

    def test_validate_against_string_env_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_settings_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        settings = _build_settings()

        with pytest.raises(ConfigError):
            settings.validate_for_environment("staging")
