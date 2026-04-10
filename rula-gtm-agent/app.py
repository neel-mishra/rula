from __future__ import annotations

import datetime as dt
import inspect
import json
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from src.agents.prospecting.corrections import apply_ae_edit, list_corrections
from src.agents.verification.capture import map_capture_to_evidence_text
from src.config import load_config, validate_startup
from src.security.rbac import resolve_role
from src.explainability.economics import estimate_economics
from src.explainability.threshold import explain_threshold, explain_tier_assignment
from src.explainability.value_prop import explain_value_prop
from src.governance.retention import enforce_retention
from src.integrations.export import build_map_export, build_prospecting_export
from src.schemas.evidence_artifact import LineageExportBlock
from src.integrations.handoff import handoff_orchestrator, HandoffResult
from src.integrations.ingestion import load_test_accounts_raw, load_clay_accounts_demo
from src.integrations.map_handoff import map_handoff_orchestrator, MapHandoffResult
from src.integrations.map_sample_combine import combine_first_two_map_evidence
from src.orchestrator.bulk_map import BulkMapSummary, run_map_verification_bulk
from src.orchestrator.bulk_prospecting import BulkRunSummary, AuditOutcome, run_prospecting_bulk
from src.orchestrator.graph import run_map_verification, run_prospecting
from src.orchestrator.shadow import compare_map, compare_prospecting
from src.schemas.map_capture import MapCampaignPlan, MapCaptureInput
from src.schemas.prospecting import ProspectingOutput
from src.ui.components import (
    audit_badge,
    confidence_pill,
    copyable_block,
    render_empty_state,
    render_permission_error,
    render_runtime_error,
    risk_chips,
)
from src.ui.promote_map import build_evidence_from_prospecting
from src.ui.pages import page_insights

DATA_DIR = Path("data")


def _store_map_promotion(account: dict, result: dict) -> None:
    eid, text = build_evidence_from_prospecting(account, result)
    st.session_state["map_bridge_text"] = text
    st.session_state["map_bridge_evidence_id"] = eid
    st.session_state["map_bridge_pr"] = str(result.get("prospecting_run_id") or "")
    aid = account.get("account_id")
    st.session_state["map_bridge_account_id"] = str(aid) if aid is not None else ""


def _render_promote_to_map_expander(
    *,
    summary: BulkRunSummary | None = None,
    single_result: dict | None = None,
    single_account: dict | None = None,
) -> None:
    with st.expander("Promote to MAP (optional)", expanded=False):
        st.caption(
            "Create a MAP verification draft from prospecting output. "
            "Open **MAP Review** → **Single evidence** — a **Promoted from Prospecting** panel appears when a draft exists."
        )
        if summary and summary.pass_rows:
            labels = [
                f'{r.account_payload.get("company", r.account_id)} — {r.account_id}' for r in summary.pass_rows
            ]
            idx = st.selectbox(
                "Ready to Send account",
                range(len(labels)),
                format_func=lambda i: labels[i],
                key="promote_map_pick",
            )
            if st.button("Prepare MAP draft from this account", key="promote_map_bulk_btn"):
                row = summary.pass_rows[idx]
                assert row.output is not None
                _store_map_promotion(row.account_payload, row.output.model_dump())
                st.success("Draft stored. Switch to **MAP Review** to continue.")
        elif single_result and single_account:
            if st.button("Prepare MAP draft from this run", key="promote_map_single_btn"):
                _store_map_promotion(single_account, single_result)
                st.success("Draft stored. Switch to **MAP Review** to continue.")
        else:
            st.caption("No prospecting output available to promote yet.")


def _run_prospecting_bulk_compat(
    accounts: list[dict],
    *,
    actor_role: str,
    source: str,
    queue_mode: str,
) -> BulkRunSummary:
    """Call bulk runner; only passes queue_mode if this process loaded a module that supports it."""
    kw: dict = {"actor_role": actor_role, "source": source}
    if "queue_mode" in inspect.signature(run_prospecting_bulk).parameters:
        kw["queue_mode"] = queue_mode
    return run_prospecting_bulk(accounts, **kw)


def _load_accounts() -> list[dict]:
    return load_test_accounts_raw()


