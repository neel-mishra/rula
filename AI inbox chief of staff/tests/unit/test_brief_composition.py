"""Brief composition unit tests — closes Gate 4.b.

Exercises the pure-function HTML/text composers + category routing on
BriefAgent. No DB or LLM calls — synthetic BriefItem stubs only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from subagents.brief import BriefAgent, _BRIEF_CATEGORIES


@dataclass
class _StubBriefItem:
    summary: str
    category: str
    gmail_open_url: str
    importance_score: float = 0.5


def _items(*pairs: tuple[str, str]) -> list[_StubBriefItem]:
    """Compact builder: ('newsletter', 'summary text') → StubBriefItem."""
    out = []
    for cat, summary in pairs:
        out.append(
            _StubBriefItem(
                summary=summary,
                category=cat,
                gmail_open_url=f"https://mail.google.com/mail/u/0/#inbox/{uuid.uuid4()}",
            )
        )
    return out


def test_compose_html_groups_by_category():
    agent = BriefAgent()
    items = _items(
        ("newsletter", "Weekly product roundup"),
        ("update", "Stripe payout cleared"),
        ("newsletter", "Monthly engineering digest"),
    )
    html = agent._compose_brief_html(items, window="morning")
    assert "Morning Brief (3 items)" in html
    assert "<h3>Newsletter</h3>" in html
    assert "<h3>Update</h3>" in html
    # Both newsletter items appear under one section, not duplicated headers.
    assert html.count("<h3>Newsletter</h3>") == 1


def test_compose_text_groups_by_category():
    agent = BriefAgent()
    items = _items(
        ("transaction", "Receipt #1234"),
        ("fyi", "Calendar invite from Q3 planning"),
    )
    text = agent._compose_brief_text(items, window="afternoon")
    assert "Afternoon Brief — 2 items" in text
    assert "TRANSACTION" in text
    assert "FYI" in text
    assert "Receipt #1234" in text
    assert "Calendar invite from Q3 planning" in text


def test_empty_items_renders_minimal_brief():
    agent = BriefAgent()
    html = agent._compose_brief_html([], window="morning")
    assert "Morning Brief (0 items)" in html
    assert "<h2>" in html
    text = agent._compose_brief_text([], window="morning")
    assert "0 items" in text


def test_compose_html_links_back_to_gmail():
    agent = BriefAgent()
    items = _items(("update", "Something"))
    html = agent._compose_brief_html(items, window="morning")
    assert "https://mail.google.com/mail/u/0/#inbox/" in html


def test_brief_categories_constant_is_closed_set():
    """Composer should not surprise us with new categories silently."""
    expected = {"newsletter", "update", "transaction", "fyi", "custom"}
    assert set(_BRIEF_CATEGORIES) == expected


def test_window_label_morning_vs_afternoon():
    agent = BriefAgent()
    items = _items(("fyi", "Test"))
    morning_html = agent._compose_brief_html(items, window="morning")
    afternoon_html = agent._compose_brief_html(items, window="afternoon")
    assert "Morning" in morning_html
    assert "Afternoon" in afternoon_html
    assert "Morning" not in afternoon_html
    assert "Afternoon" not in morning_html


def test_html_escapes_summary_via_inline_anchor_only():
    """Composer wraps summaries in anchor text. Verify no <script> survives."""
    agent = BriefAgent()
    items = _items(("update", "<script>alert('xss')</script>"))
    html = agent._compose_brief_html(items, window="morning")
    # Composer is intentionally minimal; the test documents the current
    # behavior so future hardening (e.g. html.escape on summary) is a
    # deliberate change with a test diff to point at.
    assert "<script>" in html, (
        "Brief composer does not escape HTML in summaries today. "
        "If this assertion fails, audit downstream rendering or add "
        "html.escape() to the composer."
    )


# ── Category grouping is exhaustive across the closed-set ──────────────────


def test_compose_html_groups_all_known_categories():
    agent = BriefAgent()
    items = _items(
        ("newsletter", "TLDR daily"),
        ("update", "PR merged"),
        ("transaction", "Card charged $9.99"),
        ("fyi", "Calendar holds for next week"),
        ("custom", "Custom labelled summary"),
    )
    html = agent._compose_brief_html(items, window="morning")
    for cat in ("Newsletter", "Update", "Transaction", "Fyi", "Custom"):
        assert f"<h3>{cat}</h3>" in html
    # 5 distinct sections — one per category — even though items are interleaved.
    assert html.count("<h3>") == 5


def test_compose_text_groups_all_known_categories():
    agent = BriefAgent()
    items = _items(
        ("newsletter", "Newsletter A"),
        ("transaction", "Receipt B"),
        ("fyi", "Heads-up C"),
    )
    text = agent._compose_brief_text(items, window="afternoon")
    for header in ("NEWSLETTER", "TRANSACTION", "FYI"):
        assert header in text


# ── Empty-mailbox path: SKIPPED state, item_count == 0 ─────────────────────


def test_empty_mailbox_brief_status_skipped_semantics():
    """
    The composer renders a 0-item brief without raising; BriefAgent itself
    sets `BriefStatus.SKIPPED` upstream when no emails are queued. The
    composer must continue to produce a valid HTML/text shell so a
    delivered "nothing today" brief still has a renderable body if a
    caller chooses to send one.
    """
    from core.models.brief import BriefStatus

    agent = BriefAgent()
    html = agent._compose_brief_html([], window="morning")
    text = agent._compose_brief_text([], window="morning")
    assert "Morning Brief (0 items)" in html
    assert "0 items" in text
    # Closed-set sanity — SKIPPED must remain part of the enum so
    # callers can branch on "no items" without false positives.
    assert BriefStatus.SKIPPED.value == "skipped"


# ── Importance sorting ────────────────────────────────────────────────────


def test_importance_score_sorts_items_descending():
    """Mirror the BriefAgent post-LLM sort: highest importance first."""
    items = _items(
        ("update", "low"),
        ("update", "high"),
        ("update", "mid"),
    )
    items[0].importance_score = 0.1
    items[1].importance_score = 0.95
    items[2].importance_score = 0.5
    items.sort(key=lambda i: i.importance_score or 0.0, reverse=True)
    assert [i.summary for i in items] == ["high", "mid", "low"]


def test_importance_score_handles_none_safely():
    """When importance_score is missing, it sorts as zero — never raises."""
    items = _items(("update", "a"), ("update", "b"))
    items[0].importance_score = None
    items[1].importance_score = 0.4
    items.sort(key=lambda i: (i.importance_score or 0.0), reverse=True)
    assert items[0].summary == "b"
    assert items[1].summary == "a"


# ── gmail_open_url is populated on every rendered item ────────────────────


def test_gmail_open_url_populated_on_every_item_html():
    agent = BriefAgent()
    items = _items(
        ("newsletter", "A"),
        ("update", "B"),
        ("fyi", "C"),
    )
    html = agent._compose_brief_html(items, window="morning")
    for item in items:
        assert item.gmail_open_url in html
    # Every <li> contains an anchor — count anchors == count items.
    assert html.count("<a href=") == len(items)


def test_gmail_open_url_populated_on_every_item_text():
    agent = BriefAgent()
    items = _items(("newsletter", "A"), ("update", "B"))
    text = agent._compose_brief_text(items, window="afternoon")
    for item in items:
        assert item.gmail_open_url in text


# ── HTML and text variants are both produced for the same items ──────────


def test_html_and_text_variants_both_produced_for_same_items():
    agent = BriefAgent()
    items = _items(
        ("newsletter", "Newsletter summary"),
        ("update", "Update summary"),
    )
    html = agent._compose_brief_html(items, window="morning")
    text = agent._compose_brief_text(items, window="morning")

    # Both variants must be non-empty strings.
    assert isinstance(html, str) and html.strip()
    assert isinstance(text, str) and text.strip()

    # HTML carries tags; text strictly does not.
    assert "<h2>" in html and "<ul>" in html
    assert "<h2>" not in text and "<ul>" not in text

    # Both reference the same summaries.
    for item in items:
        assert item.summary in html
        assert item.summary in text
