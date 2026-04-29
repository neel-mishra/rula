"""Alert router — dispatches a single alert to every configured sink."""

from __future__ import annotations

from typing import Protocol

import structlog

from core.alerts import Severity

log = structlog.get_logger(__name__)


class AlertSink(Protocol):
    """Pluggable alert destination (Slack, PagerDuty, stdout)."""

    name: str

    def send(
        self,
        severity: Severity,
        title: str,
        details: dict | None = None,
    ) -> bool:
        """Return True on success. Never raises."""
        ...


class AlertRouter:
    def __init__(self, sinks: list[AlertSink] | None = None) -> None:
        self._sinks: list[AlertSink] = sinks or []

    def register(self, sink: AlertSink) -> None:
        self._sinks.append(sink)

    def clear(self) -> None:
        self._sinks.clear()

    @property
    def sinks(self) -> list[AlertSink]:
        return list(self._sinks)

    def emit(
        self,
        severity: Severity,
        title: str,
        details: dict | None = None,
    ) -> dict[str, bool]:
        """Fan out to every sink; collect per-sink results."""
        if not self._sinks:
            log.debug("alerts.no_sinks_configured", title=title)
            return {}
        results: dict[str, bool] = {}
        for sink in self._sinks:
            try:
                results[sink.name] = sink.send(severity, title, details)
            except Exception as exc:  # sinks must not raise, but defend anyway
                log.warning(
                    "alerts.sink_raised",
                    sink=sink.name,
                    error=str(exc),
                    title=title,
                )
                results[sink.name] = False
        return results


_router: AlertRouter | None = None


def get_alert_router() -> AlertRouter:
    global _router
    if _router is None:
        _router = _build_default_router()
    return _router


def _build_default_router() -> AlertRouter:
    """Construct the default router from settings."""
    from core.alerts.sinks import PagerDutySink, SlackSink
    from core.config import settings

    router = AlertRouter()
    slack_url = getattr(settings, "slack_webhook_url", "")
    if slack_url:
        router.register(SlackSink(webhook_url=slack_url))
    pd_key = getattr(settings, "pagerduty_routing_key", "")
    if pd_key:
        router.register(PagerDutySink(routing_key=pd_key))
    return router


def emit_alert(
    severity: Severity,
    title: str,
    details: dict | None = None,
) -> dict[str, bool]:
    """Shortcut: fan out via the default router."""
    return get_alert_router().emit(severity, title, details)
