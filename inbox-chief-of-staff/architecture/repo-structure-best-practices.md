# Repository Structure Best Practices (Applied)

## References
- GitHub Docs: [Best practices for repositories](https://docs.github.com/en/repositories/creating-and-managing-repositories/best-practices-for-repositories)
- ADR guidance: [Architecture Decision Record examples](https://github.com/joelparkerhenderson/architecture-decision-record)
- Compound engineering folder layout: `/Users/neelmishra/.cursor/Rula/skills/compound-engineering/06-project-bootstrap/folder-layout.md`

## Applied structure for this project
- `inbox-chief-of-staff/README.md`: entry point and execution rules.
- `inbox-chief-of-staff/roadmap.md`: phase plan and gating schedule.
- `inbox-chief-of-staff/research/`: source-backed discovery artifacts.
- `inbox-chief-of-staff/prds/`: one PRD per phase, versioned updates.
- `inbox-chief-of-staff/tickets/`: prioritized phase ticket trackers.
- `inbox-chief-of-staff/reviews/`: gate approvals and review outcomes.
- `inbox-chief-of-staff/architecture/`: connectors, contracts, ADRs, diagrams.
- `inbox-chief-of-staff/runbooks/`: deploy, incident, rollback procedures.

## Operational conventions
- Keep files small and purpose-specific.
- Use markdown for planning/governance artifacts.
- Record decisions as ADRs in `architecture/adrs/` when architecture changes.
- Link every completed ticket to validation evidence.
- Keep gate decisions immutable; append updates with dates.
