# Compound Engineering Framework

## Purpose

Define a reusable engineering system where each unit of work makes future work easier.

## Core Loop Contract

Plan -> Work -> Review -> Compound

### 1) Plan

Required outputs:
- Problem statement and user outcome
- Constraints and risk classification
- Affected components/contracts
- Validation and rollback strategy
- Explicit approval marker

### 2) Work

Required outputs:
- Implemented changes mapped to plan steps
- Validation evidence (tests/lint/type checks)
- Runtime or integration evidence for high-risk changes
- Change log tied to risk notes

### 3) Review

Required outputs:
- Findings triaged by priority (P1/P2/P3)
- Human review focused on intent, domain logic, and UX/copy
- Resolution or deferral decision for each finding
- Final merge readiness decision

### 4) Compound

Required outputs:
- Structured learning artifact with metadata
- Prevention rule updates
- Template/checklist updates where applicable
- Rule/instruction updates for future agent runs

## Operating Principles

1. Deterministic first; probabilistic where justified.
2. Contracts at every boundary.
3. Safety controls are product features, not add-ons.
4. Human review prioritizes intent and correctness, not rote syntax.
5. Evidence beats opinion for merge and release decisions.
6. Weekly compounding is mandatory.

## Repository-Specific Decisions

- Merge bar: strict by default for high-risk work.
- Hard blockers:
  - security issues
  - data integrity/contract breaks
  - major UX breakage in critical flows
  - silent behavior/fallback changes
  - missing provenance for AI-assisted outputs
- Ownership: single feature owner across the full loop.
- Parallelization: adaptive by coupling and risk, not blanket concurrency.

## Maturity Target

- Strategic target: Stage 5 compound engineering maturity (parallel cloud-scale execution).
- Near-term operational baseline: pragmatic 90-day uplift with weekly scoring.

