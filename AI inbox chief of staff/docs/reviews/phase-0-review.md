# Phase 0 Review Packet — Foundations

**Status**: v1
**Companions**: `../PRODUCT_ROADMAP.md`, `../quality-gates.md`, `../risk-register.md`

---

## Header

| Field | Value |
|-------|-------|
| Phase | 0 — Foundations |
| Packet date | 2026-04-25 |
| Author | `<owner>` |
| Reviewers | `<names>` |
| Roadmap snapshot SHA | `<git sha>` |
| Related risks | R2 (infra not provisioned), R6 (supply chain) |

---

## 1. Phase Scope

| Roadmap ID | Feature | Status | Evidence |
|------------|---------|--------|----------|
| 0.1 | Project scaffolding (pyproject, docker-compose, alembic) | PASS | `pyproject.toml`, `docker-compose.dev.yml`, `alembic.ini` |
| 0.2 | ORM models (all 11 tables) | PASS | `core/models/__init__.py` exports |
| 0.3 | Typed stage contracts | PASS | `core/schemas/contracts.py` |
| 0.4 | Security: encryption (Fernet/KMS) | PASS | `core/security/encryption.py` |
| 0.5 | Security: prompt injection detection | PASS | `tests/safety/` — 17 adversarial tests |
| 0.6 | Gmail OAuth (no send scope) | PASS | `core/gmail/auth.py` + scope assertion test |
| 0.7 | LLM client with provider fallback | PASS | `core/llm/client.py` Anthropic primary + OpenAI fallback |
| 0.8 | All 9 subagents + orchestrator | PASS | `subagents/` + `orchestrator/orchestrator.py` |
| 0.9 | API layer (health, auth, webhooks, mailboxes, assistant, undo) | PASS | `api/routers/` |
| 0.10 | Workers (ingest, scheduler) | PASS | `workers/` |
| 0.11 | Terraform infra (VPC, RDS, SQS, ECS, monitoring) | PARTIAL | `infra/terraform/*.tf` written; not applied (R2) |
| 0.12 | Unit tests (97 passing) | PASS | `pytest tests/unit/` |
| 0.13 | Integration tests (SQLite + Postgres) | PASS | `tests/integration/` 19 pgvector/JSONB/enum/cascade tests |
| 0.14 | CI/CD pipeline (GitHub Actions) | PASS | `.github/workflows/` lint+unit+integration+security |
| 0.15 | Environments (dev/staging/prod) config | PARTIAL | `.env.example` exists; staging/prod creds pending R2 |

---

## 2. Gate Criteria

| # | Criterion | Verification | Status |
|---|-----------|--------------|--------|
| 0.a | CI pipeline green on baseline unit suite | `.github/workflows/*` + latest run | PASS |
| 0.b | Unit tests for every new model | `tests/unit/test_contracts.py` + `core/models/__init__.py` | PASS |
| 0.c | Config loads under missing-env path | `tests/unit/test_security.py` covers `Settings()` failures | PASS |
| 0.d | Health endpoints + startup smoke | `tests/integration/test_health.py` | PASS |
| 0.e | Prompt-injection adversarial suite ≥ 99% | `tests/safety/` — 17/17 pass (100%) | PASS |

---

## 3. Acceptance Evidence

- **Tests**: `pytest tests/unit/ tests/integration/ tests/safety/` — 187 passing on commit `<sha>`
- **Migrations**: 001–006 applied cleanly to dev + integration DB
- **CI**: GitHub Actions backend + frontend pipelines green; ECR push verified
- **Dashboards**: `/slo/status` reachable in dev compose stack
- **PRs merged into main during this phase**: foundational scaffolding (`<PR# range>`)

---

## 4. Risk Delta

| Risk ID | Title | Pre-phase status | Post-phase status | Notes |
|---------|-------|------------------|-------------------|-------|
| R2 | Production AWS infra not provisioned | n/a | OPEN | Terraform written; `apply` deferred to staging cut |
| R6 | Supply-chain compromise via optional deps | n/a | OPEN | pypdf/python-docx import-guarded; pip-audit not yet in CI |

No new risks introduced this phase beyond those already in the register.

---

## 5. Outstanding Items / Waivers

### Waiver: 0.11 / 0.15 — Terraform applied + staging/prod env config
- **Reason**: Phase 0 deliverable is the *code* for foundations; cloud
  provisioning is tracked under cross-cutting items X.3 / X.7 / X.8 and
  blocked by R2 (single-operator timeline).
- **Compensating control**: `docker-compose.dev.yml` provides full local
  parity (postgres, redis, localstack SQS+S3, OTel collector). All Phase 1+
  development unblocked locally.
- **Revisit date**: 2026-05-15 (or sooner if Google consent screen approved).
- **Owner**: `<owner>`
- **Tracked in**: `risk-register.md::R2`

---

## 6. Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Engineering | `<owner>` | `2026-04-25` | _______________ |
| Product / Owner | `<owner>` | `2026-04-25` | _______________ |

I confirm every PASS row in §2 has verifiable evidence in §3 and the two
PARTIAL rows in §1 have a documented waiver in §5 with a compensating
control. Phase 0 is closed for the purposes of advancing to Phase 1+.

---

## Change Log

- `2026-04-25 (v1)`: Phase 0 closed retroactively. All gate criteria PASS;
  infrastructure deliverables (0.11, 0.15) waived to cross-cutting tracks.
