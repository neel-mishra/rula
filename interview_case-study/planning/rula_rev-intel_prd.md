## 17. Product Requirements Document (PRD)

### 17.1 Executive Summary

**Problem Statement**  
Rula's employer AE motion is constrained by manual prospect research, manual outreach drafting, and unstructured MAP evidence verification. This creates throughput bottlenecks, variable messaging quality, and forecast risk due to unverifiable commitments.

**Solution Overview**  
Build a staged, multi-agent revenue intelligence system with:
- Prospecting Pod: enrich -> match value props -> generate outreach -> evaluate quality
- MAP Verification Pod: parse evidence -> score confidence -> flag required actions
- Orchestrator and validation gateway: enforce H.A.V.O.C. controls, human checkpoints, and safe endpoint writes
- Closed-loop audit layer: LLM-as-a-Judge with self-correction and drift detection

**Business Impact**  
- Reduce AE prep time from 20-30 minutes/account to < 2 minutes review time
- Improve outreach consistency and adoption (target >= 60% no-edit usage in v1)
- Increase MAP data trustworthiness for forecasting via confidence-tiered verification
- Preserve compliance posture in a regulated context (HIPAA-adjacent, PII-sensitive workflows)

**Resource Requirements**  
- 1 GTM engineer (owner), 1 RevOps stakeholder (Austin), 1 Salesforce architect partner (Trevor), 1 MarTech partner (Cesar), 1 manager/reviewer (Paul)
- APIs: Anthropic/OpenAI enterprise, Salesforce, enrichment provider
- Infra: Python services, PostgreSQL, Redis, secrets manager, observability stack

**Risk Assessment (Top 5)**  
- Hallucinated or non-compliant outreach claims  
- Inflated MAP scoring from weak/secondhand evidence  
- API failure chain causing dropped entities  
- PII leakage through prompts/logs  
- Over-complex implementation before proof of value  
Mitigations are embedded in phases, guardrails, and QA gates.

### 17.2 Product Overview

**Vision**  
Create a trustworthy, scalable GTM automation layer that accelerates account progression from assignment to verifiable MAP commitment without compromising compliance, accuracy, or human judgment.

**Target Users**  
- Primary: Account Executives (AEs)  
- Secondary: AE Managers, RevOps, Salesforce Admin, MarTech  
- Tertiary: Hiring/panel stakeholders evaluating production readiness

**Value Proposition**  
- Faster: seconds for draft outputs, not manual minutes
- Better: structured, auditable decisions and outputs
- Safer: validation-first, human-in-the-loop, compliance-aware automation

**Success Criteria**  
- Prospecting output adoption >= 60% no-edit usage by AEs in shadow/live test
- MAP tier agreement >= 90% with human reviewers on curated set
- Shadow criteria met: >= 98% structural correctness and >= 80% directional accuracy
- Zero invalid writes to CRM via validation gateway

**Core Assumptions**  
- AEs remain final sender/approver for outbound outreach in v1
- MAP evidence sources remain mixed during transition
- Salesforce remains system of engagement, not system of truth
- Enterprise contracts for model providers allow compliant data handling

### 17.3 Objectives and OKR Alignment

**Objective A: Increase AE throughput without lowering quality**  
- KR1: Reduce average research+draft time/account by >= 80%  
- KR2: Achieve >= 60% generated-email no-edit adoption  
- KR3: Maintain quality score >= 3.5/5 on accepted outputs

**Objective B: Improve forecast reliability from MAP data**  
- KR1: Tier MAP submissions (HIGH/MEDIUM/LOW) with traceable reasoning  
- KR2: Reduce false-positive MAP commitments by >= 50% vs current baseline  
- KR3: 100% MAP records include required structured fields or explicit missing flags

**Objective C: Ensure resilient and compliant operations**  
- KR1: 0 unvalidated CRM writes  
- KR2: 100% failed operations routed to DLQ with recoverable metadata  
- KR3: 100% LLM calls processed through PII minimization policy path

### 17.4 Scope

