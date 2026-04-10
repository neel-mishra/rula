# PRD: {{PROJECT_NAME}}

## 1. Document Control
- **Document status:** {{STATUS}}
- **Last updated:** {{DATE}}
- **Author:** {{ROLE}}
- **Stakeholders:** {{STAKEHOLDER_LIST}}

---

## 2. Executive Summary
- **The pitch:** {{ONE_SENTENCE_VALUE_PROP}}
- **Strategic objective:** {{OBJECTIVE_DESCRIPTION}}
- **Core technology:** {{TECH_STACK_AND_SYSTEM_COMPONENTS}}

---

## 3. Problem Statement
### Customer/Operator Problem
- **Friction points:** {{LIST_KEY_PAIN_POINTS}}
- **Current workflow:** {{DESCRIBE_CURRENT_MANUAL_PROCESS}}

### Business Impact
| Metric | Current State (Baseline) | Target Impact |
| :--- | :--- | :--- |
| Time-to-value | {{BASELINE}} | {{TARGET}} |
| Output adoption | {{BASELINE}} | {{TARGET}} |
| Verification quality | {{BASELINE}} | {{TARGET}} |

---

## 4. Goals & Success Metrics
### Primary Goals
1. **Implementation goal:** {{GOAL_1}}
2. **Reliability goal:** {{GOAL_2}}
3. **Quality goal:** {{GOAL_3}}

---

## 5. Technical Requirements & Architecture
### Data and inference requirements
- **Input contract:** {{INPUT_SCHEMA}}
- **Validation rules:** {{VALIDATION_CONSTRAINTS}}
- **Fallback behavior:** {{FALLBACK_STRATEGY}}

### Solution architecture
1. Input enrichment
2. Decision/matching logic
3. Generation/parsing logic
4. Validation and flagging
5. Export and telemetry

---

## 6. User Experience Flow
1. **Initiation:** {{START_POINT}}
2. **Interaction:** {{CORE_STEPS}}
3. **Review:** {{REVIEW_AND_APPROVAL}}
4. **Execution:** {{HANDOFF_OR_EXPORT}}

---

## 7. Implementation Roadmap
- **Phase 1 (core):** {{PHASE_1}}
- **Phase 2 (hardening):** {{PHASE_2}}
- **Phase 3 (scale):** {{PHASE_3}}

---

## 8. Success Criteria (Readiness)
- **Technical acceptance:** {{QUALITY_THRESHOLD}}
- **Monitoring and analytics:** {{OBSERVABILITY_REQUIREMENTS}}
- **Dependencies:** {{DEPENDENCY_LIST}}

---

## 9. Go-To-Market (GTM) & Launch Plan
- **Beta segment:** {{EARLY_ADOPTER_SEGMENT}}
- **Messaging hook:** {{PRIMARY_ANGLE}}
- **Distribution channel:** {{PRIMARY_AND_SECONDARY_CHANNELS}}

---

## 10. Risks, Assumptions, & Mitigations
| Risk | Impact | Probability | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| {{RISK_1}} | {{IMPACT}} | {{PROB}} | {{MITIGATION}} |
| {{RISK_2}} | {{IMPACT}} | {{PROB}} | {{MITIGATION}} |
| **Assumption** | {{KEY_ASSUMPTION}} | — | {{HOW_TO_VALIDATE}} |

---

## 11. Appendix & Open Questions
- **Unresolved questions:** {{OPEN_ITEMS}}
- **Glossary:** {{KEY_TERMS}}
- **Reference links:** `@core/business_context.md`, `@core/product_dna.md`, `@identity/style_guide_internal.md`

---

### AI Agent Context Rule
Before drafting a PRD:
1. Anchor strategy to `@core/business_context.md`.
2. Anchor segmentation to `@core/ideal_customer_profile.md`.
3. Anchor tone to `@identity/style_guide_internal.md`.
4. Fill all placeholders with concrete, source-backed details.
