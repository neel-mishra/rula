from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.integrations.handoff import handoff_orchestrator
from src.integrations.ingestion import load_test_accounts_raw
from src.orchestrator.bulk_prospecting import run_prospecting_bulk


def test_handoff_creates_archive_and_review_queue() -> None:
    accounts = load_test_accounts_raw()[:3]
    summary = run_prospecting_bulk(accounts, source="test_data")

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_dir = Path(tmpdir) / "runs"
        review_dir = Path(tmpdir) / "review"
        with patch("src.integrations.handoff.load_config") as mock_cfg:
            mock = mock_cfg.return_value
            mock.human_review_dir = str(review_dir)
            mock.run_archive_dir = str(archive_dir)
            result = handoff_orchestrator(summary)

        assert result.run_id == summary.run_id
        assert len(result.sequencer_payloads) == summary.passed
        assert len(result.crm_manifest) == summary.passed
        assert len(result.review_queue) == summary.review + summary.errors

        manifest = json.loads((Path(result.archive_path) / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["policy_skipped"] == summary.policy_skipped
        assert manifest["queue_mode"] == summary.queue_mode


def test_handoff_sequencer_payload_has_contact() -> None:
    accounts = load_test_accounts_raw()[:1]
    summary = run_prospecting_bulk(accounts, source="test_data")

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.integrations.handoff.load_config") as mock_cfg:
            mock = mock_cfg.return_value
            mock.human_review_dir = str(Path(tmpdir) / "review")
            mock.run_archive_dir = str(Path(tmpdir) / "runs")
            result = handoff_orchestrator(summary)

    if result.sequencer_payloads:
        sp = result.sequencer_payloads[0]
        assert sp.account_id == accounts[0]["account_id"]
        assert sp.email_subject


def test_handoff_crm_manifest_has_value_prop() -> None:
    accounts = load_test_accounts_raw()[:1]
    summary = run_prospecting_bulk(accounts, source="test_data")

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.integrations.handoff.load_config") as mock_cfg:
            mock = mock_cfg.return_value
            mock.human_review_dir = str(Path(tmpdir) / "review")
            mock.run_archive_dir = str(Path(tmpdir) / "runs")
            result = handoff_orchestrator(summary)

    if result.crm_manifest:
        row = result.crm_manifest[0]
        assert row.top_value_prop
        assert row.quality_score > 0
