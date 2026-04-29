"""
Experiment assignment + rollup helpers.

Design:
- An active Experiment pins a prompt_name (e.g. 'triage_classifier') to 2+
  variants. Each variant has a registered prompt_version and a traffic_pct
  (shares sum to 100).
- `resolve_variant(prompt_name, mailbox_id, session)` deterministically picks a
  variant for this mailbox by hashing (experiment_id, mailbox_id) into [0, 100).
  Same mailbox + same experiment always yields the same bucket → stable
  assignment across agent runs.
- `rollup_experiment` computes per-variant sample counts + the primary metric
  and runs a two-proportion z-test against the control variant.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Integer, case, cast, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models.experiment import (
    Experiment,
    ExperimentMetric,
    ExperimentStatus,
    ExperimentVariant,
)


# ─────────────────────────────────────────────────────────────────────────────
# Assignment
# ─────────────────────────────────────────────────────────────────────────────


def _bucket(experiment_id: uuid.UUID, mailbox_id: uuid.UUID) -> int:
    """Deterministic bucket in [0, 100) using SHA-256 of the pair."""
    key = f"{experiment_id}:{mailbox_id}".encode()
    digest = hashlib.sha256(key).digest()
    return int.from_bytes(digest[:4], "big") % 100


def assign_variant(
    experiment: Experiment, mailbox_id: uuid.UUID
) -> ExperimentVariant | None:
    """Return the variant this mailbox falls into given the traffic split."""
    variants = sorted(experiment.variants, key=lambda v: v.created_at)
    if not variants:
        return None
    bucket = _bucket(experiment.id, mailbox_id)
    cumulative = 0
    for variant in variants:
        cumulative += variant.traffic_pct
        if bucket < cumulative:
            return variant
    return variants[-1]  # rounding safety


async def resolve_variant(
    prompt_name: str,
    mailbox_id: uuid.UUID,
    session: AsyncSession,
) -> ExperimentVariant | None:
    """
    For the given prompt_name + mailbox, return the active experiment's
    variant (or None if no active experiment matches).

    If multiple active experiments target the same prompt_name, the most
    recently started one wins.
    """
    result = await session.execute(
        select(Experiment)
        .where(
            Experiment.prompt_name == prompt_name,
            Experiment.status == ExperimentStatus.ACTIVE,
        )
        .options(selectinload(Experiment.variants))
        .order_by(Experiment.started_at.desc().nulls_last())
        .limit(1)
    )
    experiment = result.scalar_one_or_none()
    if not experiment:
        return None
    return assign_variant(experiment, mailbox_id)


# ─────────────────────────────────────────────────────────────────────────────
# Rollup + significance
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class VariantStats:
    variant_id: str
    label: str
    prompt_version: str
    is_control: bool
    traffic_pct: int
    sample_size: int
    metric_value: float | None          # primary metric (rate 0.0-1.0 or mean)
    correction_count: int | None        # triage-only
    acceptance_count: int | None        # draft-only
    avg_confidence: float | None
    z_score_vs_control: float | None
    p_value_vs_control: float | None
    is_significant: bool                # |z| > 1.96


@dataclass
class ExperimentRollup:
    experiment_id: str
    primary_metric: str
    window_start: str | None
    window_end: str
    variants: list[VariantStats]
    winner_variant_id: str | None
    notes: list[str]


def _two_proportion_z(
    p1: float, n1: int, p2: float, n2: int
) -> tuple[float, float] | None:
    """Two-proportion z-test. Returns (z, two-sided p-value) or None if N too low."""
    if n1 < 5 or n2 < 5:
        return None
    pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
    if pooled <= 0 or pooled >= 1:
        return None
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    z = (p1 - p2) / se
    # Two-sided p via normal CDF; 0.5 * erfc(|z|/sqrt(2))
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return z, p_value


async def rollup_experiment(
    experiment: Experiment, session: AsyncSession
) -> ExperimentRollup:
    """Compute per-variant metrics for the experiment's window."""
    from core.models.draft import Draft, DraftStatus
    from core.models.triage import TriageDecision

    window_start = experiment.started_at
    window_end = experiment.stopped_at or datetime.now(tz=timezone.utc)

    notes: list[str] = []
    variants_sorted = sorted(experiment.variants, key=lambda v: v.created_at)
    control = next((v for v in variants_sorted if v.is_control), None)

    # Control stats first (needed for delta tests)
    control_rate: float | None = None
    control_n: int = 0

    stats: list[VariantStats] = []

    for variant in variants_sorted:
        sample_size = 0
        metric_value: float | None = None
        correction_count: int | None = None
        acceptance_count: int | None = None
        avg_confidence: float | None = None

        if experiment.primary_metric in (
            ExperimentMetric.TRIAGE_CORRECTION_RATE,
            ExperimentMetric.AVG_CONFIDENCE,
        ):
            corrected_flag = case(
                (TriageDecision.corrected_by_user.is_(True), 1), else_=0
            )
            q = select(
                sa_func.count(TriageDecision.id),
                sa_func.coalesce(sa_func.sum(corrected_flag), 0),
                sa_func.avg(TriageDecision.confidence),
            ).where(
                TriageDecision.prompt_version == variant.prompt_version,
                TriageDecision.user_id == experiment.user_id,
            )
            if window_start:
                q = q.where(TriageDecision.created_at >= window_start)
            q = q.where(TriageDecision.created_at <= window_end)
            row = (await session.execute(q)).one()
            sample_size = row[0] or 0
            correction_count = int(row[1] or 0)
            avg_confidence = float(row[2]) if row[2] is not None else None

            if experiment.primary_metric == ExperimentMetric.TRIAGE_CORRECTION_RATE:
                metric_value = (
                    correction_count / sample_size if sample_size else None
                )
            else:  # AVG_CONFIDENCE
                metric_value = avg_confidence

        elif experiment.primary_metric == ExperimentMetric.DRAFT_ACCEPTANCE_RATE:
            accepted_flag = case(
                (Draft.status == DraftStatus.ACCEPTED, 1),
                (Draft.status == DraftStatus.EDITED_AND_SENT, 1),
                else_=0,
            )
            q = select(
                sa_func.count(Draft.id),
                sa_func.coalesce(sa_func.sum(accepted_flag), 0),
            ).where(
                Draft.prompt_version == variant.prompt_version,
                Draft.user_id == experiment.user_id,
            )
            if window_start:
                q = q.where(Draft.created_at >= window_start)
            q = q.where(Draft.created_at <= window_end)
            row = (await session.execute(q)).one()
            sample_size = row[0] or 0
            acceptance_count = int(row[1] or 0)
            metric_value = (
                acceptance_count / sample_size if sample_size else None
            )

        # Record control
        if variant.is_control:
            control_n = sample_size
            control_rate = metric_value

        stats.append(
            VariantStats(
                variant_id=str(variant.id),
                label=variant.label,
                prompt_version=variant.prompt_version,
                is_control=variant.is_control,
                traffic_pct=variant.traffic_pct,
                sample_size=sample_size,
                metric_value=metric_value,
                correction_count=correction_count,
                acceptance_count=acceptance_count,
                avg_confidence=avg_confidence,
                z_score_vs_control=None,
                p_value_vs_control=None,
                is_significant=False,
            )
        )

    # Pairwise tests against control (only meaningful for rate metrics)
    if (
        control is not None
        and control_rate is not None
        and experiment.primary_metric != ExperimentMetric.AVG_CONFIDENCE
    ):
        for s in stats:
            if s.is_control or s.metric_value is None or control_rate is None:
                continue
            res = _two_proportion_z(
                s.metric_value, s.sample_size, control_rate, control_n
            )
            if res is not None:
                s.z_score_vs_control, s.p_value_vs_control = res
                s.is_significant = abs(s.z_score_vs_control) > 1.96
    elif control is None:
        notes.append("No control variant set; pairwise tests skipped.")

    # Winner: best metric among significant non-control variants; "lower is better"
    # for TRIAGE_CORRECTION_RATE, "higher is better" otherwise.
    winner_id: str | None = None
    if control is not None:
        significant = [s for s in stats if s.is_significant and not s.is_control]
        if significant:
            if experiment.primary_metric == ExperimentMetric.TRIAGE_CORRECTION_RATE:
                best = min(significant, key=lambda s: s.metric_value or 1.0)
            else:
                best = max(significant, key=lambda s: s.metric_value or 0.0)
            winner_id = best.variant_id

    return ExperimentRollup(
        experiment_id=str(experiment.id),
        primary_metric=experiment.primary_metric.value,
        window_start=window_start.isoformat() if window_start else None,
        window_end=window_end.isoformat(),
        variants=stats,
        winner_variant_id=winner_id,
        notes=notes,
    )
