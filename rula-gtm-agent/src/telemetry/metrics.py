from __future__ import annotations

from dataclasses import dataclass
from src.telemetry.events import read_events


@dataclass
class PipelineMetrics:
    total_runs: int
    success_count: int
    failure_count: int
    avg_duration_ms: float
    p95_duration_ms: float
    fallback_rate: float
    providers_used: dict[str, int]


def compute_metrics(pipeline: str | None = None) -> PipelineMetrics:
    events = read_events(limit=1000)
    if pipeline:
        events = [e for e in events if e.get("pipeline") == pipeline]
    run_events = [e for e in events if e.get("event_type") == "pipeline_complete"]
    total = len(run_events)
    if total == 0:
        return PipelineMetrics(
            total_runs=0,
            success_count=0,
            failure_count=0,
            avg_duration_ms=0,
            p95_duration_ms=0,
            fallback_rate=0,
            providers_used={},
        )
    successes = [e for e in run_events if e.get("success")]
    failures = [e for e in run_events if not e.get("success")]
    durations = sorted([e.get("duration_ms", 0) for e in run_events])
    avg_d = sum(durations) / len(durations) if durations else 0
    p95_idx = int(len(durations) * 0.95)
    p95_d = durations[min(p95_idx, len(durations) - 1)]

    providers: dict[str, int] = {}
    fallback_count = 0
    gen_events = [e for e in events if e.get("event_type") == "generation_complete"]
    for e in gen_events:
        p = e.get("provider", "unknown")
        providers[p] = providers.get(p, 0) + 1
        if e.get("fallback_used"):
            fallback_count += 1

    fb_rate = fallback_count / len(gen_events) if gen_events else 0

    return PipelineMetrics(
        total_runs=total,
        success_count=len(successes),
        failure_count=len(failures),
        avg_duration_ms=avg_d,
        p95_duration_ms=p95_d,
        fallback_rate=fb_rate,
        providers_used=providers,
    )


def compute_breaker_metrics() -> dict[str, dict[str, int]]:
    """Count ``circuit_state`` telemetry rows by circuit name and state (open/closed)."""
    events = read_events(limit=2000)
    out: dict[str, dict[str, int]] = {}
    for e in events:
        if e.get("event_type") != "circuit_state":
            continue
        meta = e.get("metadata") or {}
        name = str(meta.get("circuit_name", "unknown"))
        state = str(meta.get("state", "unknown"))
        if name not in out:
            out[name] = {}
        out[name][state] = out[name].get(state, 0) + 1
    return out


def compute_llm_connector_stats() -> dict[str, dict[str, float]]:
    """Per-provider generation latency / success / fallback from ``generation_complete`` events."""
    events = read_events(limit=2000)
    gen = [e for e in events if e.get("event_type") == "generation_complete"]
    by_prov: dict[str, list[dict]] = {}
    for e in gen:
        p = str(e.get("provider", "unknown"))
        by_prov.setdefault(p, []).append(e)
    stats: dict[str, dict[str, float]] = {}
    for p, rows in by_prov.items():
        durs = [float(r.get("duration_ms", 0)) for r in rows]
        n = len(rows)
        succ = sum(1 for r in rows if r.get("success"))
        fb = sum(1 for r in rows if r.get("fallback_used"))
        sd = sorted(durs)
        p95_idx = min(int(n * 0.95), n - 1) if n else 0
        stats[p] = {
            "samples": float(n),
            "avg_ms": sum(durs) / n if n else 0.0,
            "p95_ms": float(sd[p95_idx]) if n else 0.0,
            "success_rate": succ / n if n else 0.0,
            "fallback_rate": fb / n if n else 0.0,
        }
    return stats


def compute_lifecycle_event_counts() -> dict[str, int]:
    """Count ``lifecycle_domain`` rows by ``lifecycle_event`` name."""
    events = read_events(limit=2000)
    counts: dict[str, int] = {}
    for e in events:
        if e.get("event_type") != "lifecycle_domain":
            continue
        meta = e.get("metadata") or {}
        name = str(meta.get("lifecycle_event", "unknown"))
        counts[name] = counts.get(name, 0) + 1
    return counts


def compute_connector_health_snapshot() -> dict[str, object]:
    """Aggregate connector-oriented telemetry for Insights / SLO-style views."""
    return {
        "llm_by_provider": compute_llm_connector_stats(),
        "circuit_breakers": compute_breaker_metrics(),
        "lifecycle": compute_lifecycle_event_counts(),
    }