def _load_evidence() -> list[dict]:
    return json.loads((DATA_DIR / "map_evidence.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_edit_to_bulk_summary(account_id: int, subject: str, body: str, cta: str) -> None:
    """Propagate an inline email edit back into the stored BulkRunSummary
    so that handoff always pushes the latest saved version."""
    summary: BulkRunSummary | None = st.session_state.get("last_bulk_summary")
    if summary is None:
        return
    from src.schemas.prospecting import OutreachEmail
    for row in summary.rows:
        if row.account_id == account_id and row.output is not None:
            row.output = row.output.model_copy(
                update={"email": OutreachEmail(subject_line=subject, body=body, cta=cta)}
            )
            break


# ---------------------------------------------------------------------------
# Slide navigation helpers
# ---------------------------------------------------------------------------

def _get_current_slide() -> int:
    return st.session_state.get("prospecting_slide", 1)


def _go_to_slide(target: int) -> None:
    if target < 1 or target > 3:
        return
    st.session_state["prospecting_slide"] = target
    st.rerun()


def _can_go_next_from_slide1() -> bool:
    return st.session_state.get("last_bulk_summary") is not None


def _can_go_next_from_slide2() -> bool:
    return st.session_state.get("last_bulk_summary") is not None


# ---------------------------------------------------------------------------
# Shared result renderers
# ---------------------------------------------------------------------------

def _render_prospecting_result(result: dict, account: dict | None = None) -> None:
    st.markdown("#### Outcome")
    st.write(f"Prospecting complete for account **{result.get('account_id')}**.")

    aid = result.get("account_id", 0)
    if "edited_accounts" not in st.session_state:
        st.session_state["edited_accounts"] = set()
    edited: set[int] = st.session_state["edited_accounts"]
    edit_icon = "✅" if aid in edited else "✗"

    # Outcome layout: titles row + values row (scan-aligned)
    t1, t2, t3 = st.columns(3)
    with t1:
        st.markdown("**Status**")
    with t2:
        st.markdown("**Account Score**")
    with t3:
        st.markdown("**Email edits**")

    v1, v2, v3 = st.columns(3)
    with v1:
        st.markdown(audit_badge(result.get("judge_pass")), unsafe_allow_html=True)
    with v2:
        st.markdown(f"{result.get('quality_score', 0):.1f} / 5")
    with v3:
        st.markdown(edit_icon)

    vps = result.get("matched_value_props", [])
    if vps:
        st.markdown("**Why these value props**")
        for vp in vps[:3]:
            try:
                from src.schemas.prospecting import ValuePropMatch
                from src.schemas.account import EnrichedAccount, Account

                vpm = ValuePropMatch(**vp)
                if account:
                    acct = Account.model_validate(account)
                    enriched = EnrichedAccount(
                        account=acct, icp_fit_score=80, data_completeness_score=80, flags=[],
                    )
                    explanation = explain_value_prop(vpm, enriched)
                else:
                    explanation = vp.get("reasoning", "")
            except Exception:
                explanation = vp.get("reasoning", "")
            with st.expander(
                f"{vp['value_prop'].replace('_', ' ').title()} (score {vp['score']})",
                expanded=False,
            ):
                st.markdown(explanation)

    if account and account.get("us_employees"):
        with st.expander("Unit economics estimate", expanded=False):
            econ = estimate_economics(account["us_employees"])
            st.markdown(econ.rationale)
            st.metric("Estimated ACV", f"${econ.annual_contract_value:,.0f}")

    st.markdown("---")
    st.markdown("#### Recommended next action")
    if result.get("human_review_needed"):
        st.warning("Review suggested before sending. Edit the draft below or regenerate.")
    else:
        st.success("Ready to send. Edit the email below if needed, then submit.")

    email = result.get("email", {})
    key_prefix = f"edit_{aid}"

    # Capture the original AI-generated draft once, so we can reliably revert.
    if f"{key_prefix}_orig_subject" not in st.session_state:
        st.session_state[f"{key_prefix}_orig_subject"] = email.get("subject_line", "")
    if f"{key_prefix}_orig_body" not in st.session_state:
        st.session_state[f"{key_prefix}_orig_body"] = email.get("body", "")
    if f"{key_prefix}_orig_cta" not in st.session_state:
        st.session_state[f"{key_prefix}_orig_cta"] = email.get("cta", "")

    if f"{key_prefix}_subject" not in st.session_state:
        st.session_state[f"{key_prefix}_subject"] = email.get("subject_line", "")
    if f"{key_prefix}_body" not in st.session_state:
        st.session_state[f"{key_prefix}_body"] = email.get("body", "")
    if f"{key_prefix}_cta" not in st.session_state:
        st.session_state[f"{key_prefix}_cta"] = email.get("cta", "")

    # Phase 2 of revert: set widget keys before widgets render, show toast.
    if st.session_state.get(f"{key_prefix}_revert_confirmed"):
        st.session_state[f"{key_prefix}_revert_confirmed"] = False
        st.session_state[f"{key_prefix}_subject_input"] = st.session_state[f"{key_prefix}_subject"]
        st.session_state[f"{key_prefix}_body_input"] = st.session_state[f"{key_prefix}_body"]
        st.session_state[f"{key_prefix}_cta_input"] = st.session_state[f"{key_prefix}_cta"]
        st.success("Reverted to original AI-generated draft.")

    # Show save confirmation after rerun (set before the rerun in save handler).
    if st.session_state.get(f"{key_prefix}_save_toast"):
        st.session_state[f"{key_prefix}_save_toast"] = False
        st.success("Edits saved.")

    new_subject = st.text_input("Subject", value=st.session_state[f"{key_prefix}_subject"],
                                key=f"{key_prefix}_subject_input")
    new_body = st.text_area("Body", value=st.session_state[f"{key_prefix}_body"],
                            height=180, key=f"{key_prefix}_body_input")
    new_cta = st.text_input("CTA", value=st.session_state[f"{key_prefix}_cta"],
                            key=f"{key_prefix}_cta_input")

    btn1, btn2 = st.columns([1, 1])
    with btn1:
        save_clicked = st.button("Save edits", key=f"{key_prefix}_save", use_container_width=True)
    with btn2:
        revert_requested = st.button(
            "Revert to original",
            key=f"{key_prefix}_revert",
            use_container_width=True,
        )

    # -- Save edits --
    if save_clicked:
        st.session_state["active_account_expander"] = aid
        st.session_state[f"{key_prefix}_subject"] = new_subject
        st.session_state[f"{key_prefix}_body"] = new_body
        st.session_state[f"{key_prefix}_cta"] = new_cta

        orig_subject = st.session_state[f"{key_prefix}_orig_subject"]
        orig_body = st.session_state[f"{key_prefix}_orig_body"]
        orig_cta = st.session_state[f"{key_prefix}_orig_cta"]
        if (new_subject, new_body, new_cta) == (orig_subject, orig_body, orig_cta):
            edited.discard(aid)
        else:
            edited.add(aid)

        result["email"] = {"subject_line": new_subject, "body": new_body, "cta": new_cta}
        _apply_edit_to_bulk_summary(aid, new_subject, new_body, new_cta)
        st.session_state[f"{key_prefix}_save_toast"] = True
        st.rerun()

    # -- Revert: two-step confirmation to prevent accidental data loss --
    if revert_requested:
        st.session_state["active_account_expander"] = aid
        st.session_state[f"{key_prefix}_confirm_revert"] = True

    if st.session_state.get(f"{key_prefix}_confirm_revert"):
        st.warning("This will revert all changes you saved for this account. Are you sure?")
        c_yes, c_no = st.columns(2)
        with c_yes:
            if st.button("Confirm", key=f"{key_prefix}_confirm_yes", use_container_width=True):
                st.session_state["active_account_expander"] = aid
                st.session_state[f"{key_prefix}_confirm_revert"] = False
                orig_s = st.session_state[f"{key_prefix}_orig_subject"]
                orig_b = st.session_state[f"{key_prefix}_orig_body"]
                orig_c = st.session_state[f"{key_prefix}_orig_cta"]
                # Update non-widget state (widget keys set in phase 2 at top of next render).
                st.session_state[f"{key_prefix}_subject"] = orig_s
                st.session_state[f"{key_prefix}_body"] = orig_b
                st.session_state[f"{key_prefix}_cta"] = orig_c
                edited.discard(aid)
                result["email"] = {"subject_line": orig_s, "body": orig_b, "cta": orig_c}
                _apply_edit_to_bulk_summary(aid, orig_s, orig_b, orig_c)
                st.session_state[f"{key_prefix}_revert_confirmed"] = True
                st.rerun()
        with c_no:
            if st.button("Cancel", key=f"{key_prefix}_confirm_no", use_container_width=True):
                st.session_state["active_account_expander"] = aid
                st.session_state[f"{key_prefix}_confirm_revert"] = False

    copyable_block(
        "Copy-ready email",
        f"Subject: {st.session_state[f'{key_prefix}_subject']}\n\n"
        f"{st.session_state[f'{key_prefix}_body']}\n\n"
        f"{st.session_state[f'{key_prefix}_cta']}",
    )

    questions = result.get("discovery_questions", [])
    if questions:
        with st.expander("Discovery questions", expanded=False):
            for i, q in enumerate(questions, 1):
                st.write(f"{i}. {q}")

    flags = result.get("flags", [])
    if flags:
        with st.expander("Flags", expanded=False):
            for f in flags:
                st.write(f"- {f}")

    st.markdown("---")
    col_dl1, col_dl2 = st.columns(2)
    cur_subject = st.session_state.get(f"{key_prefix}_subject", email.get("subject_line", ""))
    cur_body = st.session_state.get(f"{key_prefix}_body", email.get("body", ""))
    cur_cta = st.session_state.get(f"{key_prefix}_cta", email.get("cta", ""))
    with col_dl1:
        if account:
            export = build_prospecting_export(result, account)
            st.download_button(
                "Download CRM export",
                data=export.to_json(),
                file_name=f"prospecting_{aid}.json",
                mime="application/json",
                use_container_width=True,
            )
    with col_dl2:
        email_text = f"Subject: {cur_subject}\n\n{cur_body}\n\n{cur_cta}"
        st.download_button(
            "Download email",
            data=email_text,
            file_name=f"email_{aid}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with st.expander("Technical details", expanded=False):
        st.json(result)


def _render_map_result(result: dict) -> None:
    tier = result.get("confidence_tier", "?")
    score = result.get("confidence_score")

    st.markdown("#### Outcome")
    st.markdown(
        f"Evidence **{result.get('evidence_id')}** &rarr; {confidence_pill(tier, score)}",
        unsafe_allow_html=True,
    )

    t1, t2, t3 = st.columns(3)
    with t1:
        st.markdown("**Status**")
    with t2:
        st.markdown("**Confidence score**")
    with t3:
        st.markdown("**Audit retries**")

    v1, v2, v3 = st.columns(3)
    with v1:
        st.markdown(audit_badge(result.get("judge_pass")), unsafe_allow_html=True)
    with v2:
        st.markdown(f"{score} / 100" if score is not None else "N/A")
    with v3:
        st.markdown(str(result.get("correction_attempts_used", 0)))

    risks = result.get("risk_factors", [])
    if risks:
        st.markdown("**Risk factors**")
        st.markdown(risk_chips(risks), unsafe_allow_html=True)

    # Parsed evidence preview (markdown) — from parse_summary if available
    parse_summary = result.get("parse_summary")
    if parse_summary:
        with st.expander("Commitment summary", expanded=False):
            committer = parse_summary.get("committer_name") or "Unknown"
            committer_title = parse_summary.get("committer_title") or ""
            source = parse_summary.get("source_directness", "unknown").replace("_", " ").title()
            campaigns = parse_summary.get("campaigns", [])
            blockers = parse_summary.get("blockers", [])
            quarters = parse_summary.get("total_quarters", 0)

            st.markdown(
                f"**Committer:** {committer}"
                + (f", {committer_title}" if committer_title else "")
                + f"  \n**Source:** {source}"
                + f"  \n**Campaigns:** {len(campaigns)}"
                + f" across {quarters} quarter(s)"
            )
            if campaigns:
                year, rows = _build_commitment_calendar_rows(parse_summary)
                st.markdown(f"**Commitment Calendar - {year}**")
                st.table(rows)

                ambiguities = parse_summary.get("commitment_ambiguities") or []
                strategy = parse_summary.get("commitment_strategy")
                if strategy or ambiguities:
                    with st.expander("Extraction diagnostics", expanded=False):
                        if strategy:
                            st.markdown(f"**Strategy:** `{strategy}`")
                        if ambiguities:
                            st.markdown("**Ambiguities:**")
                            for a in ambiguities:
                                st.markdown(f"- {a}")
            if blockers:
                st.markdown("**Blockers:** " + ", ".join(blockers))

    # Score breakdown transparency (always visible)
    breakdown = result.get("score_breakdown")
    with st.expander("Score breakdown", expanded=False):
        if breakdown:
            st.markdown(
                f"**Base:** {breakdown.get('base', 0)}  \n"
                f"**Source directness:** +{breakdown.get('source_directness', 0)}  \n"
                f"**Campaign count:** +{breakdown.get('campaign_count', 0)}  \n"
                f"**Quarter span:** +{breakdown.get('quarter_span', 0)}  \n"
                f"**Blocker penalty:** {breakdown.get('blocker_penalty', 0)}  \n"
                f"**Positive language:** +{breakdown.get('language_positive', 0)}  \n"
                f"**Negative language:** {breakdown.get('language_negative', 0)}  \n"
                f"**Scoring version:** {breakdown.get('scoring_version', 'N/A')}"
            )
        else:
            # Keep section non-empty even if older payloads lack breakdown fields.
            st.markdown(
                f"**Base:** 20  \n"
                f"**Source directness:** {'applied' if result.get('risk_factors') else 'applied'}  \n"
                f"**Campaign count:** Derived from parsed commitments  \n"
                f"**Quarter span:** Derived from parsed commitments  \n"
                f"**Blocker penalty:** Derived from risk factors  \n"
                f"**Positive language:** Derived from language heuristics  \n"
                f"**Negative language:** Derived from language heuristics  \n"
                f"**Scoring version:** {result.get('scoring_version', 'map_v1.0')}"
            )

    with st.expander("Why this confidence tier?", expanded=False):
        if tier in ("HIGH", "MEDIUM", "LOW") and score is not None:
            st.markdown(explain_threshold(tier, score, risks))
            for r in explain_tier_assignment(score, risks):
                st.write(f"- {r}")
        else:
            st.write("Tier assignment details unavailable.")

    actions = result.get("recommended_actions", [])
    if actions:
        with st.expander("Recommended actions", expanded=False):
            for i, a in enumerate(actions, 1):
                st.write(f"{i}. {a}")

    threshold_text = ""
    if tier in ("HIGH", "MEDIUM", "LOW") and score is not None:
        threshold_text = explain_threshold(tier, score, risks)
    export = build_map_export(result, threshold_rationale=threshold_text)
    st.download_button(
        "Download CRM export",
        data=export.to_json(),
        file_name=f"map_{result.get('evidence_id', 'unknown')}.json",
        mime="application/json",
        use_container_width=True,
    )

    with st.expander("Technical details", expanded=False):
        st.json(result)


def _build_commitment_calendar_rows(parse_summary: dict) -> tuple[int, list[dict[str, str]]]:
    year = parse_summary.get("commitment_year") or dt.datetime.now().year
    campaigns = parse_summary.get("campaigns", [])
    quarter_cols = ["Q1", "Q2", "Q3", "Q4"]
    pretty_name = {
        "launch_email": "Launch Email",
        "benefits_insert": "Benefits Insert",
        "manager_toolkit": "Manager Toolkit",
        "email_blast": "Email Blast",
        "posters": "Posters",
        "quarterly_campaign": "Quarterly Campaign",
    }
    row_order = [
        "launch_email",
        "benefits_insert",
        "manager_toolkit",
        "email_blast",
        "posters",
        "quarterly_campaign",
    ]

    row_map: dict[str, set[str]] = {}
    for c in campaigns:
        ctype = c.get("campaign_type", "unknown")
        q = (c.get("quarter") or "").upper()
        if q not in quarter_cols:
            continue
        row_map.setdefault(ctype, set()).add(q)

    ordered_types = [k for k in row_order if k in row_map] + [
        k for k in row_map if k not in row_order
    ]
    rows: list[dict[str, str]] = []
    for ctype in ordered_types:
        row = {"Initiative": pretty_name.get(ctype, ctype.replace("_", " ").title())}
        for q in quarter_cols:
            row[q] = "Committed" if q in row_map[ctype] else ""
        rows.append(row)
    return year, rows


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _render_account_markdown(account: dict) -> None:
    """Render account details as a readable markdown preview."""
    contact = account.get("contact", {})
    contact_name = contact.get("name") or "Not identified"
    contact_title = contact.get("title") or "N/A"
    rh = account.get("reachability_hint")
    reach_line = (
        f"**Reachability hint (demo):** {rh}/100  \n"
        if isinstance(rh, int)
        else ""
    )
    st.markdown(
        f"**Company:** {account.get('company', 'N/A')}  \n"
        f"**Industry:** {account.get('industry', 'N/A')}  \n"
        f"**Size:** {account.get('us_employees', 'N/A'):,} US employees  \n"
        f"**Primary contact:** {contact_name}, {contact_title}  \n"
        f"**Health plan:** {account.get('health_plan', 'N/A')}  \n"
        f"{reach_line}"
        f"**Notes:** {account.get('notes', 'None')}"
    )


def _render_bulk_summary(summary: BulkRunSummary) -> None:
    """Render the bulk run summary cards and per-account expanders."""
    edited = st.session_state.get("edited_accounts", set())
    edited_count = len(edited)

    st.markdown("### Run summary")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total accounts", summary.total)
    with c2:
        st.metric("Ready to Send", summary.passed)
    with c3:
        st.metric("Needs Review", summary.review)
    with c4:
        st.metric("Accounts skipped", getattr(summary, "policy_skipped", 0))
    with c5:
        st.metric("Email edits", f"{edited_count}/{summary.total}")
    with st.expander("Run details", expanded=False):
        qm = getattr(summary, "queue_mode", "file_order")
        st.caption(
            f"Duration: {summary.duration_ms / 1000:.1f}s · Queue: **{qm}**"
        )

    active_aid = st.session_state.get("active_account_expander")

    if getattr(summary, "policy_skipped", 0) > 0:
        st.warning(
            f"{summary.policy_skipped} account(s) were skipped by data-quality policy "
            "(no generation run for those rows)."
        )

    if summary.pass_rows:
        st.markdown("#### Ready to Send")
        sorted_pass = sorted(summary.pass_rows,
                             key=lambda r: r.output.quality_score if r.output else 0,
                             reverse=True)
        for row in sorted_pass:
            assert row.output is not None
            aid = row.account_id
            edit_flag = "✅" if aid in edited else ""
            label = (f"{row.account_payload.get('company', aid)} — "
                     f"Account Score {row.output.quality_score:.1f}/5"
                     f"{' — edited' if edit_flag else ''}")
            with st.expander(label, expanded=(aid == active_aid)):
                _render_prospecting_result(row.output.model_dump(), account=row.account_payload)

    if summary.review_rows:
        st.markdown("#### Needs Review")
        for row in summary.review_rows:
            assert row.output is not None
            aid_r = row.account_id
            with st.expander(
                f"{row.account_payload.get('company', aid_r)} — review",
                expanded=(aid_r == active_aid),
            ):
                _render_prospecting_result(row.output.model_dump(), account=row.account_payload)

    if getattr(summary, "policy_skip_rows", None) and summary.policy_skip_rows:
        st.markdown("#### Accounts skipped")
        for row in summary.policy_skip_rows:
            assert row.output is not None
            reasons = ", ".join(row.output.skip_reasons) if row.output.skip_reasons else "policy"
            st.info(
                f"**{row.account_payload.get('company', row.account_id)}** — skipped ({reasons})."
            )

    if summary.error_rows:
        st.markdown("#### Errors")
        for row in summary.error_rows:
            with st.expander(f"{row.account_payload.get('company', row.account_id)} — error"):
                st.error(row.error or "Unknown pipeline error")


def _render_handoff_panel(summary: BulkRunSummary) -> None:
    """Render the one-CTA handoff panel with pre-handoff summary."""
    st.markdown("---")
    st.markdown("### Handoff")

    st.info(
        f"**{summary.passed}** account(s) will be packaged for **local simulated** sequencer + CRM stubs.  \n"
        f"**{summary.review + summary.errors}** account(s) will be routed to the review queue.  \n"
        "This demo does **not** call live Outreach or Salesforce—artifacts are written under **`out/`** only."
    )

    if st.button("Submit Now", type="primary", use_container_width=True,
                  disabled=(summary.total == 0)):
        with st.spinner("Processing handoff..."):
            result = handoff_orchestrator(summary)
        st.session_state["last_handoff_result"] = result
        st.success(
            f"Handoff complete — {len(result.sequencer_payloads)} draft(s) written to the **local** sequencer stub, "
            f"{len(result.crm_manifest)} CRM manifest row(s) in the **simulated** archive, "
            f"{len(result.review_queue)} routed to the local review queue."
        )
    elif st.session_state.get("last_handoff_result"):
        result = st.session_state["last_handoff_result"]
        st.success(
            f"Last handoff — {len(result.sequencer_payloads)} draft(s) to local sequencer stub, "
            f"{len(result.crm_manifest)} row(s) to simulated CRM manifest, "
            f"{len(result.review_queue)} to review queue."
        )

    with st.expander("Future production capabilities", expanded=False):
        st.markdown(
            "**Salesforce (when connected):** OAuth + scoped API user, field mapping, idempotent upserts, "
            "sandbox validation before production.\n\n"
            "*Live sequencer push (Outreach, etc.) is not connected—**Submit Now** writes local stubs only.*"
        )

    with st.expander("Secondary actions", expanded=False):
        st.caption("Copy or export individual items for offline use.")
        if summary.pass_rows:
            all_emails = ""
            for r in summary.pass_rows:
                assert r.output is not None
                aid = r.account_id
                kp = f"edit_{aid}"
                subj = st.session_state.get(f"{kp}_subject", r.output.email.subject_line)
                bod = st.session_state.get(f"{kp}_body", r.output.email.body)
                ct = st.session_state.get(f"{kp}_cta", r.output.email.cta)
                all_emails += f"--- {r.account_payload.get('company', aid)} ---\n"
                all_emails += f"Subject: {subj}\n\n{bod}\n\nCTA: {ct}\n\n"
            st.download_button(
                "Download all emails",
                data=all_emails,
                file_name="bulk_emails.txt",
                mime="text/plain",
            )
            manifest = []
            for r in summary.pass_rows:
                if not r.output:
                    continue
                lin = LineageExportBlock(
                    correlation_id=summary.run_id,
                    prospecting_run_id=summary.run_id,
                )
                manifest.append(
                    asdict(build_prospecting_export(r.output.model_dump(), r.account_payload, lineage=lin))
                )
            st.download_button(
                "Download CRM manifest",
                data=json.dumps(manifest, indent=2),
                file_name="crm_manifest.json",
                mime="application/json",
            )
        if getattr(summary, "policy_skip_rows", None) and summary.policy_skip_rows:
            dq_manifest = [
                {
                    "account_id": r.account_id,
                    "company": r.account_payload.get("company"),
                    "skip_reasons": list(r.output.skip_reasons) if r.output else [],
                }
                for r in summary.policy_skip_rows
            ]
            st.download_button(
                "Download DQ manifest",
                data=json.dumps(dq_manifest, indent=2),
                file_name="dq_manifest.json",
                mime="application/json",
            )


def _render_slide_footer_nav(slide: int) -> None:
    """Consistent Back / Next footer at the bottom of every slide."""
    st.markdown("---")
    col_back, col_center, col_next = st.columns([1, 2, 1])

    with col_center:
        st.caption(f"Step {slide} of 3")

    if slide > 1:
        with col_back:
            if st.button("Back", key=f"slide_back_{slide}", use_container_width=True):
                _go_to_slide(slide - 1)

    if slide < 3:
        can_next = (
            _can_go_next_from_slide1() if slide == 1
            else _can_go_next_from_slide2()
        )
        with col_next:
            if not can_next:
                st.button(
                    "Next", key=f"slide_next_{slide}", disabled=True, use_container_width=True,
                    help="Run prospecting first to proceed." if slide == 1 else "No results to review.",
                )
            else:
                if st.button("Next", key=f"slide_next_{slide}", type="primary", use_container_width=True):
                    _go_to_slide(slide + 1)


# ---------------------------------------------------------------------------
# Slide 1: Setup and Run
# ---------------------------------------------------------------------------

def _render_prospecting_slide1_setup() -> None:
    source = st.selectbox(
        "Data source", ["Test Data", "Clay"],
        help="Choose where your account list comes from.",
    )

    if source == "Clay":
        st.info(
            "**Production connector — not wired in this build.**\n\n"
            "- RevOps-assigned account lists from Clay\n"
            "- Scheduled sync and list membership rules\n"
            "- CRM-ready field mapping\n\n"
            "Use **Test Data** to run the enclosed demo today."
        )
        st.caption("Switch to Test Data to run the agent with sample accounts.")
        _render_slide_footer_nav(1)
        return

    st.caption(
        "Book: static fixture (demo). Production: last sync from Clay/CRM."
    )

    run_mode = st.radio(
        "Run mode",
        ["Bulk list (all accounts)", "Single account"],
        horizontal=True,
        help="Bulk processes all accounts at once. Single lets you inspect one at a time.",
    )

    accounts = _load_accounts()
    if not accounts:
        render_empty_state("No accounts found in data/accounts.json.")
        _render_slide_footer_nav(1)
        return

    if run_mode == "Bulk list (all accounts)":
        st.caption(f"{len(accounts)} accounts loaded from test data.")

        queue_mode = "file_order"
        with st.expander("Advanced options", expanded=False):
            qm_label = st.radio(
                "Bulk processing order",
                ["File order (default)", "Heuristic priority (demo)"],
                horizontal=True,
                key="bulk_queue_mode_ui",
                help="Heuristic ranks by ICP fit score + optional reachability hint (0–100); no extra LLM call.",
            )
            queue_mode = "heuristic" if qm_label.startswith("Heuristic") else "file_order"
            st.caption(
                "Company context uses repo stubs in this build—no live LinkedIn/news API."
            )

        with st.expander("Preview accounts", expanded=False):
            for a in accounts:
                _render_account_markdown(a)
                st.markdown("---")

        if st.button("Run prospecting", type="primary", use_container_width=True):
            with st.spinner(f"Running prospecting for {len(accounts)} accounts..."):
                try:
                    summary = _run_prospecting_bulk_compat(
                        accounts,
                        actor_role=st.session_state["role"],
                        source="test_data",
                        queue_mode=queue_mode,
                    )
                except PermissionError as e:
                    render_permission_error(e)
                    return
                except RuntimeError as e:
                    render_runtime_error(e)
                    return
            st.session_state["last_bulk_summary"] = summary

        if st.session_state.get("last_bulk_summary"):
            st.success("Prospecting run complete. Click **Next** to view results.")
    else:
        st.caption("Select an account for a single prospecting run.")
        labels = [f'{a["company"]}  ({a["industry"]})' for a in accounts]
        idx = st.selectbox("Select account", range(len(labels)), format_func=lambda i: labels[i])
        account = accounts[idx]

        with st.expander("Account details", expanded=False):
            _render_account_markdown(account)

        if st.button("Run prospecting", type="primary", use_container_width=True):
            with st.spinner("Running prospecting pipeline..."):
                try:
                    result = run_prospecting(account, actor_role=st.session_state["role"]).model_dump()
                except PermissionError as e:
                    render_permission_error(e)
                    return
                except RuntimeError as e:
                    render_runtime_error(e)
                    return
                except Exception as e:
                    st.error(f"Unexpected error: {e}")
                    st.caption("Try again or contact your administrator.")
                    return
            st.session_state["last_prospecting_result"] = result
            st.session_state["last_prospecting_account"] = account

        if st.session_state.get("last_prospecting_result"):
            st.success("Prospecting run complete. Click **Next** to view results.")

    _render_slide_footer_nav(1)


# ---------------------------------------------------------------------------
# Slide 2: Results
# ---------------------------------------------------------------------------

def _render_prospecting_slide2_results() -> None:
    summary: BulkRunSummary | None = st.session_state.get("last_bulk_summary")
    single_result = st.session_state.get("last_prospecting_result")

    if summary:
        _render_bulk_summary(summary)
        _render_promote_to_map_expander(summary=summary)
    elif single_result:
        _render_prospecting_result(
            single_result,
            account=st.session_state.get("last_prospecting_account"),
        )
        _render_promote_to_map_expander(
            single_result=single_result,
            single_account=st.session_state.get("last_prospecting_account"),
        )
    else:
        st.info("No results yet. Go back to Slide 1 and run prospecting.")

    _render_slide_footer_nav(2)


# ---------------------------------------------------------------------------
# Slide 3: Handoff
# ---------------------------------------------------------------------------

def _render_prospecting_slide3_handoff() -> None:
    summary: BulkRunSummary | None = st.session_state.get("last_bulk_summary")
    single_result = st.session_state.get("last_prospecting_result")

    if summary:
        _render_handoff_panel(summary)
    elif single_result:
        st.info(
            "Handoff is available for bulk runs. Re-run in bulk mode "
            "on Slide 1 to enable the full handoff workflow."
        )
    else:
        st.info("No results to hand off. Go back and run prospecting first.")

    _render_slide_footer_nav(3)


# ---------------------------------------------------------------------------
# Page router
# ---------------------------------------------------------------------------

def _page_prospecting() -> None:
    if "prospecting_slide" not in st.session_state:
        st.session_state["prospecting_slide"] = 1

    slide = _get_current_slide()
    st.header("Prospecting")

    if slide == 1:
        _render_prospecting_slide1_setup()
    elif slide == 2:
        _render_prospecting_slide2_results()
    elif slide == 3:
        _render_prospecting_slide3_handoff()


# ---------------------------------------------------------------------------
# MAP slide navigation helpers
# ---------------------------------------------------------------------------

def _get_current_map_slide() -> int:
    return st.session_state.get("map_slide", 1)


def _go_to_map_slide(target: int) -> None:
    if target < 1 or target > 3:
        return
    st.session_state["map_slide"] = target
    st.rerun()


def _can_go_next_from_map_slide1() -> bool:
    return (
        st.session_state.get("last_map_bulk_summary") is not None
        or st.session_state.get("last_map_result") is not None
    )


def _can_go_next_from_map_slide2() -> bool:
    return _can_go_next_from_map_slide1()


def _render_map_slide_footer_nav(slide: int) -> None:
    st.markdown("---")
    col_back, col_center, col_next = st.columns([1, 2, 1])

    with col_center:
        st.caption(f"Step {slide} of 3")

    if slide > 1:
        with col_back:
            if st.button("Back", key=f"map_slide_back_{slide}", use_container_width=True):
                _go_to_map_slide(slide - 1)

    if slide < 3:
        can_next = (
            _can_go_next_from_map_slide1() if slide == 1
            else _can_go_next_from_map_slide2()
        )
        with col_next:
            if not can_next:
                st.button(
                    "Next", key=f"map_slide_next_{slide}", disabled=True, use_container_width=True,
                    help="Run MAP verification first to proceed." if slide == 1 else "No results to review.",
                )
            else:
                if st.button("Next", key=f"map_slide_next_{slide}", type="primary", use_container_width=True):
                    _go_to_map_slide(slide + 1)


# ---------------------------------------------------------------------------
# MAP bulk summary
# ---------------------------------------------------------------------------

def _render_map_bulk_summary(summary: BulkMapSummary) -> None:
    st.markdown("### Run summary")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total evidence", summary.total)
    with c2:
        st.metric("Passed audit", summary.passed)
    with c3:
        st.metric("Needs review", summary.review)
    with c4:
        st.metric("Errors", summary.errors)
    st.caption(f"Run completed in {summary.duration_ms / 1000:.1f}s")

    active_eid = st.session_state.get("active_map_evidence_expander")

    if summary.pass_rows:
        st.markdown("#### Passed audit")
        for row in summary.pass_rows:
            assert row.output is not None
            eid = row.evidence_id
            label = (
                f"Evidence {eid} — {row.output.confidence_tier} "
                f"(score {row.output.confidence_score})"
            )
            with st.expander(label, expanded=(eid == active_eid)):
                _render_map_result(row.output.model_dump())

    if summary.review_rows:
        st.markdown("#### Needs review")
        for row in summary.review_rows:
            assert row.output is not None
            eid = row.evidence_id
            label = (
                f"Evidence {eid} — {row.output.confidence_tier} "
                f"(score {row.output.confidence_score})"
            )
            with st.expander(label, expanded=(eid == active_eid)):
                _render_map_result(row.output.model_dump())

    if summary.error_rows:
        st.markdown("#### Errors")
        for row in summary.error_rows:
            with st.expander(f"Evidence {row.evidence_id} — error"):
                st.error(row.error or "Unknown pipeline error")


# ---------------------------------------------------------------------------
# MAP handoff panel
# ---------------------------------------------------------------------------

def _render_map_handoff_panel(summary: BulkMapSummary) -> None:
    st.markdown("---")
    st.markdown("### Handoff")

    st.info(
        f"**{summary.passed}** evidence item(s) will be packaged into a **local simulated** CRM manifest "
        f"(including **recommended actions** for each row—map to a CRM long-text field in production).  \n"
        f"**{summary.review + summary.errors}** item(s) will be routed to the review queue.  \n"
        "This demo does **not** POST to Salesforce—artifacts land under **`out/`** only."
    )

    if st.button("Submit Now", type="primary", use_container_width=True,
                  key="map_handoff_submit", disabled=(summary.total == 0)):
        with st.spinner("Processing MAP handoff..."):
            result = map_handoff_orchestrator(summary)
        st.session_state["last_map_handoff_result"] = result
        st.success(
            f"Handoff complete — {len(result.crm_manifest)} row(s) written to the **simulated** CRM manifest, "
            f"{len(result.review_queue)} routed to the local review queue."
        )
    elif st.session_state.get("last_map_handoff_result"):
        result = st.session_state["last_map_handoff_result"]
        st.success(
            f"Last handoff — {len(result.crm_manifest)} row(s) in simulated CRM manifest, "
            f"{len(result.review_queue)} to review queue."
        )

    with st.expander("Future production capabilities", expanded=False):
        st.caption(
            "When Salesforce is connected, MAP exports include CRM handoff state and recommended actions; "
            "this build does not call the live API."
        )

    with st.expander("Secondary actions", expanded=False):
        st.caption("Download exports for offline use.")
        if summary.pass_rows:
            manifest_data = []
            for r in summary.pass_rows:
                assert r.output is not None
                res = r.output.model_dump()
                threshold_text = ""
                tier = res.get("confidence_tier", "")
                sc = res.get("confidence_score")
                rk = res.get("risk_factors", [])
                if tier in ("HIGH", "MEDIUM", "LOW") and sc is not None:
                    threshold_text = explain_threshold(tier, sc, rk)
                lin = LineageExportBlock(
                    correlation_id=summary.run_id,
                    map_run_id=summary.run_id,
                    evidence_id=str(res.get("evidence_id", "")),
                )
                manifest_data.append(
                    asdict(
                        build_map_export(res, threshold_rationale=threshold_text, lineage=lin)
                    )
                )
            st.download_button(
                "Download CRM manifest",
                data=json.dumps(manifest_data, indent=2),
                file_name="map_crm_manifest.json",
                mime="application/json",
            )
            revops_md = "\n".join(f"- {x}" for x in manifest_data[0].get("revops_review_checklist", []))
            st.download_button(
                "Download RevOps checklist",
                data="# RevOps review checklist\n\n" + revops_md,
                file_name="map_revops_checklist.md",
                mime="text/markdown",
            )


# ---------------------------------------------------------------------------
# MAP Slide 1: Setup and Run
# ---------------------------------------------------------------------------

def _render_map_slide1_setup() -> None:
    ev_src = st.selectbox(
        "Evidence source",
        ["Samples and structured capture (demo)", "Evidence database (n8n) — production"],
        key="map_evidence_source_main",
        help="Demo uses local JSON. Production uses n8n-fed evidence and retrieval.",
    )

    if ev_src.startswith("Evidence database"):
        st.info(
            "**Production connector — not wired in this build.**\n\n"
            "- n8n workflows publish commitment evidence payloads\n"
            "- Vector store retrieval scoped to employer account\n"
            "- Account-scoped document chunks for MAP context layers\n\n"
            "Use **Samples and structured capture** to run MAP in this demo."
        )
        st.caption("Future HTTP shape is sketched in `docs/ingest_contract.md`.")
        with st.expander("Summarized evidence pack (production)", expanded=False):
            st.markdown(
                "- Optional LLM layer condensing multi-source evidence before MAP scoring\n"
                "- Governance hooks for PII and retention classes\n"
                "- Out of scope for the enclosed prototype"
            )
        _render_map_slide_footer_nav(1)
        return

    st.caption("Verify evidence and confidence.")

    run_mode = st.radio(
        "Run mode",
        ["All sample evidence", "Single evidence"],
        horizontal=True,
        key="map_run_mode",
        help="Bulk processes all evidence at once. Single lets you inspect one at a time.",
    )

    if run_mode == "All sample evidence":
        raw_items = _load_evidence()
        if not raw_items:
            render_empty_state("No evidence items found in data/map_evidence.json.")
            _render_map_slide_footer_nav(1)
            return

        combine_two = st.checkbox(
            "Combine two samples (demo)",
            value=False,
            key="map_combine_two_samples",
            help="Merges the first two JSON fixtures into one verification input (multi-fragment demo).",
        )
        evidence_items = list(raw_items)
        if combine_two and len(raw_items) >= 2:
            evidence_items = [combine_first_two_map_evidence(raw_items)]

        st.caption(f"{len(evidence_items)} evidence item(s) loaded for this run.")

        with st.expander("Preview evidence", expanded=False):
            for e in evidence_items:
                st.markdown(
                    f"**Evidence {e['evidence_id']}**  \n"
                    f"{e['text'][:200]}{'...' if len(e['text']) > 200 else ''}"
                )
                st.markdown("---")

        with st.expander("Future production capabilities", expanded=False):
            st.markdown(
                "- **Summarized evidence pack:** optional LLM layer across channels before MAP scoring.\n"
                "- **Evidence database:** n8n-fed retrieval (choose *Evidence database* above)."
            )

        if st.button("Run MAP verification", type="primary", use_container_width=True):
            with st.spinner(f"Running MAP verification for {len(evidence_items)} items..."):
                try:
                    summary = run_map_verification_bulk(
                        evidence_items, actor_role=st.session_state["role"],
                    )
                except PermissionError as e:
                    render_permission_error(e)
                    _render_map_slide_footer_nav(1)
                    return
                except RuntimeError as e:
                    render_runtime_error(e)
                    _render_map_slide_footer_nav(1)
                    return
            st.session_state["last_map_bulk_summary"] = summary
            st.session_state.pop("last_map_result", None)

        if st.session_state.get("last_map_bulk_summary"):
            st.success("MAP verification run complete. Click **Next** to view results.")

    else:
        bridge_txt = st.session_state.get("map_bridge_text")
        if bridge_txt:
            st.markdown("#### Promoted from Prospecting (optional)")
            st.caption("Review promoted outreach text, then run MAP. This panel clears after a successful run.")
            peid = st.text_input(
                "Evidence ID",
                value=st.session_state.get("map_bridge_evidence_id", "promote"),
                key="map_bridge_evidence_id_input",
            )
            ptxt = st.text_area(
                "Evidence text",
                value=bridge_txt,
                height=220,
                key="map_bridge_text_area",
            )
            pr_run = st.session_state.get("map_bridge_pr") or ""
            aid_raw = (st.session_state.get("map_bridge_account_id") or "").strip()
            account_id_bridge = int(aid_raw) if aid_raw.isdigit() else None
            if st.button("Run MAP verification", type="primary", use_container_width=True, key="map_bridge_run"):
                with st.spinner("Running MAP verification..."):
                    try:
                        result = run_map_verification(
                            peid,
                            ptxt,
                            actor_role=st.session_state["role"],
                            prospecting_run_id=pr_run or None,
                            account_id=account_id_bridge,
                            correlation_id=pr_run or None,
                        ).model_dump()
                    except PermissionError as e:
                        render_permission_error(e)
                        _render_map_slide_footer_nav(1)
                        return
                    except RuntimeError as e:
                        render_runtime_error(e)
                        _render_map_slide_footer_nav(1)
                        return
                    except Exception as e:
                        st.error(f"Unexpected error: {e}")
                        st.caption("Try again or contact your administrator.")
                        _render_map_slide_footer_nav(1)
                        return
                st.session_state["last_map_result"] = result
                st.session_state.pop("last_map_bulk_summary", None)
                for k in (
                    "map_bridge_text",
                    "map_bridge_evidence_id",
                    "map_bridge_pr",
                    "map_bridge_account_id",
                ):
                    st.session_state.pop(k, None)
                st.success("MAP verification complete. Click **Next** to view results.")
            st.markdown("---")

        mode = st.radio(
            "Input mode",
            ["Select sample evidence", "Structured capture"],
            horizontal=True,
            key="map_input_mode",
        )

        evidence_id = ""
        custom_text = ""

        if mode == "Select sample evidence":
            evidence_items = _load_evidence()
            if not evidence_items:
                render_empty_state("No evidence items found in data/map_evidence.json.")
                _render_map_slide_footer_nav(1)
                return
            labels = [f'Evidence {e["evidence_id"]}' for e in evidence_items]
            idx = st.selectbox("Select evidence", range(len(labels)), format_func=lambda i: labels[i])
            evidence = evidence_items[idx]
            evidence_id = evidence["evidence_id"]
            custom_text = st.text_area("Evidence text (editable)", value=evidence["text"], height=180)
        else:
            evidence_id = st.text_input("Evidence ID", value="NEW")
            source_type = st.selectbox("Source type", ["Email", "Call notes", "Slack", "Meeting notes"])
            c1, c2 = st.columns(2)
            with c1:
                committer_name = st.text_input("Committer name")
            with c2:
                committer_title = st.text_input("Committer title")
            commitment_language = st.text_area("Commitment language", value="We are ready to move forward.")
            c3, c4 = st.columns(2)
            with c3:
                campaign_type = st.selectbox("Campaign type", ["launch_email", "benefits_insert", "manager_toolkit"])
            with c4:
                quarter = st.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"], index=1)
            blockers = st.text_input("Blockers (comma-separated)", value="")
            capture = MapCaptureInput(
                evidence_id=evidence_id,
                source_type=source_type,
                committer_name=committer_name or None,
                committer_title=committer_title or None,
                commitment_language=commitment_language,
                campaign_plan=[MapCampaignPlan(campaign_type=campaign_type, quarter=quarter)],
                blockers=[b.strip() for b in blockers.split(",") if b.strip()],
            )
            custom_text = map_capture_to_evidence_text(capture)
            with st.expander("Compiled evidence preview", expanded=True):
                st.markdown(custom_text)
            with st.expander("Raw compiled text", expanded=False):
                st.code(custom_text, language=None)

        if st.button("Run MAP verification", type="primary", use_container_width=True):
            with st.spinner("Running MAP verification..."):
                try:
                    result = run_map_verification(
                        evidence_id, custom_text, actor_role=st.session_state["role"]
                    ).model_dump()
                except PermissionError as e:
                    render_permission_error(e)
                    _render_map_slide_footer_nav(1)
                    return
                except RuntimeError as e:
                    render_runtime_error(e)
                    _render_map_slide_footer_nav(1)
                    return
                except Exception as e:
                    st.error(f"Unexpected error: {e}")
                    st.caption("Try again or contact your administrator.")
                    _render_map_slide_footer_nav(1)
                    return
            st.session_state["last_map_result"] = result
            st.session_state.pop("last_map_bulk_summary", None)

        if st.session_state.get("last_map_result"):
            st.success("MAP verification complete. Click **Next** to view results.")

    _render_map_slide_footer_nav(1)


# ---------------------------------------------------------------------------
# MAP Slide 2: Results
# ---------------------------------------------------------------------------

def _render_map_slide2_results() -> None:
    bulk_summary: BulkMapSummary | None = st.session_state.get("last_map_bulk_summary")
    single_result = st.session_state.get("last_map_result")

    if bulk_summary:
        _render_map_bulk_summary(bulk_summary)
    elif single_result:
        _render_map_result(single_result)
    else:
        st.info("No results yet. Go back to Slide 1 and run MAP verification.")

    _render_map_slide_footer_nav(2)


# ---------------------------------------------------------------------------
# MAP Slide 3: Handoff
# ---------------------------------------------------------------------------

def _render_map_slide3_handoff() -> None:
    bulk_summary: BulkMapSummary | None = st.session_state.get("last_map_bulk_summary")
    single_result = st.session_state.get("last_map_result")

    if bulk_summary:
        _render_map_handoff_panel(bulk_summary)
    elif single_result:
        st.info(
            "Full handoff is available for bulk runs. Re-run in bulk mode "
            "on Slide 1 to enable the consolidated handoff workflow."
        )
        st.markdown("---")
        st.markdown("#### Single export")
        result = single_result
        threshold_text = ""
        tier = result.get("confidence_tier", "")
        sc = result.get("confidence_score")
        rk = result.get("risk_factors", [])
        if tier in ("HIGH", "MEDIUM", "LOW") and sc is not None:
            threshold_text = explain_threshold(tier, sc, rk)
        lin = LineageExportBlock(
            evidence_id=str(result.get("evidence_id", "")),
        )
        export = build_map_export(result, threshold_rationale=threshold_text, lineage=lin)
        st.download_button(
            "Download CRM export",
            data=export.to_json(),
            file_name=f"map_{result.get('evidence_id', 'unknown')}.json",
            mime="application/json",
            use_container_width=True,
        )
        with st.expander("Future production capabilities", expanded=False):
            st.caption(
                "Exports include **simulated** CRM handoff state, recommended actions, and a RevOps checklist; "
                "no live Salesforce API call is made."
            )
    else:
        st.info("No results to hand off. Go back and run MAP verification first.")

    _render_map_slide_footer_nav(3)


# ---------------------------------------------------------------------------
# MAP page router
# ---------------------------------------------------------------------------

def _page_map_review() -> None:
    if "map_slide" not in st.session_state:
        st.session_state["map_slide"] = 1

    slide = _get_current_map_slide()
    st.header("MAP Review")

    if slide == 1:
        _render_map_slide1_setup()
    elif slide == 2:
        _render_map_slide2_results()
    elif slide == 3:
        _render_map_slide3_handoff()


def _page_admin() -> None:
    st.header("Admin panel")
    if st.session_state["role"] != "admin":
        st.info("Admin access required. Switch your role to **admin** in the sidebar.")
        return

    st.subheader("Retention cleanup")
    days = st.number_input("Retention window (days)", min_value=1, value=30)
    if st.button("Run retention cleanup", use_container_width=True):
        try:
            report = enforce_retention(int(days), actor_role="admin")
            st.success(f"Removed {report['rows_removed']} rows older than {days} days.")
        except Exception as e:
            st.error(f"Retention cleanup failed: {e}")

    st.markdown("---")
    st.subheader("Shadow compare")
    shadow_mode = st.radio("Compare type", ["MAP sample", "Prospecting account"], horizontal=True, key="admin_shadow")
    if shadow_mode == "MAP sample":
        evidence_items = _load_evidence()
        if not evidence_items:
            render_empty_state("No evidence data available.")
            return
        labels = [f'Evidence {e["evidence_id"]}' for e in evidence_items]
        idx = st.selectbox("Evidence", range(len(labels)), format_func=lambda i: labels[i], key="admin_map_sel")
        evidence = evidence_items[idx]
        if st.button("Run shadow compare", key="admin_shadow_btn", use_container_width=True):
            with st.spinner("Running shadow comparison..."):
                result = compare_map(evidence["evidence_id"], evidence["text"], actor_role=st.session_state["role"])
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Directional match", "Yes" if result["directional_match"] else "No")
            with col2:
                st.metric("Structural match", "Yes" if result["structural_match"] else "No")
            with st.expander("Full comparison", expanded=False):
                st.json(result)
    else:
        accounts = _load_accounts()
        if not accounts:
            render_empty_state("No account data available.")
            return
        labels = [a["company"] for a in accounts]
        idx = st.selectbox("Account", range(len(labels)), format_func=lambda i: labels[i], key="admin_acc_sel")
        if st.button("Run shadow compare", key="admin_shadow_btn2", use_container_width=True):
            with st.spinner("Running shadow comparison..."):
                result = compare_prospecting(accounts[idx], actor_role=st.session_state["role"])
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Directional match", "Yes" if result["directional_match"] else "No")
            with col2:
                st.metric("Structural match", "Yes" if result["structural_match"] else "No")
            with st.expander("Full comparison", expanded=False):
                st.json(result)

    st.markdown("---")
    st.subheader("Incidents and DLQ")
    dlq_path = Path("out/dlq.jsonl")
    incidents_path = Path("out/incidents.jsonl")
    if dlq_path.exists():
        dlq_lines = dlq_path.read_text(encoding="utf-8").strip().splitlines()
        if dlq_lines:
            with st.expander(f"Dead Letter Queue ({len(dlq_lines)} entries)", expanded=False):
                for line in dlq_lines[-10:]:
                    try:
                        entry = json.loads(line)
                        st.write(f"- **{entry.get('pipeline', '?')}**: {entry.get('error', '?')[:120]}")
                    except Exception:
                        st.write(f"- {line[:120]}")
        else:
            st.caption("DLQ is empty.")
    else:
        st.caption("No DLQ file found.")

    if incidents_path.exists():
        inc_lines = incidents_path.read_text(encoding="utf-8").strip().splitlines()
        if inc_lines:
            with st.expander(f"Incidents ({len(inc_lines)} entries)", expanded=False):
                for line in inc_lines[-10:]:
                    try:
                        entry = json.loads(line)
                        st.write(f"- **{entry.get('severity', '?')}**: {entry.get('message', '?')[:120]}")
                    except Exception:
                        st.write(f"- {line[:120]}")
        else:
            st.caption("No incidents recorded.")
    else:
        st.caption("No incidents file found.")

    st.markdown("---")
    st.subheader("Configuration")
    cfg = load_config()
    st.write({
        "environment": cfg.environment,
        "model_primary": cfg.model_primary,
        "model_fallback": cfg.model_fallback,
        "generation_mode": cfg.generation_mode,
        "claude_available": cfg.has_claude,
        "gemini_available": cfg.has_gemini,
    })
    warnings = validate_startup(cfg)
    if warnings:
        for w in warnings:
            st.warning(w)
    else:
        st.success("All provider keys configured.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _apply_landing_query_params(cfg) -> None:
    """Apply URL query params once per session for Vercel landing deep links.

    - ``page=prospecting`` | ``page=map`` sets initial Navigate target.
    - ``role=admin|user|viewer`` sets initial role in non-production only
      (production remains viewer-locked via :func:`resolve_role`).
    """
    if st.session_state.get("_rula_qs_bridge_done"):
        return
    st.session_state["_rula_qs_bridge_done"] = True
    try:
        qp = st.query_params
    except Exception:
        return
    page_raw = (qp.get("page") or "").strip().lower()
    nav_map = {"prospecting": "Prospecting", "map": "MAP Review"}
    if page_raw in nav_map:
        st.session_state["_ui_nav_page"] = nav_map[page_raw]
    if cfg.environment == "production":
        return
    role_raw = (qp.get("role") or "").strip().lower()
    if role_raw in ("admin", "user", "viewer"):
        st.session_state["role"] = role_raw


def main() -> None:
    st.set_page_config(
        page_title="Rula Revenue Intelligence",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.sidebar.markdown("## Rula Revenue Intelligence")

    cfg = load_config()
    if "role" not in st.session_state:
        st.session_state["role"] = "user"
    _apply_landing_query_params(cfg)
    role_internal = ["admin", "user", "viewer"]
    role_labels = {"admin": "Admin", "user": "User", "viewer": "Viewer"}
    label_to_role = {v: k for k, v in role_labels.items()}
    current = st.session_state["role"]
    if current not in role_internal:
        current = "user"
    is_production = cfg.environment == "production"
    display_options = [role_labels[r] for r in role_internal]
    current_label = role_labels[current]
    selected_label = st.sidebar.selectbox(
        "Your role",
        display_options,
        index=display_options.index(current_label),
        disabled=is_production,
        key="sidebar_role_display",
    )
    st.session_state["role"] = resolve_role(label_to_role[selected_label], environment=cfg.environment)
    if is_production:
        st.sidebar.caption("Role locked in production.")
    st.sidebar.caption(f"Logged in as **{st.session_state['role']}**")

    pages = ["Prospecting", "MAP Review", "Insights"]
    if st.session_state["role"] == "admin":
        pages.append("Admin")
    prev_nav = st.session_state.get("_ui_nav_page", "Prospecting")
    if prev_nav not in pages:
        prev_nav = "Prospecting"
    page = st.sidebar.selectbox(
        "Navigate",
        pages,
        index=pages.index(prev_nav),
        key="sidebar_navigate",
    )
    st.session_state["_ui_nav_page"] = page

    st.sidebar.markdown("---")

    if page == "Prospecting":
        _page_prospecting()
    elif page == "MAP Review":
        _page_map_review()
    elif page == "Insights":
        page_insights()
    elif page == "Admin":
        _page_admin()


if __name__ == "__main__":
    main()
