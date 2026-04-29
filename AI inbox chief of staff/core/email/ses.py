"""
Amazon SES email delivery — used for sending brief digests.
Async wrapper around synchronous boto3 SES client.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

import structlog

from core.config import settings

log = structlog.get_logger(__name__)


class SESClient:
    """Async SES email sender."""

    def __init__(self) -> None:
        import boto3

        self._client = boto3.client("ses", region_name=settings.ses_region)

    async def send_html_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
        from_address: str | None = None,
    ) -> str:
        """Send an HTML email via SES. Returns the SES message ID."""
        sender = from_address or settings.ses_from_address

        def _send() -> dict:
            return self._client.send_email(
                Source=sender,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                    },
                },
            )

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, _send)
            message_id = result.get("MessageId", "")
            log.info("ses.email_sent", to=to, subject=subject, message_id=message_id)
            return message_id
        except Exception as exc:
            log.error("ses.send_failed", to=to, subject=subject, error=str(exc))
            raise

    async def send_brief(self, mailbox_email: str, brief: Any) -> str:
        """Convenience: send a composed Brief to the mailbox owner."""
        return await self.send_html_email(
            to=mailbox_email,
            subject=brief.subject_line or "Your Brief",
            html_body=brief.body_html or "",
            text_body=brief.body_text or "",
        )


_ses_client: SESClient | None = None


def get_ses_client() -> SESClient:
    global _ses_client
    if _ses_client is None:
        _ses_client = SESClient()
    return _ses_client
