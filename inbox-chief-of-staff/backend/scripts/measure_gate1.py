"""Gate 1 composite metric measurement script.

Computes the three Gate 1 component scores and the composite:

    Composite = 0.40 * triage_quality
              + 0.35 * time_saved
              + 0.25 * draft_acceptance

Pass conditions
---------------
- Composite >= 0.75
- triage_quality >= 0.72   (precision + recall of priority classification)
- time_saved    >= 0.60    (self-reported; supplied via --time-saved flag)
- draft_acceptance >= 0.50 (helpful / (helpful + unhelpful) draft ratings)

Usage
-----
    uv run python3 scripts/measure_gate1.py --time-saved 0.65

Optional flags
--------------
    --since YYYY-MM-DD    Only consider records created on or after this date
                          (default: 30 days ago)
    --database-url URL    Override the DATABASE_URL in .env
    --env-file PATH       Path to the .env file (default: .env in cwd)
    --min-samples INT     Minimum sample size before a score is considered
                          reliable (default: 20; printed as a warning when
                          not met, but computation still proceeds)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# .env loader — stdlib only, no dotenv dependency required
# ---------------------------------------------------------------------------

def _load_env_file(path: Path) -> None:
    """Parse a simple KEY=VALUE .env file and set missing env vars."""
    if not path.exists():
        return
    with path.open() as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure Gate 1 composite metric for Inbox Chief of Staff.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--time-saved",
        type=float,
        required=True,
        metavar="FLOAT",
        help="Self-reported time-saved score (0.0–1.0).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Only include records on or after this date (default: 30 days ago).",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        metavar="URL",
        help="Override DATABASE_URL from .env.",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        metavar="PATH",
        help="Path to the .env file.",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=20,
        metavar="INT",
        help="Warn when sample count is below this threshold.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def _get_eval_samples(
    db,
    sample_type: str,
    since: datetime,
) -> list:
    """Return all eval_samples rows matching sample_type created since `since`."""
    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            SELECT
                id,
                sample_type,
                input_hash,
                output_hash,
                human_label,
                model_output,
                score,
                model_version,
                created_at
            FROM eval_samples
            WHERE sample_type = :sample_type
              AND created_at >= :since
            ORDER BY created_at DESC
            """
        ),
        {"sample_type": sample_type, "since": since},
    )
    return result.mappings().all()


