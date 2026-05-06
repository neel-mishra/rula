#!/usr/bin/env python3
"""Bulk-ingest recent Gmail messages for a given user via the dev/ingest API.

Usage:
    python3 scripts/bulk_ingest.py --email neel.mish98@gmail.com --count 50

Requirements:
    - The FastAPI server must be running on localhost:8000.
    - The user must have completed the OAuth flow (so their refresh token is in the DB).
    - .env must be loaded (DATABASE_URL, GOOGLE_CLIENT_ID, etc.) — the script only
      talks to the running server via HTTP, so the server handles all credentials.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Load .env so DATABASE_URL / other vars are in the environment if the caller
# hasn't already exported them.  We rely only on stdlib + requests here.
# ---------------------------------------------------------------------------

def _load_dotenv(env_file: Path) -> None:
    """Minimal .env loader — sets vars that aren't already in the environment."""
    import os
    if not env_file.exists():
        return
    with env_file.open() as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _find_dotenv() -> Path:
    """Walk up from this script's location to find a .env file."""
    start = Path(__file__).resolve().parent
    for candidate in [start, start.parent, start.parent.parent]:
        p = candidate / ".env"
        if p.exists():
            return p
    return start / ".env"  # fallback (may not exist — that's OK)


# ---------------------------------------------------------------------------
# Gmail listing — we call the running server for ingest, but we need to list
# message IDs from Gmail directly here (or accept them on stdin).  However,
# to keep things zero-dependency we use the server's /dev/ingest endpoint,
# which means we need message IDs first.
#
# We fetch message IDs by calling the Gmail REST API directly via requests,
# using an access token obtained by exchanging the refresh token stored in
# the DB.  But that requires DB access — which we explicitly want to avoid.
#
# Simpler approach that keeps the script truly self-contained:
#   1. Accept --token (OAuth access token) directly.  User can get it from
#      the running server's /auth/me or by running `python3 -c "..."` helper.
#   OR
#   2. Read refresh_token from the DB (requires psycopg2 + sqlalchemy — heavy).
#
# We go with option 1 for zero new deps: --token is an optional flag.
# If not provided, the script prints instructions for how to obtain one.
# ---------------------------------------------------------------------------

GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def _get_access_token(refresh_token: str, client_id: str, client_secret: str) -> str:
    """Exchange a refresh token for a short-lived access token."""
    resp = requests.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _list_inbox_message_ids(access_token: str, count: int) -> list[str]:
    """Return up to `count` message IDs from the user's INBOX (newest first)."""
    ids: list[str] = []
    page_token: str | None = None
    while len(ids) < count:
        batch = min(count - len(ids), 500)  # Gmail max per page is 500
        params: dict = {
            "maxResults": batch,
            "labelIds": "INBOX",
        }
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(
            GMAIL_MESSAGES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        for msg in data.get("messages", []):
            ids.append(msg["id"])
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return ids[:count]


def _ingest_message(base_url: str, email: str, gmail_message_id: str) -> dict:
    """POST to /dev/ingest and return the parsed JSON response."""
    resp = requests.post(
        f"{base_url}/dev/ingest",
        json={"user_email": email, "gmail_message_id": gmail_message_id},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_refresh_token_from_db(email: str) -> str | None:
    """
    Attempt to read the encrypted refresh token from the database, then decrypt
    it so we can exchange it for an access token.

    Requires the server's Python environment (sqlalchemy, app.core.security).
    Silently returns None if the import fails — the caller will fall back to
    asking the user to supply --refresh-token manually.
    """
    import os
    try:
        # Ensure we can import the app; the script may be run from the repo root
        # or from inside backend/.
        import importlib.util
        backend_path = Path(__file__).resolve().parent.parent
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))

        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select
        from app.models.user import User
        from app.core.security import decrypt_token

        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            return None

        engine = create_async_engine(database_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _query() -> str | None:
            async with async_session() as session:
                result = await session.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()
                if user and user.google_refresh_token:
                    return decrypt_token(user.google_refresh_token)
                return None

        return asyncio.run(_query())
    except Exception as exc:
        print(f"[warn] Could not auto-fetch refresh token from DB: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-ingest the N most recent INBOX messages for a Gmail user."
    )
    parser.add_argument("--email", required=True, help="Gmail address of the pilot user")
    parser.add_argument(
        "--count", type=int, default=50, help="Number of messages to ingest (default: 50)"
    )
    parser.add_argument(
        "--refresh-token",
        default=None,
        help=(
            "OAuth refresh token for the user.  If omitted the script tries to "
            "read it from the database (requires DATABASE_URL in .env)."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the running API server (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Seconds to sleep between ingest requests (default: 0.5)",
    )
    args = parser.parse_args()

    # 1. Load .env
    _load_dotenv(_find_dotenv())

    import os

    # 2. Resolve refresh token
    refresh_token = args.refresh_token
    if not refresh_token:
        print("[info] No --refresh-token supplied — attempting to read from DB …")
        refresh_token = _fetch_refresh_token_from_db(args.email)
        if not refresh_token:
            print(
                "[error] Could not obtain a refresh token.  "
                "Either pass --refresh-token <token> or ensure DATABASE_URL is set in .env "
                "and the user has completed OAuth.",
                file=sys.stderr,
            )
            sys.exit(1)

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print(
            "[error] GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. Obtain access token
    print("[info] Fetching Gmail access token …")
    try:
        access_token = _get_access_token(refresh_token, client_id, client_secret)
    except requests.HTTPError as exc:
        print(f"[error] Token exchange failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # 4. List message IDs from INBOX
    print(f"[info] Listing up to {args.count} INBOX messages for {args.email} …")
    try:
        message_ids = _list_inbox_message_ids(access_token, args.count)
    except requests.HTTPError as exc:
        print(f"[error] Failed to list Gmail messages: {exc}", file=sys.stderr)
        sys.exit(1)

    total = len(message_ids)
    if total == 0:
        print("[info] No messages found in INBOX. Nothing to ingest.")
        return

    print(f"[info] Found {total} messages. Starting ingest …\n")

    # 5. Ingest each message via the dev/ingest endpoint
    skipped = 0
    failed = 0
    for idx, msg_id in enumerate(message_ids, start=1):
        try:
            result = _ingest_message(args.base_url, args.email, msg_id)
            status = result.get("status", "ok")
            # Print progress — the endpoint doesn't return priority yet,
            # but we include it if the response ever adds it.
            priority = result.get("priority", "")
            priority_str = f" | priority={priority}" if priority else ""
            print(f"[{idx}/{total}] ingested {msg_id}{priority_str}")
            if status == "duplicate":
                skipped += 1
        except requests.HTTPError as exc:
            # 409 / 422 can mean already ingested depending on the server version
            if exc.response is not None and exc.response.status_code in (409, 422):
                print(f"[{idx}/{total}] skipped {msg_id} (already ingested)")
                skipped += 1
            else:
                print(f"[{idx}/{total}] FAILED  {msg_id} — {exc}", file=sys.stderr)
                failed += 1
        except requests.RequestException as exc:
            print(f"[{idx}/{total}] FAILED  {msg_id} — {exc}", file=sys.stderr)
            failed += 1

        if idx < total:
            time.sleep(args.sleep)

    print(
        f"\n[done] {total - skipped - failed} ingested, "
        f"{skipped} skipped (duplicates), "
        f"{failed} failed."
    )


if __name__ == "__main__":
    main()
