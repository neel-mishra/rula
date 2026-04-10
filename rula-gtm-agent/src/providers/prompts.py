from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SYSTEM_SALES = (
    "You are a senior sales copywriter for Rula Health, a behavioral health company "
    "that helps employers improve employee mental healthcare access. "
    "Write in a professional, empathetic, and concise tone. Never be pushy. "
    "Always ground claims in the prospect's context."
)

SYSTEM_GTM_STRATEGIST = (
    "You are an elite GTM Strategist. Your task is to generate three "
    "high-stakes discovery questions for a Rula Account Executive to use "
    "during a first meeting.\n\n"
    "The Goal: Shift the conversation from \"features\" to \"marketing "
    "partnership and employee engagement\"."
)


def _business_dna_prompt_block(slices: list[str]) -> str:
    """Build a bounded context injection from business DNA.

    Returns an empty string when the registry is unavailable, so prompts
    degrade gracefully to their current behavior.
    """
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded:
            block = reg.prompt_block(slices)
            if block:
                return f"\n\n--- Business Context (sourced, verified) ---\n{block}\n--- End Business Context ---\n"
    except Exception:
        logger.debug("Business DNA context unavailable for prompt injection")
    return ""


def email_prompt_v3(
    *,
    prospect_name: str,
    company_name: str,
    company_context: str,
    segment_label: str,
    health_plan: str,
    mapped_value_prop: str,
    similar_competitor: str,
) -> str:
    """Strict 3-paragraph email prompt (v3 deterministic contract).

    All placeholders are pre-populated before LLM invocation.
    """
    return f"""Construct a 3-paragraph email body following this strict deterministic structure:

1. The Pattern Interrupt (Relevance): Reference the following company context: "{company_context}". Connect it to the difficulty of maintaining a high-performing workforce. Do not use "I hope you're well."

2. The Straight Line (The Rula Solution): Introduce Rula as the solution to the engagement gap.
* Constraint: You must mention that Rula is free for the employer and works with {health_plan} to remove financial friction.

Segment Logic: If the segment is a Health System, focus on "Total Cost of Care." If it is a University, focus on "Student/Staff Access".
The account segment is: {segment_label}. The mapped value proposition is: {mapped_value_prop.replace("_", " ")}.

3. The Offer (The MAP): Frame the meeting as a discussion about a "Marketing Partnership" rather than a sales pitch.
* The Pitch: "We handle the provider network and the internal marketing campaigns so your team doesn't have to".

The CTA: "Open to seeing the campaign playbook we used to drive utilization at {similar_competitor}?"

Strict Banned List: "Revolutionary," "pioneering," "partnership" (in the first sentence), "help," "excited," "reached out," "checking in."

Additional context:
- Prospect name: {prospect_name}
- Company: {company_name}
- Health plan: {health_plan}

Return EXACTLY this JSON (no markdown fences):
{{"subject_line": "...", "body": "...", "cta": "..."}}

Rules:
1. Subject line: < 60 chars, mention the company name, no clickbait.
2. Body: exactly 3 paragraphs following the structure above.
3. CTA: use the campaign-playbook framing specified above.
4. Never use words from the Strict Banned List.
5. Only use claims that appear in the Business Context section below. Do not invent statistics.
{_business_dna_prompt_block(["voice", "claims", "pillars"])}"""


def discovery_questions_prompt_v3(
    *,
    prospect_name: str,
    company_context: str,
    health_plan: str,
    mapped_value_prop: str,
    wedge: str,
) -> str:
    """Strategic Wedge discovery-question prompt (v3 deterministic contract)."""
    return f"""Input Variables:
[Prospect_Name]: {prospect_name}
[Company_Context]: {company_context}
[Health_Plan]: {health_plan}
[Mapped_Value_Prop]: {mapped_value_prop.replace("_", " ")}
[The_Wedge]: {wedge}

The Prompt Logic (Deterministic Rules)
Generate three questions based on these exact categories:

Question 1: The "Engagement Gap" (The Hook)
* Logic: Reference [Company_Context] and ask how they measure the success of current benefits.
* Constraint: Use the "Straight Line" method—focus on the disparity between having a benefit and employees actually using it.

Question 2: The "Friction Point" (The Logic)
* Logic: Tie the [Health_Plan] to the difficulty of finding in-network care.
* Constraint: Ask about the administrative burden or "employee feedback" they've received regarding mental health access.

Question 3: The "Future Commitment" (The Close)
* Logic: Pivot toward the Mutual Action Plan (MAP).
* Constraint: Ask what their current process is for internal employee communications. We need to know if they have the "marketing muscle" to partner with us.

Return a JSON array of exactly 3 strings. No markdown fences. Example:
["Question 1?", "Question 2?", "Question 3?"]
{_business_dna_prompt_block(["voice", "product", "icp"])}"""


# Keep v1 prompts available for backward compatibility / audit pipeline
def email_prompt(
    company: str,
    contact_name: str,
    industry: str,
    employee_count: int | None,
    top_value_prop: str,
    value_prop_reasoning: str,
    correction_feedback: list[str] | None = None,
) -> str:
    emp = f" ({employee_count} employees)" if employee_count else ""
    feedback_block = ""
    if correction_feedback:
        items = "\n".join(f"- {f}" for f in correction_feedback)
        feedback_block = f"\n\nPrevious version feedback (address each point):\n{items}"

    return f"""Write a cold prospecting email for:
- Company: {company}{emp}
- Industry: {industry}
- Contact: {contact_name}
- Primary value proposition: {top_value_prop}
- Why this angle: {value_prop_reasoning}
{feedback_block}

Return EXACTLY this JSON (no markdown fences):
{{"subject_line": "...", "body": "...", "cta": "..."}}

Rules:
1. Subject line: < 60 chars, mention the company name, no clickbait.
2. Body: 3-5 short paragraphs. Reference the company by name at least once. Tie benefits to their industry.
3. CTA: Propose a specific 20-minute call, suggest two days.
4. Never use exclamation marks or "exciting".
"""


def discovery_questions_prompt(
    company: str,
    industry: str,
    top_value_prop: str,
) -> str:
    return f"""Generate 3 discovery questions for a first call with {company} in {industry}.
Focus on their likely priorities around {top_value_prop.replace("_", " ")}.

Return a JSON array of 3 strings. No markdown fences. Example:
["Question 1?", "Question 2?", "Question 3?"]

Rules:
1. Each question should be open-ended and consultative.
2. Questions should help the AE understand the prospect's current state, pain, and decision process.
3. Avoid yes/no questions.
"""


def map_synthesis_prompt(
    evidence_text: str,
    confidence_tier: str,
    confidence_score: int,
    risk_factors: list[str],
) -> str:
    risks = ", ".join(risk_factors) if risk_factors else "none"
    return f"""Summarize this MAP (Mutual Action Plan) verification result for a sales manager.

Evidence text:
{evidence_text}

System assessment:
- Confidence tier: {confidence_tier}
- Confidence score: {confidence_score}
- Risk factors: {risks}

Return a 2-3 sentence plain-text summary explaining:
1. What the evidence says about commitment level.
2. Why the confidence tier was assigned.
3. What to watch for next.

No JSON, no markdown. Just the summary paragraph.
"""
