"""Format a non-secret company/account snippet for MAP committer disambiguation."""

from __future__ import annotations

from src.integrations.ingestion import load_test_accounts_raw

_MAX_NOTES = 400


def build_company_profile_text(
    account_id: int | None,
    *,
    accounts: list[dict] | None = None,
) -> str:
    """Return a short markdown-style block for LLM context, or empty if unknown."""
    if account_id is None:
        return ""
    rows = accounts if accounts is not None else load_test_accounts_raw()
    for row in rows:
        if int(row.get("account_id", -1)) != int(account_id):
            continue
        contact = row.get("contact") or {}
        cname = contact.get("name") if isinstance(contact, dict) else None
        ctitle = contact.get("title") if isinstance(contact, dict) else None
        lines = [
            f"Company: {row.get('company', '')}",
            f"Industry: {row.get('industry', '')}",
            f"Approx. US employees: {row.get('us_employees', '')}",
        ]
        if cname or ctitle:
            lines.append(f"Primary contact on file: {cname or '—'} ({ctitle or '—'})")
        hp = row.get("health_plan")
        if hp:
            lines.append(f"Health plan: {hp}")
        notes = str(row.get("notes") or "").strip()
        if notes:
            if len(notes) > _MAX_NOTES:
                notes = notes[: _MAX_NOTES] + "…"
            lines.append(f"Notes: {notes}")
        return "\n".join(lines)
    return ""
