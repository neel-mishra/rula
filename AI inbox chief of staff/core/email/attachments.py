"""
Attachment text extraction — pulls searchable plain text out of PDF, DOCX,
HTML, and text attachments for brief summaries and triage context.

Import-guarded deps (pypdf, python-docx): if missing, that mime type
returns None rather than blocking ingestion. Extraction is best-effort and
bounded; output is truncated to `MAX_CHARS_PER_ATTACHMENT` characters so
one pathological attachment can't blow up LLM token budgets downstream.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)

MAX_CHARS_PER_ATTACHMENT = 50_000
MAX_BYTES = 20 * 1024 * 1024  # skip anything over 20 MiB

# MIME types we know how to extract
_PDF = "application/pdf"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PLAIN = "text/plain"
_HTML = "text/html"
_MARKDOWN = "text/markdown"

SUPPORTED_MIME_TYPES = frozenset({_PDF, _DOCX, _PLAIN, _HTML, _MARKDOWN})


@dataclass
class AttachmentExtract:
    filename: str
    mime_type: str
    size_bytes: int
    extracted_text: str | None
    extractor: str  # "pypdf" | "python-docx" | "plain" | "html" | "unsupported" | "error"
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "extracted_text": self.extracted_text,
            "extractor": self.extractor,
            "error": self.error,
        }


def _truncate(text: str) -> str:
    if len(text) > MAX_CHARS_PER_ATTACHMENT:
        return text[:MAX_CHARS_PER_ATTACHMENT] + "\n…[truncated]"
    return text


def _extract_pdf(content: bytes) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts).strip() or None


def _extract_docx(content: bytes) -> str | None:
    try:
        from docx import Document
    except ImportError:
        return None
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(parts).strip() or None


def _extract_html(content: bytes) -> str | None:
    # Best-effort: strip tags. No external dep; good enough for brief context.
    import re
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return None
    # Remove <script>, <style>, then tags
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _extract_plain(content: bytes) -> str | None:
    try:
        return content.decode("utf-8", errors="replace").strip() or None
    except Exception:
        return None


def extract_attachment(
    filename: str, mime_type: str, content: bytes
) -> AttachmentExtract:
    """
    Extract searchable text from a single attachment. Never raises.

    Returns AttachmentExtract with `extracted_text=None` and a populated
    `extractor`/`error` when extraction is skipped or fails.
    """
    size = len(content)
    mime_type_lower = (mime_type or "").lower()

    if size > MAX_BYTES:
        return AttachmentExtract(
            filename=filename,
            mime_type=mime_type_lower,
            size_bytes=size,
            extracted_text=None,
            extractor="unsupported",
            error=f"exceeds {MAX_BYTES} bytes",
        )

    if mime_type_lower not in SUPPORTED_MIME_TYPES:
        return AttachmentExtract(
            filename=filename,
            mime_type=mime_type_lower,
            size_bytes=size,
            extracted_text=None,
            extractor="unsupported",
        )

    try:
        if mime_type_lower == _PDF:
            text = _extract_pdf(content)
            extractor = "pypdf"
        elif mime_type_lower == _DOCX:
            text = _extract_docx(content)
            extractor = "python-docx"
        elif mime_type_lower == _HTML:
            text = _extract_html(content)
            extractor = "html"
        else:  # plain + markdown
            text = _extract_plain(content)
            extractor = "plain"
    except Exception as exc:
        log.warning(
            "attachment.extract_failed",
            filename=filename,
            mime_type=mime_type_lower,
            error=str(exc),
        )
        return AttachmentExtract(
            filename=filename,
            mime_type=mime_type_lower,
            size_bytes=size,
            extracted_text=None,
            extractor="error",
            error=str(exc),
        )

    if text is None:
        return AttachmentExtract(
            filename=filename,
            mime_type=mime_type_lower,
            size_bytes=size,
            extracted_text=None,
            extractor=extractor,
            error="no text recovered (or extractor dep missing)",
        )

    return AttachmentExtract(
        filename=filename,
        mime_type=mime_type_lower,
        size_bytes=size,
        extracted_text=_truncate(text),
        extractor=extractor,
    )


def extract_gmail_payload_attachments(
    payload: dict, fetch_body: callable
) -> list[AttachmentExtract]:
    """
    Walk a Gmail message payload. For each part with a filename and
    attachmentId, call `fetch_body(attachmentId) -> bytes`, then extract.

    `fetch_body` is an injected dependency so we never pull live bytes from
    Gmail inside this module (testable in isolation).
    """
    extracts: list[AttachmentExtract] = []

    def walk(part: dict) -> None:
        filename = part.get("filename")
        if filename:
            body = part.get("body") or {}
            attachment_id = body.get("attachmentId")
            mime_type = part.get("mimeType") or ""
            if attachment_id:
                try:
                    content = fetch_body(attachment_id)
                except Exception as exc:
                    extracts.append(
                        AttachmentExtract(
                            filename=filename,
                            mime_type=mime_type.lower(),
                            size_bytes=0,
                            extracted_text=None,
                            extractor="error",
                            error=f"fetch failed: {exc}",
                        )
                    )
                    return
                extracts.append(extract_attachment(filename, mime_type, content))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return extracts
