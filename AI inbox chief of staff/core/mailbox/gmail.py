from __future__ import annotations

from typing import Any

from core.gmail import GmailClient


class GmailMailboxBackend:
    def __init__(self, mailbox: Any) -> None:
        self._client = GmailClient(mailbox)

    def get_history(self, start_history_id: str, max_results: int = 100) -> dict[str, Any]:
        return self._client.get_history(start_history_id=start_history_id, max_results=max_results)

    def create_draft(
        self,
        thread_id: str | None,
        to: str,
        subject: str,
        body_text: str,
        in_reply_to: str | None = None,
    ) -> dict[str, Any]:
        return self._client.create_draft(
            thread_id=thread_id,
            to=to,
            subject=subject,
            body_text=body_text,
            in_reply_to=in_reply_to,
        )
