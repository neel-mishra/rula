"""Insights dashboard page (pipeline metrics, connector health, recent activity)."""

from __future__ import annotations

import datetime

import streamlit as st

from src.telemetry.events import read_events
from src.telemetry.metrics import compute_connector_health_snapshot, compute_metrics


def page_insights() -> None:
    st.header("Insights")
    st.caption("Pipeline performance, provider health, and recent activity.")

    st.subheader("Pipeline metrics")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Prospecting**")
        pm = compute_metrics("prospecting")
        st.metric("Total runs", pm.total_runs)
        st.metric("Success rate", f"{pm.success_count}/{pm.total_runs}" if pm.total_runs else "N/A")
        st.metric("Avg latency", f"{pm.avg_duration_ms:.0f} ms" if pm.total_runs else "N/A")
        if pm.total_runs:
            st.metric("P95 latency", f"{pm.p95_duration_ms:.0f} ms")
    with col2:
        st.markdown("**MAP Verification**")
        mm = compute_metrics("map_verification")
        st.metric("Total runs", mm.total_runs)
        st.metric("Success rate", f"{mm.success_count}/{mm.total_runs}" if mm.total_runs else "N/A")
        st.metric("Avg latency", f"{mm.avg_duration_ms:.0f} ms" if mm.total_runs else "N/A")
        if mm.total_runs:
            st.metric("P95 latency", f"{mm.p95_duration_ms:.0f} ms")

    st.markdown("---")
    st.subheader("Connector health (SLO-style slices)")
    snap = compute_connector_health_snapshot()
    llm_stats = snap.get("llm_by_provider") or {}
    if llm_stats:
        st.caption("LLM router — latency and reliability by **provider** (from generation telemetry).")
        for prov, s in sorted(llm_stats.items()):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric(f"{prov} — samples", int(s.get("samples", 0)))
            with c2:
                st.metric(f"{prov} — avg ms", f"{s.get('avg_ms', 0):.0f}")
            with c3:
                st.metric(f"{prov} — success", f"{s.get('success_rate', 0):.0%}")
            with c4:
                st.metric(f"{prov} — fallback", f"{s.get('fallback_rate', 0):.0%}")
    else:
        st.caption("No generation telemetry yet — run prospecting or MAP with LLM providers enabled.")

    br = snap.get("circuit_breakers") or {}
    if br:
        st.caption("Circuit breakers — recent **open/closed** transitions.")
        for name, states in sorted(br.items()):
            st.write(f"- **{name}**: {states}")
    else:
        st.caption("No circuit breaker transitions recorded.")

    lc = snap.get("lifecycle") or {}
    if lc:
        st.caption("Lifecycle domain events (normalized pipeline milestones).")
        st.write({k: lc[k] for k in sorted(lc.keys())})

    st.markdown("---")
    st.subheader("Provider usage")
    all_m = compute_metrics()
    if all_m.providers_used:
        for provider, count in all_m.providers_used.items():
            st.write(f"- **{provider}**: {count} generations")
        st.metric("Fallback rate", f"{all_m.fallback_rate:.1%}")
    else:
        st.caption("No generation events recorded yet. Run a pipeline to start tracking.")

    st.markdown("---")
    st.subheader("Recent activity")
    events = read_events(limit=50)
    pipeline_events = [e for e in events if e.get("event_type") == "pipeline_complete"]
    if pipeline_events:
        for ev in reversed(pipeline_events[-5:]):
            ts = ev.get("timestamp", 0)
            ts_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "?"
            status = "OK" if ev.get("success") else "FAIL"
            pipe = ev.get("pipeline", "?")
            dur = ev.get("duration_ms", 0)
            icon = "✓" if ev.get("success") else "✗"
            st.write(f"{icon} **{status}**  {pipe}  {dur:.0f}ms  {ts_str}")
    else:
        st.caption("No pipeline runs recorded yet.")

    edge_events = [e for e in events if e.get("event_type") == "edge_case"]
    if edge_events:
        with st.expander(f"Edge cases ({len(edge_events)} events)", expanded=False):
            for ev in edge_events[-10:]:
                st.write(f"- **{ev.get('error', '?')}**: {ev.get('metadata', {}).get('detail', '?')}")

    st.markdown("---")
    st.subheader("Evaluation baselines")
    st.caption("Run `PYTHONPATH=. python3 eval/drift_check.py` and `eval/compare_shadow.py` for live numbers.")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Golden MAP accuracy", "1.00")
    with col2:
        st.metric("Prospecting audit pass", "1.00")
    with col3:
        st.metric("Shadow structural match", "1.00")
