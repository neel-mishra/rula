# Integration Contracts (v1)

## Overview

All outbound payloads are shadow-safe (read-only export, no CRM write) in v1. Live write paths require explicit promotion gates.

## Prospecting Export Contract

```json
{
  "account_id": 1,
  "company": "Meridian Health Partners",
  "industry": "Health system",
  "email_subject": "Idea for Meridian Health Partners' benefits strategy",
  "email_body": "Hi Lisa Chen, ...",
  "email_cta": "Open to a call next Tuesday or Wednesday?",
  "discovery_questions": ["..."],
  "top_value_prop": "total_cost_of_care",
  "value_prop_rationale": "total_cost_of_care selected from industry/size/notes signals.",
  "quality_score": 4.2,
  "human_review_needed": false,
  "audit_pass": true,
  "audit_score": 4.5,
  "content_model": "deterministic",
  "content_prompt_version": "v1",
  "content_validation_status": "passed",
  "content_review_required": false,
  "provider_primary": "",
  "provider_fallback_used": false,
  "confidence_caveats": []
}
```

## MAP Export Contract

```json
{
  "evidence_id": "A",
  "confidence_tier": "HIGH",
  "confidence_score": 85,
  "risk_factors": [],
  "recommended_actions": ["Proceed to deal review."],
  "map_threshold_rationale": "High confidence (score 85, range 75-100)...",
  "audit_pass": true,
  "audit_score": 4.0,
  "confidence_caveats": []
}
```

## Provenance Fields

Every export includes:
- `content_model`: which model generated the content ("deterministic", "claude", "gemini")
- `content_prompt_version`: prompt template version used
- `content_validation_status`: "passed", "failed_repaired", "failed_deterministic"
- `content_review_required`: whether human review was flagged
- `provider_primary`: primary provider attempted
- `provider_fallback_used`: whether fallback chain was activated

## Export Actions (v1)

| Action | Format | Location |
|--------|--------|----------|
| Download CRM export | JSON | Prospecting result card, MAP result card |
| Download email | TXT | Prospecting result card |
| Copy email to clipboard | Code block | Prospecting result card |

## Promotion Gates for Live Write

Before enabling CRM write paths:
1. 4-week shadow period with >= 95% structural match
2. AE acceptance rate >= 60% on exports
3. Zero safety/audit gate failures
4. Manager sign-off on export data quality
5. CRM integration test suite passing in staging
