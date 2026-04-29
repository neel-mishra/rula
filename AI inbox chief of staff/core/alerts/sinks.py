"""Concrete alert sinks: Slack incoming webhooks, PagerDuty Events API v2."""

from __future__ import annotations

import json
from urllib import request as urlrequest
from urllib.error import URLError

import structlog

from core.alerts import Severity

log = structlog.get_logger(__name__)

HTTP_TIMEOUT_SECONDS = 5


def _post_json(url: str, payload: dict) -> int:
    """Synchronous JSON POST. Returns HTTP status, raises on transport error."""
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return resp.status


_SEVERITY_EMOJI = {
    Severity.INFO: ":information_source:",
    Severity.WARNING: ":warning:",
    Severity.CRITICAL: ":rotating_light:",
}


class SlackSink:
    name = "slack"

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    def send(
        self,
        severity: Severity,
        title: str,
        details: dict | None = None,
    ) -> bool:
        emoji = _SEVERITY_EMOJI.get(severity, "")
        detail_lines = []
        if details:
            for k, v in list(details.items())[:10]:
                detail_lines.append(f"*{k}*: `{v}`")
        text = f"{emoji} *[{severity.value.upper()}]* {title}"
        payload = {
            "text": text,
            "attachments": [
                {"text": "\n".join(detail_lines)} if detail_lines else {"text": ""},
            ],
        }
        try:
            status = _post_json(self._url, payload)
        except (URLError, TimeoutError, OSError) as exc:
            log.warning("alerts.slack_transport_failed", error=str(exc))
            return False
        if 200 <= status < 300:
            return True
        log.warning("alerts.slack_http_error", status=status)
        return False


_PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"


class PagerDutySink:
    name = "pagerduty"

    def __init__(
        self,
        routing_key: str,
        url: str = _PAGERDUTY_EVENTS_URL,
    ) -> None:
        self._routing_key = routing_key
        self._url = url

    def send(
        self,
        severity: Severity,
        title: str,
        details: dict | None = None,
    ) -> bool:
        # Only pages on CRITICAL; warnings/info are dropped to avoid noise.
        if severity != Severity.CRITICAL:
            return True
        payload = {
            "routing_key": self._routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": title,
                "source": "inbox-chief-of-staff",
                "severity": "critical",
                "custom_details": details or {},
            },
        }
        try:
            status = _post_json(self._url, payload)
        except (URLError, TimeoutError, OSError) as exc:
            log.warning("alerts.pagerduty_transport_failed", error=str(exc))
            return False
        if 200 <= status < 300:
            return True
        log.warning("alerts.pagerduty_http_error", status=status)
        return False
