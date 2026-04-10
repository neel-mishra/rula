"""Tests for v2 QA bug fixes: signal footnote variance and quality-score variance."""
from __future__ import annotations

import json
from pathlib import Path

from src.agents.prospecting.enrichment import enrich_account
from src.agents.prospecting.evaluator import evaluate_output
from src.agents.prospecting.matcher import match_value_props
from src.agents.prospecting.generator import _deterministic_email_v3
from src.agents.prospecting.segment_logic import resolve_segment_context
from src.explainability.value_prop import explain_value_prop
from src.schemas.account import Account


def _all_accounts() -> list[Account]:
    raw = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    return [Account.model_validate(a) for a in raw]


class TestSignalFootnoteVariance:
    """Value-prop signal footnotes must vary per account and per prop."""

    def test_signals_differ_across_accounts(self) -> None:
        accounts = _all_accounts()
        signal_sets: list[str] = []
        for acct in accounts:
            enriched = enrich_account(acct)
            matches = match_value_props(enriched)
            explanation = explain_value_prop(matches[0], enriched)
            signal_sets.append(explanation)
        unique = set(signal_sets)
        assert len(unique) > 1, "All accounts produced identical signal footnotes"

    def test_signals_differ_across_props_same_account(self) -> None:
        acct = _all_accounts()[0]
        enriched = enrich_account(acct)
        matches = match_value_props(enriched)
        explanations = [explain_value_prop(m, enriched) for m in matches[:3]]
        assert len(set(explanations)) > 1, (
            "All value props for the same account have identical signal footnotes"
        )

    def test_no_static_education_for_non_education_account(self) -> None:
        for acct in _all_accounts():
            if "education" not in acct.industry.lower() and "university" not in acct.industry.lower():
                enriched = enrich_account(acct)
                matches = match_value_props(enriched)
                for m in matches:
                    explanation = explain_value_prop(m, enriched)
                    assert "industry = education" not in explanation.lower(), (
                        f"Non-education account {acct.company} has 'industry = education' signal"
                    )


class TestQualityScoreVariance:
    """Quality scores must differ across accounts with diverse profiles."""

    def test_scores_are_not_constant(self) -> None:
        accounts = _all_accounts()
        scores: list[float] = []
        for acct in accounts:
            enriched = enrich_account(acct)
            matches = match_value_props(enriched)
            seg = resolve_segment_context(acct.industry, matches)
            email = _deterministic_email_v3(enriched, seg, "")
            score, _, _ = evaluate_output(enriched, email, matches)
            scores.append(score)
        unique_scores = set(scores)
        assert len(unique_scores) > 1, (
            f"All accounts yield the same quality score: {scores[0]}"
        )

    def test_sparse_account_scores_lower(self) -> None:
        accounts = _all_accounts()
        sparse = [a for a in accounts if a.contact.name is None]
        full = [a for a in accounts if a.contact.name is not None]
        assert sparse, "No sparse accounts in test data"
        assert full, "No complete accounts in test data"

        sparse_scores = []
        for acct in sparse:
            enriched = enrich_account(acct)
            matches = match_value_props(enriched)
            seg = resolve_segment_context(acct.industry, matches)
            email = _deterministic_email_v3(enriched, seg, "")
            score, _, _ = evaluate_output(enriched, email, matches)
            sparse_scores.append(score)

        full_scores = []
        for acct in full:
            enriched = enrich_account(acct)
            matches = match_value_props(enriched)
            seg = resolve_segment_context(acct.industry, matches)
            email = _deterministic_email_v3(enriched, seg, "")
            score, _, _ = evaluate_output(enriched, email, matches)
            full_scores.append(score)

        assert min(full_scores) > min(sparse_scores), (
            "Sparse accounts should score lower than complete accounts"
        )


class TestMatcherVariance:
    """Different accounts should produce different top value props or orderings."""

    def test_top_value_props_vary(self) -> None:
        accounts = _all_accounts()
        top_props = []
        for acct in accounts:
            enriched = enrich_account(acct)
            matches = match_value_props(enriched)
            top_props.append(matches[0].value_prop)
        unique = set(top_props)
        assert len(unique) > 1, "All accounts have the same top value prop"

    def test_match_scores_differ_across_accounts(self) -> None:
        accounts = _all_accounts()
        top_scores = []
        for acct in accounts:
            enriched = enrich_account(acct)
            matches = match_value_props(enriched)
            top_scores.append(matches[0].score)
        unique = set(top_scores)
        assert len(unique) > 1, "All accounts have the same top match score"
