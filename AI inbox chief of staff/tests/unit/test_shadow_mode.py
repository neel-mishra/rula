"""Tests for shadow mode configuration."""

from __future__ import annotations

import pytest


def test_shadow_mode_defaults_off():
    """Shadow mode should be disabled by default."""
    from core.config import settings
    assert settings.shadow_mode is False


def test_shadow_mode_field_exists():
    """Shadow mode config field must exist."""
    from core.config import Settings
    assert "shadow_mode" in Settings.model_fields
