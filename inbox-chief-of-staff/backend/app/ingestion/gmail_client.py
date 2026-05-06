from __future__ import annotations
import base64
import re
from email import message_from_bytes
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.core.config import settings


class GmailClient:
    """Wraps Gmail API v1. Only performs actions allowed in Phase 1: read, label, draft."""

    def __init__(self, refresh_token: str) -> None:
        self._credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=settings.gmail_scopes.split(","),
        )
        # Refresh token proactively
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        self._service = build("gmail", "v1", credentials=self._credentials, cache_discovery=False)

    def get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        return (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format=format)
            .execute()
        )

    def list_messages(
        self,
        max_results: int = 50,
        label_ids: list[str] | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"userId": "me", "maxResults": max_results}
        if label_ids:
            kwargs["labelIds"] = label_ids
        if page_token:
            kwargs["pageToken"] = page_token
        return self._service.users().messages().list(**kwargs).execute()

    def create_draft(self, to: str, subject: str, body: str) -> str:
        """Creates a Gmail draft. Returns the gmail_draft_id. NEVER sends."""
        import base64
        from email.mime.text import MIMEText
        mime = MIMEText(body)
        mime["to"] = to
        mime["subject"] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        result = (
            self._service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )
        return result["id"]

    def add_label(self, message_id: str, label_ids: list[str]) -> None:
        self._service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": label_ids},
        ).execute()

    def setup_watch(self, topic_name: str) -> dict[str, Any]:
        """Register Gmail push notifications via Cloud Pub/Sub."""
        return (
            self._service.users()
            .watch(
                userId="me",
                body={
                    "topicName": topic_name,
                    "labelIds": settings.gmail_watch_labels.split(","),
                },
            )
            .execute()
        )

    @staticmethod
    def _get_header(headers: list[dict], name: str) -> str:
        for h in headers:
            if h["name"].lower() == name.lower():
                return h["value"]
        return ""

    @staticmethod
    def decode_body(payload: dict[str, Any]) -> str:
        """Recursively extract and decode plain-text body from a Gmail message payload."""
        mime_type = payload.get("mimeType", "")

        if mime_type == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            return ""

        if mime_type.startswith("multipart/"):
            for part in payload.get("parts", []):
                text = GmailClient.decode_body(part)
                if text:
                    return text

        return ""
