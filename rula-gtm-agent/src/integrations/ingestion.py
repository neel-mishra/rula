from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.schemas.account import Account


def validate_commitment_ingest_dict(raw: dict[str, Any]) -> None:
    """Pre-flight schema check for external commitment evidence payloads."""
    from src.integrations.contract_compat import require_ingest_schema

    require_ingest_schema(str(raw.get("schema_version", "1.0")), component="ingestion")


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_test_accounts() -> list[Account]:
    """Load all accounts from the test data file."""
    path = DATA_DIR / "accounts.json"
    if not path.exists():
        raise FileNotFoundError(f"Test data file not found: {path}")
    raw: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [Account.model_validate(a) for a in raw]


def load_test_accounts_raw() -> list[dict[str, Any]]:
    """Load raw account dicts from the test data file."""
    path = DATA_DIR / "accounts.json"
    if not path.exists():
        raise FileNotFoundError(f"Test data file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_clay_accounts_demo() -> list[Account]:
    """Placeholder for Clay import — returns empty list with metadata for demo UI."""
    return []


@dataclass(frozen=True)
class ClayWebhookConfig:
    webhook_url: str
    workspace_id: str
    list_id: str

    @classmethod
    def from_env(cls) -> ClayWebhookConfig | None:
        url = os.environ.get("CLAY_WEBHOOK_URL", "")
        wid = os.environ.get("CLAY_WORKSPACE_ID", "")
        lid = os.environ.get("CLAY_LIST_ID", "")
        if not url:
            return None
        return cls(webhook_url=url, workspace_id=wid, list_id=lid)


def build_clay_webhook_payload(config: ClayWebhookConfig) -> dict[str, Any]:
    """Build the payload that would be sent to Clay to trigger an import.

    In production, this would POST to config.webhook_url.
    In demo, we only return the shape so the UI can display it.
    """
    return {
        "action": "import_account_list",
        "workspace_id": config.workspace_id,
        "list_id": config.list_id,
        "callback_url": "https://placeholder.rula.internal/api/clay-callback",
        "fields_requested": [
            "company",
            "industry",
            "us_employees",
            "contact_name",
            "contact_title",
            "health_plan",
            "notes",
            "enrichment_signals",
        ],
    }
