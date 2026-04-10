# Connector policy registry

Reliability defaults for logical outbound connectors live in
[`src/integrations/connector_policy.py`](../src/integrations/connector_policy.py).

## Built-in connectors

| ID | Purpose | Default timeout (s) | Max retries | Idempotency scope |
|----|---------|----------------------|-------------|-------------------|
| `llm_provider` | Model router / LLM calls | 120 | 0 | none |
| `context_company` | LinkedIn/news-style company context | 10 | 1 | none |
| `handoff_prospecting` | Prospecting handoff (sequencer/CRM/review stubs) | 60 | 2 | run_id |
| `handoff_map` | MAP handoff (CRM/review/archive) | 60 | 2 | run_id |
| `ingestion` | Ingestion adapters | 30 | 2 | none |

## Overrides

Per-connector (ID is uppercased):

- `RULA_CONNECTOR_<ID>_TIMEOUT_S`
- `RULA_CONNECTOR_<ID>_MAX_RETRIES`
- `RULA_CONNECTOR_<ID>_BACKOFF_S`

Example: `RULA_CONNECTOR_CONTEXT_COMPANY_TIMEOUT_S=15`.

## Where policies are applied

- **Context:** `fetch_company_context()` uses `context_company` timeout (see `context_fetch.py`).
- **LLM router:** policy fields are attached to `generation_complete` telemetry (`ux_events.py` / `router.py`).  
  **HTTP timeouts:** `LLM_PROVIDER.timeout_seconds` is applied at the SDK layer where supported:
  - **Anthropic (`claude_provider`):** `Anthropic(..., timeout=<seconds>)` matches the policy.
  - **Google GenAI (`gemini_provider`):** `genai.Client(..., http_options=HttpOptions(timeout=<ms>))` with `timeout_ms = max(1, int(policy.timeout_seconds * 1000))`.
- **Handoffs:** `handoff_orchestrated` / `map_handoff_orchestrated` events include policy metadata.

Unknown connector IDs receive conservative defaults (30s timeout, 1 retry).
