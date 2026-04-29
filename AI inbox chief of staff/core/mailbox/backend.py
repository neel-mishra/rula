from __future__ import annotations

from typing import Any, Protocol

from core.config import settings


class MailboxBackend(Protocol):
    def get_history(self, start_history_id: str, max_results: int = 100) -> dict[str, Any]:
        ...

    def create_draft(
        self,
        thread_id: str | None,
        to: str,
        subject: str,
        body_text: str,
        in_reply_to: str | None = None,
    ) -> dict[str, Any]:
        ...


def get_mailbox_backend(mailbox: Any) -> MailboxBackend:
    if settings.mailbox_backend == "local":
        from core.mailbox.local import LocalMailboxBackend

        return LocalMailboxBackend(mailbox)

    from core.mailbox.gmail import GmailMailboxBackend

    return GmailMailboxBackend(mailbox)
