# Streamlit Design System Spec (v1)

## Design Tokens

### Color Semantics

| Token | Hex | Usage |
|-------|-----|-------|
| `success` | `#10B981` | Pass states, ready-to-send, HIGH tier |
| `warning` | `#F59E0B` | Review needed, MEDIUM tier, caution |
| `error` | `#EF4444` | Failure, LOW tier, blocked |
| `neutral` | `#6B7280` | Disabled, unknown, placeholder |
| `info` | `#3B82F6` | Informational badges, links |
| `surface` | `#F9FAFB` | Card backgrounds |
| `text-primary` | `#111827` | Primary text |
| `text-secondary` | `#6B7280` | Secondary/caption text |

### Typography Scale

| Level | Size | Weight | Use |
|-------|------|--------|-----|
| Page header | `st.header` | Bold | Page titles |
| Section header | `st.subheader` | Semi-bold | Section dividers |
| Card title | `#### markdown` | Bold | Result card titles |
| Body | `st.write` / `st.markdown` | Regular | Content text |
| Caption | `st.caption` | Regular | Help text, timestamps |
| Metric value | `st.metric` | Bold | KPI numbers |

### Spacing (8px grid)

| Token | Value | Usage |
|-------|-------|-------|
| `xs` | 4px | Inline pill padding |
| `sm` | 8px | Chip padding, tight gaps |
| `md` | 16px | Standard section gap (Streamlit default) |
| `lg` | 24px | Between major sections (`st.markdown("---")`) |
| `xl` | 32px | Page-level breathing room |

### Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `pill` | 12px | Status pills, confidence badges |
| `chip` | 8px | Risk factor chips, tags |
| `card` | 8px | Card containers (via Streamlit expanders) |

## Components

### 1. Confidence Pill

Inline HTML span with tier-to-color mapping.

```
States:
  HIGH  → green (#10B981) + white text
  MEDIUM → amber (#F59E0B) + white text
  LOW   → red (#EF4444) + white text
  UNKNOWN → gray (#6B7280) + white text

Format: "TIER (score)" or "TIER" if no score
Padding: 4px 12px, border-radius: 12px, font-weight: 600
```

### 2. Audit Status Badge

Inline HTML span for audit pass/review status.

```
States:
  PASS   → green (#10B981) + white text
  REVIEW → amber (#F59E0B) + white text
  FAIL   → red (#EF4444) + white text

Format: "PASS" | "REVIEW" | "FAIL"
Padding: 3px 10px, border-radius: 10px, font-size: 13px
```

### 3. Risk Factor Chips

Inline HTML spans for risk factors.

```
Background: #FEE2E2 (light red)
Text: #991B1B (dark red)
Padding: 2px 8px, border-radius: 8px, font-size: 12px
Separated by &nbsp;
```

### 4. Result Card

Composed from Streamlit primitives:

```
st.markdown("#### Outcome")       → Card title
st.columns(3)                     → Metric row (audit, quality, corrections)
st.expander("Why...")             → Rationale sections
st.markdown("---")                → Section divider
st.markdown("#### Next action")   → Action header
st.success/st.warning             → Action guidance
st.code(...)                      → Copyable email text
st.expander("Technical details")  → Collapsed debug
```

### 5. Action Button

```
st.button("Label", type="primary", use_container_width=True)

States:
  Default: Primary color, full width
  Loading: Wrapped in st.spinner("...")
  Disabled: Streamlit handles via disabled=True
  Error: st.error() rendered below button
```

### 6. Empty / Loading / Error States

Every page must handle:

| State | Rendering |
|-------|-----------|
| Empty | `st.info("No data available. Run a pipeline to see results.")` |
| Loading | `st.spinner("Running pipeline...")` wrapping the action |
| Error | `st.error(str(exception))` with recovery suggestion |
| Success | `st.success("Pipeline completed")` or result card |
| Permission denied | `st.error("Permission denied: ...")` with role guidance |
| Circuit breaker | `st.warning("System temporarily unavailable. Try again shortly.")` |
| Kill switch | `st.warning("Pipeline disabled by administrator.")` |

## Interaction States

### Button states
- **Default**: Blue primary, white text, full width
- **Hover**: Streamlit built-in hover effect
- **Active/Loading**: Button hidden, spinner shown
- **Disabled**: Grayed out (viewer role)

### Expander states
- **Default collapsed**: User sees only the header label
- **Expanded**: Full content visible
- **Convention**: Technical/debug expanders start collapsed; primary rationale starts collapsed; email content starts visible

## Accessibility

- All status pills use sufficient contrast (white text on colored background, >= 4.5:1 ratio)
- Interactive elements are keyboard-navigable (Streamlit built-in)
- No information conveyed by color alone: status text accompanies every pill ("HIGH", "PASS")
- Expander labels are descriptive: "Why this confidence tier?" not "Details"
- Error messages include suggested next action, not just error text
- Metric labels paired with values for screen reader context