**In Scope (v1-v2)**  
- Part 1 Prospecting system for 8-account case dataset and extension to CRM-fed accounts
- Part 2 MAP verification on unstructured evidence with confidence scoring/action flags
- Orchestration, guardrails, validation gateway, shadow mode, audit loop
- Security/compliance controls described in Section 11

**Out of Scope (current PRD window)**  
- Automated multichannel sending (LinkedIn/phone automation)
- Closed/Won attribution based on patient-start events
- Full UI replacement inside Salesforce (beyond integration objects/fields)
- Full MLOps platform or model fine-tuning on production data

### 17.5 Functional Requirements

#### FR-1 Prospecting Pod
- FR-1.1 Ingest account profile and validate schema via Gatekeeper
- FR-1.2 Enrich and normalize account fields; compute ICP/data completeness scores
- FR-1.3 Match and rank value propositions with reasoning
- FR-1.4 Generate first-touch email plus 2-3 discovery questions
- FR-1.5 Evaluate output quality and set `human_review_needed` flags

#### FR-2 MAP Verification Pod
- FR-2.1 Parse evidence into structured commitment schema
- FR-2.2 Score commitment confidence with weighted signal model
- FR-2.3 Flag follow-up actions and quota eligibility state
- FR-2.4 Apply secondhand-evidence guardrails before final tier assignment

#### FR-3 Orchestration and Control Plane
- FR-3.1 Route tasks to prospecting or MAP pipelines
- FR-3.2 Persist state/checkpoints at each node
- FR-3.3 Support pause/resume at human-in-the-loop checkpoints
- FR-3.4 Feature-flag stage capabilities (Judge, Shadow, MAP pod)

#### FR-4 Validation and Endpoint Safety
- FR-4.1 Validate every output against canonical schemas and business rules
- FR-4.2 Map canonical outputs to CRM-specific fields via adapter
- FR-4.3 Reject invalid writes and route to rejection queue with reason codes
- FR-4.4 Support shadow routing to hidden fields before live promotion

#### FR-5 Closed-Loop Feedback
- FR-5.1 Judge evaluates outputs from both pods with explicit rubrics
- FR-5.2 Retry failed outputs with bounded self-correction loop
- FR-5.3 Capture feedback memory (judge findings, edits, outcomes)
- FR-5.4 Run drift checks against golden set on each prompt/model revision

### 17.6 User Stories and Acceptance Criteria

**US-1 AE Prospecting Draft**
As an AE, I want a draft email and discovery questions tailored to each account so that I can initiate outreach faster with quality.
Acceptance Criteria:
- Given a valid account profile, when the prospecting flow runs, then system returns ranked value props, 1 email draft, and 2-3 discovery questions.
- Given sparse account data, when output is generated, then missing-data flags are present and no hallucinated fields are introduced.

**US-2 RevOps MAP Trust**
As RevOps, I want MAP evidence scored into confidence tiers with traceable logic so that forecasts rely on verifiable commitments.
Acceptance Criteria:
- Given evidence samples A/B/C, when verification runs, then tiers map to HIGH/LOW/MEDIUM respectively.
- Given secondhand evidence scored HIGH by model, when guardrail applies, then score is downgraded and flagged.

**US-3 Salesforce Safety**
As Salesforce architect, I want only schema-valid outputs written via a mapping layer so that CRM data integrity is protected.
Acceptance Criteria:
- Given invalid output (e.g., out-of-range confidence), when write attempted, then write is blocked and reason is logged.
- Given shadow mode enabled, when writes occur, then only shadow fields are updated and live fields remain unchanged.

**US-4 Compliance Officer / Security**
As a compliance stakeholder, I want PII minimized and data access controlled so that legal/regulatory risk is reduced.
Acceptance Criteria:
- Given LLM invocation, when prompt is sent, then PII tokenization policy is applied according to data tier.
- Given unauthorized role request, when endpoint is accessed, then access is denied and event is logged.

### 17.7 Business Rules

- BR-1 Any LOW MAP tier blocks quota credit until required actions complete.
- BR-2 Any output failing schema/business validation cannot hit live CRM endpoints.
- BR-3 Any Judge hard-fail after 2 retries routes to human review.
- BR-4 Any secondhand evidence cannot be finalized as HIGH without first-party corroboration.
- BR-5 No outbound auto-send in v1; AE is required human approver.

