"""
Launch SLO measurement + target evaluation.

These are the numeric targets that gate production launch (see
`docs/PRODUCT_ROADMAP.md` "Numeric Launch Targets"). Each metric is
measured on demand from existing DB rows; no new tables are added.

A metric computation returns a `MetricReading` carrying the current value,
the defined target, and a `status` that turns the target into a pass/warn/
fail signal the dashboard and alerting can act on.
"""

from core.slo.targets import (
    MetricReading,
    MetricStatus,
    MetricTarget,
    Operator,
    TARGETS,
)

__all__ = [
    "MetricReading",
    "MetricStatus",
    "MetricTarget",
    "Operator",
    "TARGETS",
]
