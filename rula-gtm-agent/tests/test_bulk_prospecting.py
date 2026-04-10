from __future__ import annotations


from src.integrations.ingestion import load_test_accounts_raw
from src.orchestrator.bulk_prospecting import AuditOutcome, run_prospecting_bulk


def test_bulk_runs_all_accounts() -> None:
    accounts = load_test_accounts_raw()
    summary = run_prospecting_bulk(accounts, source="test_data")
    assert summary.total == len(accounts)
    assert summary.total == summary.passed + summary.review + summary.errors
    assert len(summary.rows) == len(accounts)


def test_bulk_classifies_pass_and_review() -> None:
    accounts = load_test_accounts_raw()
    summary = run_prospecting_bulk(accounts, source="test_data")
    outcomes = {r.outcome for r in summary.rows}
    assert outcomes <= {AuditOutcome.PASS, AuditOutcome.REVIEW, AuditOutcome.ERROR}


def test_bulk_pass_rows_have_output() -> None:
    accounts = load_test_accounts_raw()
    summary = run_prospecting_bulk(accounts, source="test_data")
    for row in summary.pass_rows:
        assert row.output is not None
        assert row.output.judge_pass is True
        assert row.output.quality_score > 0


def test_bulk_review_rows_have_output() -> None:
    accounts = load_test_accounts_raw()
    summary = run_prospecting_bulk(accounts, source="test_data")
    for row in summary.review_rows:
        assert row.output is not None
        assert row.output.judge_pass is not True


def test_bulk_run_id_is_unique() -> None:
    accounts = load_test_accounts_raw()[:2]
    s1 = run_prospecting_bulk(accounts, source="test_data")
    s2 = run_prospecting_bulk(accounts, source="test_data")
    assert s1.run_id != s2.run_id
