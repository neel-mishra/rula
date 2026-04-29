from __future__ import annotations

from typing import Any


class LocalMailboxBackend:
    """
    Local test backend for mailbox operations.
    """

    def __init__(self, mailbox: Any) -> None:
        self._mailbox = mailbox

    def get_history(self, start_history_id: str, max_results: int = 100) -> dict[str, Any]:
        # Local mode has no remote mailbox history feed.
        return {"history": []}

    def create_draft(
        self,
        thread_id: str | None,
        to: str,
        subject: str,
        body_text: str,
        in_reply_to: str | None = None,
    ) -> dict[str, Any]:
        # Return a deterministic local draft id shape compatible with Gmail.
        return {"id": f"local-draft-{thread_id or 'threadless'}"}
