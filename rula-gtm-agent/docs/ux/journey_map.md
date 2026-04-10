# AE Journey Map

## Stage 1: Open Tool
- **Action**: AE opens Streamlit app at start of prospecting session
- **Thought**: "Let me check which accounts to work today"
- **Emotion**: Neutral
- **v0 friction**: Greeted by 4 tabs, sidebar admin controls, no task guidance

## Stage 2: Select Account
- **Action**: Choose an account from dropdown
- **Thought**: "I need the best account to call right now"
- **Emotion**: Slight impatience
- **v0 friction**: Dropdown shows ID:company with no priority signal; raw JSON payload visible

## Stage 3: Run Pipeline
- **Action**: Click "Run Prospecting"
- **Thought**: "Give me something I can send"
- **Emotion**: Anticipation
- **v0 friction**: Button works, but no loading indicator or progress feedback

## Stage 4: Review Output
- **Action**: Read result, decide to use or skip
- **Thought**: "Is this good enough to send? Why this angle?"
- **Emotion**: Critical evaluation
- **v0 friction**: Full JSON blob; audit fields mixed with email; no highlighted next step

## Stage 5: Act on Output
- **Action**: Copy email, note discovery questions, move to CRM
- **Thought**: "Let me get this into Salesforce"
- **Emotion**: Productive momentum (if output is clear) or frustration (if not)
- **v0 friction**: No copy button, no export, no CRM-ready format

## Stage 6: MAP Review (when needed)
- **Action**: Paste or select evidence, run verification
- **Thought**: "Is this commitment real? Can I tell my manager HIGH?"
- **Emotion**: Caution
- **v0 friction**: Evidence text area works but output is raw JSON with no confidence visualization

## Opportunities

- Guide the AE through a linear flow instead of tabs
- Show result cards instead of JSON
- Add copy/export actions at the point of decision
- Hide admin/debug by default; reveal on demand
- Confidence visualization (pill/meter) instead of raw numbers
