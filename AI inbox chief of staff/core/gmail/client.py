"""
Gmail API client — per-mailbox, using mailbox-scoped credentials.
All calls carry the mailbox's OAuth credentials. Never mixes credentials across mailboxes.
"""

from __future__ import annotations

import base64
import email as email_lib
from typing import Any

import structlog
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential

from core.gmail.auth import build_credentials_from_mailbox

log = structlog.get_logger(__name__)


class GmailClient:
    """
    Thread-safe Gmail API client for a single mailbox.
    Instantiate per-request or per-worker-job; do not share across mailboxes.
    """

    def __init__(self, mailbox: Any) -> None:
        self._mailbox = mailbox
        self._credentials = build_credentials_from_mailbox(mailbox)
        self._service = build("gmail", "v1", credentials=self._credentials, cache_discovery=False)

    @property
    def _user_id(self) -> str:
        """Gmail userId — always 'me' (authenticated user)."""
        return "me"

    # ── Message operations ──────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        """Fetch a single message by Gmail message ID."""
        return (
            self._service.users()
            .messages()
            .get(userId=self._user_id, id=message_id, format=format)
            .execute()
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Fetch a single attachment's raw bytes by message + attachment ID."""
        import base64
        resp = (
            self._service.users()
            .messages()
            .attachments()
            .get(userId=self._user_id, messageId=message_id, id=attachment_id)
            .execute()
        )
        data = resp.get("data", "")
        return base64.urlsafe_b64decode(data + "==") if data else b""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def list_messages(
        self,
        query: str = "",
        max_results: int = 50,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        kwargs: dict = {
            "userId": self._user_id,
            "maxResults": max_results,
        }
        if query:
            kwargs["q"] = query
        if page_token:
            kwargs["pageToken"] = page_token
        return self._service.users().messages().list(**kwargs).execute()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_history(self, start_history_id: str, max_results: int = 100) -> dict[str, Any]:
        """Incremental sync via Gmail history."""
        return (
            self._service.users()
            .history()
            .list(
                userId=self._user_id,
                startHistoryId=start_history_id,
                maxResults=max_results,
            )
            .execute()
        )

    # ── Label operations ─────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def create_label(self, name: str, visibility: str = "labelShow") -> dict[str, Any]:
        label_body = {
            "name": name,
            "messageListVisibility": visibility,
            "labelListVisibility": "labelShow",
        }
        return (
            self._service.users()
            .labels()
            .create(userId=self._user_id, body=label_body)
            .execute()
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def list_labels(self) -> list[dict[str, Any]]:
        result = self._service.users().labels().list(userId=self._user_id).execute()
        return result.get("labels", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def modify_message_labels(
        self,
        message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict = {}
        if add_label_ids:
            body["addLabelIds"] = add_label_ids
        if remove_label_ids:
            body["removeLabelIds"] = remove_label_ids
        return (
            self._service.users()
            .messages()
            .modify(userId=self._user_id, id=message_id, body=body)
            .execute()
        )

    def ensure_system_labels(self) -> dict[str, str]:
        """
        Create system labels if they don't exist. Returns mapping of
        label purpose -> Gmail label ID.
        """
        existing = self.list_labels()
        existing_by_name = {l["name"]: l["id"] for l in existing}

        system_labels = {
            "needs_attention": "Cora/Needs Attention",
            "next_brief": "Cora/Next Brief",
            "cora_system": "Cora/System",
        }

        result = {}
        for purpose, name in system_labels.items():
            if name in existing_by_name:
                result[purpose] = existing_by_name[name]
                log.info("label.exists", purpose=purpose, label_id=result[purpose])
            else:
                try:
                    created = self.create_label(name)
                    result[purpose] = created["id"]
                    log.info("label.created", purpose=purpose, label_id=result[purpose])
                except HttpError as e:
                    if e.resp.status == 409:  # Already exists (race condition)
                        refreshed = self.list_labels()
                        for l in refreshed:
                            if l["name"] == name:
                                result[purpose] = l["id"]
                                break
                    else:
                        raise
        return result

    # ── Draft operations ──────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def create_draft(
        self,
        thread_id: str | None,
        to: str,
        subject: str,
        body_text: str,
        in_reply_to: str | None = None,
    ) -> dict[str, Any]:
        """
        Write a draft to Gmail Drafts. NEVER sends. No gmail.send scope.
        """
        import email.mime.text
        import email.mime.multipart

        msg = email.mime.text.MIMEText(body_text, "plain")
        msg["To"] = to
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        message_body: dict[str, Any] = {"raw": raw}
        if thread_id:
            message_body["threadId"] = thread_id
        draft_body = {"message": message_body}
        return (
            self._service.users()
            .drafts()
            .create(userId=self._user_id, body=draft_body)
            .execute()
        )

    # ── Watch / push notifications ─────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def register_watch(self, topic_name: str) -> dict[str, Any]:
        """Register Gmail push watch. Returns expiration timestamp."""
        body = {
            "topicName": topic_name,
            "labelIds": ["INBOX"],
        }
        return (
            self._service.users()
            .watch(userId=self._user_id, body=body)
            .execute()
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def stop_watch(self) -> None:
        """Stop Gmail push watch for this mailbox."""
        self._service.users().stop(userId=self._user_id).execute()

    # ── Profile ──────────────────────────────────────────────────────────────

    def get_profile(self) -> dict[str, Any]:
        return self._service.users().getProfile(userId=self._user_id).execute()
