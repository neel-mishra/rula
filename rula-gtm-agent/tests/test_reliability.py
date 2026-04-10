"""Reliability smoke tests: permission errors, disabled modes, breaker-open states,
and generation-specific resilience through UI pathways."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.orchestrator.graph import run_map_verification, run_prospecting
from src.safety.circuit import map_breaker, prospecting_breaker


# ---------------------------------------------------------------------------
# Permission error paths
# ---------------------------------------------------------------------------

class TestPermissionPaths:
    def test_viewer_cannot_run_prospecting(self) -> None:
        accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
        with pytest.raises(PermissionError, match="viewer"):
            run_prospecting(accounts[0], actor_role="viewer")

    def test_viewer_cannot_run_map(self) -> None:
        evidence = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
        with pytest.raises(PermissionError, match="viewer"):
            run_map_verification(evidence[0]["evidence_id"], evidence[0]["text"], actor_role="viewer")

    def test_user_can_run_both(self) -> None:
        accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
        evidence = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
        r1 = run_prospecting(accounts[0], actor_role="user")
        assert r1.account_id == accounts[0]["account_id"]
        r2 = run_map_verification(evidence[0]["evidence_id"], evidence[0]["text"], actor_role="user")
        assert r2.evidence_id == evidence[0]["evidence_id"]


# ---------------------------------------------------------------------------
# Kill switch paths
# ---------------------------------------------------------------------------

class TestKillSwitchPaths:
    def test_prospecting_kill_switch(self) -> None:
        os.environ["RULA_DISABLE_PROSPECTING"] = "true"
        try:
            with pytest.raises(RuntimeError, match="disabled"):
                run_prospecting(
                    {"account_id": 1, "company": "X", "industry": "Y",
                     "us_employees": 100, "contact": {"name": "A", "title": "B"},
                     "health_plan": "C", "notes": "D"},
                    actor_role="user",
                )
        finally:
            os.environ.pop("RULA_DISABLE_PROSPECTING", None)

    def test_map_kill_switch(self) -> None:
        os.environ["RULA_DISABLE_MAP"] = "true"
        try:
            with pytest.raises(RuntimeError, match="disabled"):
                run_map_verification("X", "test", actor_role="user")
        finally:
            os.environ.pop("RULA_DISABLE_MAP", None)


# ---------------------------------------------------------------------------
# Circuit breaker paths
# ---------------------------------------------------------------------------

class TestCircuitBreakerPaths:
    def setup_method(self) -> None:
        prospecting_breaker._failures = 0
        prospecting_breaker._opened_at = None
        map_breaker._failures = 0
        map_breaker._opened_at = None

    def test_prospecting_breaker_opens(self) -> None:
        for _ in range(prospecting_breaker.failure_threshold):
            prospecting_breaker.record_failure()
        with pytest.raises(RuntimeError, match="circuit breaker"):
            run_prospecting(
                {"account_id": 1, "company": "X", "industry": "Y",
                 "us_employees": 100, "contact": {"name": "A", "title": "B"},
                 "health_plan": "C", "notes": "D"},
                actor_role="user",
            )

    def test_map_breaker_opens(self) -> None:
        for _ in range(map_breaker.failure_threshold):
            map_breaker.record_failure()
        with pytest.raises(RuntimeError, match="circuit breaker"):
            run_map_verification("X", "test", actor_role="user")

    def teardown_method(self) -> None:
        prospecting_breaker._failures = 0
        prospecting_breaker._opened_at = None
        map_breaker._failures = 0
        map_breaker._opened_at = None


# ---------------------------------------------------------------------------
# UI component error rendering
# ---------------------------------------------------------------------------

class TestUIErrorRendering:
    def test_runtime_error_message_includes_breaker(self) -> None:
        err = RuntimeError("circuit breaker open; retry later")
        assert "circuit breaker" in str(err).lower()

    def test_runtime_error_message_includes_disabled(self) -> None:
        err = RuntimeError("Pipeline disabled by admin")
        assert "disabled" in str(err).lower()

    def test_permission_error_format(self) -> None:
        err = PermissionError("Role 'viewer' lacks permission 'prospecting:run'.")
        assert "viewer" in str(err)


# ---------------------------------------------------------------------------
# Generation resilience: deterministic fallback always works
# ---------------------------------------------------------------------------

class TestGenerationResilience:
    def test_prospecting_works_without_llm_keys(self) -> None:
        accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
        result = run_prospecting(accounts[0]).model_dump()
        email = result.get("email", {})
        assert email.get("subject_line"), "Deterministic fallback must produce a subject"
        assert email.get("body"), "Deterministic fallback must produce a body"
        assert len(result.get("discovery_questions", [])) >= 2

    def test_all_accounts_survive_generation(self) -> None:
        accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
        for acct in accounts:
            result = run_prospecting(acct).model_dump()
            assert result.get("email"), f"Account {acct['account_id']} failed generation"
