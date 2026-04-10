# Ingest contract (future HTTP) — commitment evidence

This document describes a **proposed** HTTP interface for orchestrators (e.g. n8n) to submit commitment evidence into the Rula GTM pipeline. It aligns with `CommitmentEvidenceArtifact` and export `LineageExportBlock` in code (GAP-X1 / GAP-X2).

## Request

- **Method:** `POST`
- **Path:** `/ingest/evidence` (illustrative; not implemented in the enclosed prototype)
- **Headers:**
  - `Content-Type: application/json`
  - `Idempotency-Key: <opaque string>` — resend-safe dedupe key (e.g. hash of source message ID).

### JSON body (example)

```json
{
  "evidence_id": "EV-2026-0001",
  "source_type": "slack",
  "raw_text": "We will launch the benefits insert in Q2.",
  "raw_ref": "slack://C0123/1712345678.000100",
  "captured_at": "2026-04-10T12:00:00Z",
  "prospecting_run_id": null,
  "schema_version": "1.0"
}
```

| Field | Required | Notes |
|-------|----------|--------|
| `evidence_id` | yes | Stable ID for correlation and MAP scoring. |
| `source_type` | yes | e.g. `email`, `slack`, `call_notes`. |
| `raw_text` | yes | Commitment language and context. |
| `raw_ref` | no | Opaque URI / pointer to upstream object. |
| `captured_at` | no | ISO-8601 UTC; server may default to receive time. |
| `prospecting_run_id` | no | Links to prospecting lineage when applicable. |
| `schema_version` | no | Defaults to `1.0`. |

## Response (success)

```json
{
  "evidence_id": "EV-2026-0001",
  "state": "accepted"
}
```

`state` values (textual; align with design §6): `accepted`, `queued`, `processing`, `complete`, `failed` (production only).

## Error body

```json
{
  "error": "validation_failed",
  "detail": "evidence_id required"
}
```

## Retry policy (recommended)

- **5xx / network:** exponential backoff, cap retries, respect `Retry-After` when present.
- **4xx validation:** do not retry without fixing the payload.
- **Idempotency:** same `Idempotency-Key` should return the same logical outcome within the server’s dedupe window.

## Prototype note

The Streamlit app does **not** expose this endpoint. Use **Samples and structured capture** or the **Evidence database (n8n)** ghost in the UI to understand boundaries.