async def _get_draft_rows(db, since: datetime) -> list:
    """Return Draft rows reviewed since `since` with status accepted/rejected/edited."""
    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            SELECT
                id,
                status,
                user_feedback,
                reviewed_at,
                confidence
            FROM drafts
            WHERE reviewed_at >= :since
              AND status IN ('accepted', 'rejected', 'edited')
            ORDER BY reviewed_at DESC
            """
        ),
        {"since": since},
    )
    return result.mappings().all()


async def _get_triage_with_corrections(db, since: datetime) -> tuple[list, list]:
    """Return (triage_results, correction_eval_samples) since `since`.

    triage_results — all AI triage outputs (model priority on each message).
    correction_eval_samples — eval_samples of type "triage" that have a
        human_label (i.e., the user corrected the AI's priority).
    """
    from sqlalchemy import text

    triage_result = await db.execute(
        text(
            """
            SELECT
                tr.id,
                tr.priority AS ai_priority,
                tr.confidence,
                tr.created_at
            FROM triage_results tr
            JOIN workflow_runs wr ON wr.id = tr.workflow_run_id
            WHERE tr.created_at >= :since
            ORDER BY tr.created_at DESC
            """
        ),
        {"since": since},
    )
    triage_rows = triage_result.mappings().all()

    correction_result = await db.execute(
        text(
            """
            SELECT
                id,
                human_label,
                model_output,
                created_at
            FROM eval_samples
            WHERE sample_type = 'triage'
              AND human_label IS NOT NULL
              AND created_at >= :since
            ORDER BY created_at DESC
            """
        ),
        {"since": since},
    )
    correction_rows = correction_result.mappings().all()

    return list(triage_rows), list(correction_rows)


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

LOW_SAMPLE_THRESHOLD = 20


def _compute_triage_quality(
    triage_rows: list,
    correction_rows: list,
    min_samples: int,
) -> tuple[float | None, dict]:
    """
    Compute triage_quality = (precision + recall) / 2 for the 'urgent' class.

    Strategy:
    - total_messages   = number of triage_results rows (all AI calls)
    - corrections       = eval_samples with human_label (user said AI was wrong)
    - correct_AI_urgent = triage_results with priority='urgent' that have NO
                          corresponding correction (assumed correct)
    - total_AI_urgent   = triage_results with priority='urgent'
    - total_urgent_true = triage_results where priority='urgent' (no correction)
                          + corrections where human_label='urgent' (AI missed it)

    Note: corrections are matched heuristically by creation time proximity
    (within 5 minutes).  For an exact match we'd need the message_id in both
    tables, but the feedback endpoint writes input_hash=sha256({message_id})
    without exposing the raw ID here.  We therefore use a simpler but sound
    approximation: every correction record represents a case where the AI was
    wrong, so:

        precision = (urgent_AI - urgent_AI_corrected) / urgent_AI
        recall    = (urgent_AI - urgent_AI_corrected)
                    / (urgent_AI - urgent_AI_corrected + missed_urgent)

    where:
        urgent_AI          = triage rows with ai_priority='urgent'
        urgent_AI_corrected = corrections where model_output was urgent but
                              human_label != 'urgent'
        missed_urgent       = corrections where human_label='urgent' (AI gave
                              non-urgent, user corrected to urgent)
    """
    info: dict = {}

    total_messages = len(triage_rows)
    info["total_triage_results"] = total_messages

    total_corrections = len(correction_rows)
    info["total_corrections"] = total_corrections

    if total_messages == 0:
        info["note"] = "No triage results found — cannot compute triage_quality."
        return None, info

    # Count urgent AI predictions from triage_results table
    urgent_ai = sum(1 for r in triage_rows if r["ai_priority"] == "urgent")
    info["urgent_ai_count"] = urgent_ai

    # From correction samples: where did the AI say "urgent" but user disagreed?
    # model_output may be {} (feedback endpoint) or {"priority": "urgent"}
    urgent_ai_wrong = sum(
        1 for c in correction_rows
        if (
            c["model_output"].get("priority") == "urgent"
            and c["human_label"] != "urgent"
        )
    )

    # Where did the AI NOT say urgent, but user corrected TO urgent?
    missed_urgent = sum(
        1 for c in correction_rows
        if c["human_label"] == "urgent"
        and c["model_output"].get("priority", "") != "urgent"
    )

    # Fallback: if corrections have no model_output.priority, use aggregate count
    # (corrections all represent AI errors; split proportionally by urgent_ai share)
    has_priority_in_output = any(
        c["model_output"].get("priority") for c in correction_rows
    )
    if not has_priority_in_output and total_corrections > 0:
        # Can't discriminate — treat all corrections as: AI was wrong for urgent class
        # proportionally to how many urgents the AI called vs total
        if urgent_ai > 0 and total_messages > 0:
            urgent_fraction = urgent_ai / total_messages
            urgent_ai_wrong = round(total_corrections * urgent_fraction)
            missed_urgent = total_corrections - urgent_ai_wrong
        else:
            urgent_ai_wrong = 0
            missed_urgent = total_corrections
        info["priority_inference"] = "proportional (no model_output.priority in corrections)"

    info["urgent_ai_wrong"] = urgent_ai_wrong
    info["missed_urgent"] = missed_urgent

    correct_urgent = max(urgent_ai - urgent_ai_wrong, 0)
    total_true_urgent = correct_urgent + missed_urgent

    precision = correct_urgent / urgent_ai if urgent_ai > 0 else 1.0
    recall = correct_urgent / total_true_urgent if total_true_urgent > 0 else 1.0

    info["precision"] = round(precision, 4)
    info["recall"] = round(recall, 4)

    # triage_quality = simple average of precision and recall
    quality = (precision + recall) / 2.0

    if total_messages < min_samples:
        info["low_sample_warning"] = (
            f"Only {total_messages} triage result(s) — "
            f"score unreliable until n >= {min_samples}."
        )

    return round(quality, 4), info


def _compute_draft_acceptance(
    eval_draft_samples: list,
    draft_status_rows: list,
    min_samples: int,
) -> tuple[float | None, dict]:
    """
    draft_acceptance = helpful / (helpful + unhelpful)

    Primary source: eval_samples of type 'draft' with score set (1.0=helpful, 0.0=unhelpful).
    Fallback source: drafts table where status in ('accepted', 'rejected', 'edited').
        accepted  → helpful
        rejected  → unhelpful
        edited    → helpful (user found it useful enough to edit, not discard)
    """
    info: dict = {}

    # --- Primary: eval_samples feedback ratings ---
    scored_evals = [s for s in eval_draft_samples if s["score"] is not None]
    info["eval_feedback_count"] = len(scored_evals)

    if scored_evals:
        helpful = sum(1 for s in scored_evals if float(s["score"]) >= 1.0)
        total = len(scored_evals)
        rate = helpful / total
        info["source"] = "eval_samples (feedback ratings)"
        info["helpful"] = helpful
        info["unhelpful"] = total - helpful

        if total < min_samples:
            info["low_sample_warning"] = (
                f"Only {total} draft feedback record(s) — "
                f"score unreliable until n >= {min_samples}."
            )

        return round(rate, 4), info

    # --- Fallback: drafts table status ---
    info["draft_status_row_count"] = len(draft_status_rows)

    if draft_status_rows:
        helpful = sum(
            1 for d in draft_status_rows
            if d["status"] in ("accepted", "edited")
        )
        unhelpful = sum(
            1 for d in draft_status_rows
            if d["status"] == "rejected"
        )
        total = helpful + unhelpful
        if total == 0:
            info["note"] = "No accepted/rejected/edited drafts found."
            return None, info

        rate = helpful / total
        info["source"] = "drafts table (status column)"
        info["helpful"] = helpful
        info["unhelpful"] = unhelpful

        if total < min_samples:
            info["low_sample_warning"] = (
                f"Only {total} reviewed draft(s) — "
                f"score unreliable until n >= {min_samples}."
            )

        return round(rate, 4), info

    info["note"] = "No draft feedback data found."
    return None, info


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------

PASS_COLOR = "\033[92m"   # green
FAIL_COLOR = "\033[91m"   # red
WARN_COLOR = "\033[93m"   # yellow
BOLD      = "\033[1m"
RESET     = "\033[0m"

GATE1_WEIGHTS = {
    "triage_quality":    0.40,
    "time_saved":        0.35,
    "draft_acceptance":  0.25,
}
GATE1_FLOORS = {
    "triage_quality":    0.72,
    "time_saved":        0.60,
    "draft_acceptance":  0.50,
}
COMPOSITE_FLOOR = 0.75


def _fmt_score(value: float | None, floor: float) -> str:
    if value is None:
        return f"{WARN_COLOR}N/A{RESET}"
    color = PASS_COLOR if value >= floor else FAIL_COLOR
    return f"{color}{value:.4f}{RESET}"


def _print_report(
    triage_quality: float | None,
    time_saved: float,
    draft_acceptance: float | None,
    triage_info: dict,
    draft_info: dict,
    since: datetime,
) -> None:
    print()
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  Gate 1 Composite Metric Report{RESET}")
    print(f"  Window start : {since.date()}")
    print(f"{'=' * 60}{RESET}")
    print()

    # --- Component breakdown ---
    print(f"{BOLD}Component scores{RESET}")
    print(f"  triage_quality   (floor {GATE1_FLOORS['triage_quality']})  : "
          f"{_fmt_score(triage_quality, GATE1_FLOORS['triage_quality'])}")
    print(f"  time_saved       (floor {GATE1_FLOORS['time_saved']})  : "
          f"{_fmt_score(time_saved, GATE1_FLOORS['time_saved'])}")
    print(f"  draft_acceptance (floor {GATE1_FLOORS['draft_acceptance']})  : "
          f"{_fmt_score(draft_acceptance, GATE1_FLOORS['draft_acceptance'])}")
    print()

    # --- Detail: triage ---
    print(f"{BOLD}Triage quality detail{RESET}")
    print(f"  total triage results  : {triage_info.get('total_triage_results', 'N/A')}")
    print(f"  total corrections     : {triage_info.get('total_corrections', 'N/A')}")
    print(f"  urgent AI predictions : {triage_info.get('urgent_ai_count', 'N/A')}")
    print(f"  urgent AI wrong       : {triage_info.get('urgent_ai_wrong', 'N/A')}")
    print(f"  missed urgent         : {triage_info.get('missed_urgent', 'N/A')}")
    print(f"  precision             : {triage_info.get('precision', 'N/A')}")
    print(f"  recall                : {triage_info.get('recall', 'N/A')}")
    if "low_sample_warning" in triage_info:
        print(f"  {WARN_COLOR}WARNING: {triage_info['low_sample_warning']}{RESET}")
    if "note" in triage_info:
        print(f"  {WARN_COLOR}NOTE: {triage_info['note']}{RESET}")
    if "priority_inference" in triage_info:
        print(f"  {WARN_COLOR}INFO: Priority inference mode: {triage_info['priority_inference']}{RESET}")
    print()

    # --- Detail: draft ---
    print(f"{BOLD}Draft acceptance detail{RESET}")
    print(f"  source                : {draft_info.get('source', 'N/A')}")
    print(f"  helpful               : {draft_info.get('helpful', 'N/A')}")
    print(f"  unhelpful             : {draft_info.get('unhelpful', 'N/A')}")
    print(f"  eval feedback records : {draft_info.get('eval_feedback_count', 'N/A')}")
    print(f"  draft status rows     : {draft_info.get('draft_status_row_count', 'N/A')}")
    if "low_sample_warning" in draft_info:
        print(f"  {WARN_COLOR}WARNING: {draft_info['low_sample_warning']}{RESET}")
    if "note" in draft_info:
        print(f"  {WARN_COLOR}NOTE: {draft_info['note']}{RESET}")
    print()

    # --- Composite ---
    scores = {
        "triage_quality":   triage_quality,
        "time_saved":       time_saved,
        "draft_acceptance": draft_acceptance,
    }

    missing = [k for k, v in scores.items() if v is None]
    if missing:
        print(f"{WARN_COLOR}Cannot compute composite: missing scores for: "
              f"{', '.join(missing)}{RESET}")
        print()
        _print_verdict(None, scores)
        return

    composite = sum(
        GATE1_WEIGHTS[k] * scores[k]
        for k in GATE1_WEIGHTS
    )
    composite = round(composite, 4)

    print(f"{BOLD}Composite score{RESET}")
    print(f"  0.40 * triage_quality   ({triage_quality:.4f}) = {0.40 * triage_quality:.4f}")
    print(f"  0.35 * time_saved       ({time_saved:.4f}) = {0.35 * time_saved:.4f}")
    print(f"  0.25 * draft_acceptance ({draft_acceptance:.4f}) = {0.25 * draft_acceptance:.4f}")
    print(f"  {'─' * 42}")
    composite_color = PASS_COLOR if composite >= COMPOSITE_FLOOR else FAIL_COLOR
    print(f"  {BOLD}Composite = {composite_color}{composite:.4f}{RESET}")
    print()

    _print_verdict(composite, scores)


def _print_verdict(composite: float | None, scores: dict) -> None:
    print(f"{BOLD}{'=' * 60}{RESET}")

    floor_fails = [
        k for k in GATE1_FLOORS
        if scores.get(k) is not None and scores[k] < GATE1_FLOORS[k]
    ]

    if composite is None:
        print(f"{WARN_COLOR}{BOLD}  VERDICT: INCOMPLETE — insufficient data{RESET}")
    elif composite >= COMPOSITE_FLOOR and not floor_fails:
        print(f"{PASS_COLOR}{BOLD}  VERDICT: GATE 1 PASS{RESET}")
    else:
        print(f"{FAIL_COLOR}{BOLD}  VERDICT: GATE 1 FAIL{RESET}")
        if composite is not None and composite < COMPOSITE_FLOOR:
            print(f"  Composite {composite:.4f} < required {COMPOSITE_FLOOR}")
        for k in floor_fails:
            print(f"  {k} {scores[k]:.4f} < floor {GATE1_FLOORS[k]}")

    print(f"{BOLD}{'=' * 60}{RESET}")
    print()


# ---------------------------------------------------------------------------
# Main async entry point
# ---------------------------------------------------------------------------

async def _run(args: argparse.Namespace) -> int:
    # Resolve since date
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    else:
        since = datetime.now(timezone.utc) - timedelta(days=30)

    # Validate --time-saved
    time_saved = args.time_saved
    if not 0.0 <= time_saved <= 1.0:
        print(
            f"{FAIL_COLOR}ERROR: --time-saved must be between 0.0 and 1.0, "
            f"got {time_saved}{RESET}",
            file=sys.stderr,
        )
        return 1

    # Resolve database URL — CLI flag overrides env
    db_url: str | None = args.database_url
    if db_url is None:
        db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print(
            f"{FAIL_COLOR}ERROR: DATABASE_URL not set. "
            "Pass --database-url or set DATABASE_URL in .env{RESET}",
            file=sys.stderr,
        )
        return 1

    # Build async engine and session (direct, no app.core.config dependency)
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with SessionLocal() as db:
            # --- Triage ---
            triage_rows, correction_rows = await _get_triage_with_corrections(db, since)

            # Also pull eval_samples for triage (may have model_output.priority)
            triage_eval_samples = await _get_eval_samples(db, "triage", since)
            # Merge: prefer eval_samples that have human_label AND model_output.priority
            labeled_eval = [s for s in triage_eval_samples if s["human_label"]]
            # Use labeled eval samples as corrections if they have richer data
            if labeled_eval and not any(
                c["model_output"].get("priority") for c in correction_rows
            ) and any(
                s["model_output"].get("priority") for s in labeled_eval
            ):
                correction_rows = [dict(s) for s in labeled_eval]

            triage_quality, triage_info = _compute_triage_quality(
                triage_rows, correction_rows, args.min_samples
            )

            # --- Draft ---
            draft_eval_samples = await _get_eval_samples(db, "draft", since)
            draft_status_rows = await _get_draft_rows(db, since)

            draft_acceptance, draft_info = _compute_draft_acceptance(
                draft_eval_samples, draft_status_rows, args.min_samples
            )

    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL_COLOR}ERROR: Database query failed: {exc}{RESET}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await engine.dispose()

    _print_report(
        triage_quality=triage_quality,
        time_saved=time_saved,
        draft_acceptance=draft_acceptance,
        triage_info=triage_info,
        draft_info=draft_info,
        since=since,
    )

    # Exit code: 0 = pass or incomplete, 1 = fail
    scores = {
        "triage_quality":   triage_quality,
        "time_saved":       time_saved,
        "draft_acceptance": draft_acceptance,
    }
    missing = [k for k, v in scores.items() if v is None]
    if missing:
        return 0  # incomplete data — not a hard failure

    composite = sum(GATE1_WEIGHTS[k] * scores[k] for k in GATE1_WEIGHTS)
    floor_fails = [
        k for k in GATE1_FLOORS
        if scores[k] is not None and scores[k] < GATE1_FLOORS[k]
    ]
    return 0 if (composite >= COMPOSITE_FLOOR and not floor_fails) else 1


def main() -> None:
    args = _parse_args()

    # Load .env before touching any os.environ reads
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = Path.cwd() / env_file
    _load_env_file(env_file)

    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
