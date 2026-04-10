# Rula Revenue Intelligence - GTM Agent System

Multi-agent system for Account Executive prospecting and MAP (Mutual Action Plan) verification. Combines deterministic pipelines with optional LLM generation (Claude + Gemini), full explainability, telemetry, safety controls, and CRM-ready export.

## Architecture

```
Account -> Enrichment -> Value-Prop Matching -> Outreach Generation -> Quality Eval -> Audit Judge -> Output
Evidence -> Parser -> Commitment Scorer -> Action Flagger -> Audit Judge -> Output
                                                              |
                                          ModelRouter (Claude <-> Gemini fallback)
```

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env   # Add API keys for generative features (optional)
```

Run tests:

```bash
python -m pytest tests/ -v
```

Optional lint (requires `pip install -e .[dev]`):

```bash
ruff check src
```

Run the interactive app:

```bash
streamlit run app.py
```

## Configuration

Copy `.env.example` to `.env` and set your API keys:

| Variable | Purpose | Required |
|----------|---------|----------|
| `ANTHROPIC_API_KEY` | Claude generation | For LLM features |
| `GOOGLE_API_KEY` | Gemini generation | For LLM features |
| `MODEL_PRIMARY` | Primary model (claude/gemini) | Optional, default: claude |
| `MODEL_FALLBACK` | Fallback model | Optional, default: gemini |
| `GENERATION_MODE` | fast_mode / quality_mode | Optional |
| `CLAY_WEBHOOK_URL` | Clay webhook endpoint | For Clay integration (placeholder) |
| `CLAY_WORKSPACE_ID` | Clay workspace identifier | For Clay integration (placeholder) |
| `CLAY_LIST_ID` | Clay list identifier | For Clay integration (placeholder) |
| `RULA_REPO_OUTPUT_DIR` | Run archive directory | Optional, default: out/runs |
| `RULA_HUMAN_REVIEW_DIR` | Human review queue dir | Optional, default: out/review_queue |
| `RULA_DQ_POLICY_PATH` | YAML data-quality rules (optional) | Unset = full pipeline |
| `RULA_MIN_DISCOVERY_QUESTIONS` | Min discovery questions (generator + judge) | Default 3 |
| `RULA_EXPORT_LINEAGE` | Add `lineage_export` to JSON exports | `1` on, `0` off |
| `RULA_BULK_DEFAULT_QUEUE` | Bulk order: `file_order` or `heuristic` | Default file order |

The system works fully without API keys using deterministic fallbacks for all outputs.

### Security note (roles and authentication)

The Streamlit sidebar **role selector** (Admin / User / Viewer) is a **demo-only** affordance for local and non-production use. It is **not** an authentication or authorization boundary: anyone with access to the app can pick a role.

- In **`ENVIRONMENT=production`**, the app resolves the effective role to **`viewer`** and disables self-service role switching (see `src/security/rbac.py`). This still does **not** replace a real identity provider.
- For any shared or internet-facing deployment, integrate **real authn** (OIDC/SAML/API tokens) and map identity claims to RBAC roles server-side; do not trust client-selected roles.

### Landing page deep links (Vercel → Streamlit)

The Next.js app in `rula-landing-page` launches Streamlit with query parameters. `app.py` applies them via `_apply_landing_query_params` before the sidebar renders:

| Query param | Values | Effect |
|-------------|--------|--------|
| `page` | `prospecting`, `map` | Sets **Navigate** to **Prospecting** or **MAP Review** (any environment). |
| `role` | `admin`, `user`, `viewer` | Sets session role in **non-production** only. In **`ENVIRONMENT=production`**, the effective role stays **`viewer`** (`resolve_role`); the role selector remains disabled. |

Re-apply: when the `(page, role)` pair in the URL **changes** (e.g. user launches another tool from the landing page in the same browser session), the bridge updates `_ui_nav_page` / `role` again and clears sidebar widget keys so **Navigate** / **Your role** match the new link.

**Direct open** (no `?page=` / `?role=`): unchanged; defaults match prior behavior. Invalid values are ignored; the bridge never raises.

### Lean UX validation (post-change)

Quick checks before release:

1. **Fresh session:** From the landing page, pick a role + tool → **Launch** → confirm **Navigate** and **Your role** (non-prod) match without manual sidebar fixes.
2. **Same session, second launch:** Open the other tool from the landing page → **Navigate** updates to the new tool (non-prod role behavior unchanged unless URL includes `role`).
3. **Production:** **Navigate** matches the tool; role is viewer and disabled; copy explains production lock.

**Future HTTP ingest (orchestrators):** see [docs/ingest_contract.md](docs/ingest_contract.md). **Phase gates / baseline:** see [docs/implementation_runbook.md](docs/implementation_runbook.md).

## UI Guide (v2)

The Streamlit app has 4 pages accessible via sidebar navigation:

1. **Prospecting** (default): Choose data source (Test Data / Clay), run in Bulk or Single-Account mode, review results with AE-friendly labels, execute one-click handoff to sequencer + CRM with automatic failure routing
2. **MAP Review**: Select evidence or use structured capture, get confidence tier with threshold explanation and downloadable export
3. **Insights**: Live telemetry metrics, provider usage, recent activity feed, evaluation baselines
4. **Admin** (admin role only): Retention cleanup, shadow compare, DLQ/incident viewer, config status

## Project Structure

```
src/
  agents/          # Pipeline agents (enrichment, matcher, generator, evaluator, judge, correction, corrections)
  config.py        # Centralized configuration from .env
  explainability/  # Value-prop rationale, threshold explanation, unit economics
  integrations/    # Ingestion (Test Data / Clay), CRM export, handoff orchestrator, review queue
  orchestrator/    # Single-account graph, bulk prospecting runner
  providers/       # Claude + Gemini providers, model router, prompt templates
  safety/          # Kill switches, circuit breakers, DLQ, sanitization, incidents
  schemas/         # Pydantic models (Account, ProspectingOutput, Correction, etc.)
  security/        # RBAC (role-based access control)
  telemetry/       # Event emission, metrics computation, UX event taxonomy
  ui/              # Reusable Streamlit components (pills, badges, chips, error states)
  validators/      # Response validation (syntactic + semantic)
docs/
  ux/              # AE persona, journey map, friction backlog, IA blueprint, design system
  integration_contracts.md  # CRM export schemas and promotion gates
tests/             # 116 tests across 19 test files
eval/              # Drift check, shadow comparison, prospecting evaluation
```

## Evaluation

```bash
PYTHONPATH=. python3 eval/drift_check.py
PYTHONPATH=. python3 eval/compare_shadow.py
```

## Key Design Decisions

- **Deterministic-first**: All pipelines produce valid output without LLM keys
- **Fallback chain**: Claude primary -> Gemini fallback -> deterministic
- **Progressive disclosure**: AE sees summary cards; technical details are collapsed
- **Role-aware**: Admin panels hidden from non-admin users
- **Explainable**: Every decision has a "why" - value prop, confidence tier, economics
- **Observable**: Telemetry events emitted for every pipeline run
- **Export-ready**: CRM export payloads with provenance and caveat fields
- **Shadow-safe**: All exports are read-only; live CRM write requires promotion gates

## Documentation

- [Architecture Overview](docs/architecture_overview.md)
- [Integration Contracts](docs/integration_contracts.md)
- [Technical Walkthrough](docs/walkthrough.md)
- [Panel Talk Track](docs/panel_talk_track.md)
- [UX Design System](docs/ux/design_system.md)
- [AE Persona](docs/ux/ae_persona.md)
- [Usability Baseline](docs/ux/usability_baseline.md)