### 17.8 Non-Functional Requirements

**Performance**  
- P95 per-account prospecting pipeline < 30s in v1 environment
- P95 MAP verification < 15s for standard evidence payload

**Reliability**  
- No data loss on external failure (DLQ coverage 100%)
- Retry policies bounded; no infinite loops

**Security & Compliance**  
- Data-tier enforcement, encryption at rest/in transit, RBAC, secrets management
- LLM provider controls: enterprise terms, DPA/BAA where required, no training on prompts

**Observability**  
- 100% trace coverage across pipeline nodes
- Cost, latency, error-rate, retry-rate dashboards by pod

**Usability**  
- Outputs readable and editable by AE without engineering assistance
- Reasoning summaries concise enough for manager review

### 17.9 Technical Considerations

**Architecture**  
- Orchestrator-managed pods (LangGraph), validation gateway, SoT in data lake, CRM adapter

**Data Model**  
- Canonical schemas for Account, ProspectOutput, MAPEvidence, MAPAssessment, LineageRecord

**Integration Requirements**  
- Salesforce object mappings for account context, MAP assessment, and shadow fields
- Model provider abstractions with fallback and policy wrappers

**Infrastructure Needs**  
- Python runtime, PostgreSQL, Redis, secrets manager, CI for evals, optional Streamlit demo

### 17.10 Analytics and Measurement Plan

**Adoption Metrics**  
- Email no-edit adoption rate
- Median edit distance by AE and account segment

**Effectiveness Metrics**  
- Response rate and meeting-booking lift vs baseline
- MAP tier agreement with human reviewers

**Quality Metrics**  
- Judge pass rate, correction success rate, drift score

**Operations Metrics**  
- DLQ inflow/outflow, circuit breaker events, rejection queue counts
- API cost per processed account/evidence item

### 17.11 Release Plan and Milestones

- Milestone M1: Phase 1-2 complete (MVP + safe foundation)
- Milestone M2: Phase 3 complete (Prospecting pod on all 8 accounts)
- Milestone M3: Phase 4 complete (MAP pod on A/B/C)
- Milestone M4: Phase 5-6 complete (audit + safety net)
- Milestone M5: Phase 7 complete (shadow thresholds met)
- Milestone M6: Phase 8-9 complete (hardening + submission artifacts)

Promotion occurs only when all phase QA gates pass.

### 17.12 Dependencies

- Enterprise model API access and legal agreements
- Salesforce field/object availability for shadow/live mappings
- Stakeholder review bandwidth for QA gate signoff
- Baseline metrics from current manual process for comparison

### 17.13 Risks and Mitigations

- Risk: Over-engineering before proving value  
  Mitigation: Phase 1 thin slice and strict gate progression
- Risk: Model volatility changes output quality  
  Mitigation: prompt versioning + golden-set drift checks
- Risk: MAP scoring disputes with AEs  
  Mitigation: transparent signal breakdown + manual override workflow
- Risk: Compliance regressions under delivery pressure  
  Mitigation: security/compliance checks as release blockers

### 17.14 Open Questions

- Final confidence tier cutoffs after first 2 weeks of shadow data?
- Which enrichment sources are legally and operationally approved at launch?
- What Salesforce object design best balances reporting needs and admin overhead?
- Who is the formal approver at each phase gate (RACI)?

### 17.15 RACI (Implementation Governance)

- **Responsible**: GTM Engineer (build), Salesforce Architect (CRM integration), MarTech partner (campaign alignment)
- **Accountable**: Hiring Manager / GTM Engineering Lead
- **Consulted**: RevOps, Compliance/Legal, Security
- **Informed**: AE managers and pilot AEs

### 17.16 PRD Review and Change Control

- PRD owner: GTM Engineer
- Review cadence: weekly during build phases; ad hoc on risk events
- Versioning: semantic version tags in the plan (`PRD vX.Y`)
- Change policy: any change impacting compliance, scoring policy, or endpoint writes requires stakeholder signoff from RevOps + Salesforce + manager
