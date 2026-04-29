"""Unit tests for attachment text extraction."""

from __future__ import annotations

from core.email.attachments import (
    MAX_BYTES,
    MAX_CHARS_PER_ATTACHMENT,
    extract_attachment,
    extract_gmail_payload_attachments,
)


class TestExtractPlainText:
    def test_plain_text_utf8(self):
        result = extract_attachment("notes.txt", "text/plain", b"hello world")
        assert result.extracted_text == "hello world"
        assert result.extractor == "plain"
        assert result.error is None

    def test_plain_text_empty(self):
        result = extract_attachment("empty.txt", "text/plain", b"")
        assert result.extracted_text is None
        assert result.extractor == "plain"

    def test_plain_text_latin1_bytes_do_not_crash(self):
        # Decoding with errors="replace" should always succeed
        result = extract_attachment(
            "note.txt", "text/plain", b"caf\xe9 latte"
        )
        assert result.extracted_text is not None

    def test_markdown_uses_plain_extractor(self):
        result = extract_attachment("doc.md", "text/markdown", b"# heading")
        assert result.extractor == "plain"
        assert "heading" in result.extracted_text


class TestExtractHtml:
    def test_strips_tags(self):
        html = b"<p>hello <b>world</b></p>"
        result = extract_attachment("page.html", "text/html", html)
        assert result.extracted_text is not None
        assert "hello" in result.extracted_text
        assert "world" in result.extracted_text
        assert "<b>" not in result.extracted_text

    def test_strips_scripts_and_styles(self):
        html = (
            b"<html><head><style>body{}</style>"
            b"<script>alert(1)</script></head>"
            b"<body>visible text</body></html>"
        )
        result = extract_attachment("page.html", "text/html", html)
        assert result.extracted_text is not None
        assert "visible text" in result.extracted_text
        assert "alert" not in result.extracted_text


class TestUnsupported:
    def test_unknown_mime_type(self):
        result = extract_attachment(
            "photo.jpg", "image/jpeg", b"\xff\xd8\xff\xe0"
        )
        assert result.extracted_text is None
        assert result.extractor == "unsupported"

    def test_oversize_skipped(self):
        huge = b"x" * (MAX_BYTES + 1)
        result = extract_attachment("huge.txt", "text/plain", huge)
        assert result.extracted_text is None
        assert result.extractor == "unsupported"
        assert "exceeds" in (result.error or "")


class TestTruncation:
    def test_long_text_is_truncated(self):
        long_content = ("a" * (MAX_CHARS_PER_ATTACHMENT + 100)).encode()
        result = extract_attachment("long.txt", "text/plain", long_content)
        assert result.extracted_text is not None
        assert len(result.extracted_text) <= MAX_CHARS_PER_ATTACHMENT + 20
        assert result.extracted_text.endswith("[truncated]")


class TestGmailPayloadWalker:
    def test_collects_attachments_across_nested_parts(self):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": "body"},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "report.pdf",
                    "body": {"attachmentId": "att1", "size": 100},
                },
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "filename": "notes.txt",
                            "body": {"attachmentId": "att2", "size": 10},
                        },
                    ],
                },
            ],
        }

        fetched: dict[str, bytes] = {
            "att1": b"dummy pdf bytes",  # pypdf will fail parsing — error path
            "att2": b"these are the notes",
        }

        def fetch(attachment_id: str) -> bytes:
            return fetched[attachment_id]

        results = extract_gmail_payload_attachments(payload, fetch)
        assert len(results) == 2
        names = {r.filename for r in results}
        assert names == {"report.pdf", "notes.txt"}
        notes = next(r for r in results if r.filename == "notes.txt")
        assert notes.extracted_text == "these are the notes"

    def test_fetch_failure_is_captured(self):
        payload = {
            "filename": "x.txt",
            "mimeType": "text/plain",
            "body": {"attachmentId": "does-not-exist"},
        }

        def fetch(_: str) -> bytes:
            raise RuntimeError("network down")

        results = extract_gmail_payload_attachments(payload, fetch)
        assert len(results) == 1
        assert results[0].extractor == "error"
        assert "network down" in (results[0].error or "")

    def test_no_attachments_returns_empty(self):
        payload = {
            "mimeType": "text/plain",
            "body": {"data": "body"},
        }
        results = extract_gmail_payload_attachments(payload, lambda _: b"")
        assert results == []
