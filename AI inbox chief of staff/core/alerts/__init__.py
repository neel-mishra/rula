"""
Incident alert routing — pluggable sinks (Slack webhook, PagerDuty Events API).

Usage from any production code path:

    from core.alerts import emit_alert, Severity

    emit_alert(
        Severity.CRITICAL,
        "LLM circuit breaker tripped",
        {"provider": "anthropic", "failures_in_window": 5},
    )

Sinks are configured by environment and activated only when credentials exist.
`emit_alert` never raises — a failing sink logs a warning and the call returns.
This ensures alerting can't itself become a hot failure path.
"""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


from core.alerts.router import AlertSink, emit_alert, get_alert_router  # noqa: E402,F401
from core.alerts.sinks import PagerDutySink, SlackSink  # noqa: E402,F401

__all__ = [
    "AlertSink",
    "PagerDutySink",
    "Severity",
    "SlackSink",
    "emit_alert",
    "get_alert_router",
]
