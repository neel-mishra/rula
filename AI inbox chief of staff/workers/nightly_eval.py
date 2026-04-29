"""
Nightly evaluation pipeline — runs EvalAgent across all active mailboxes.
Evaluates triage accuracy, draft quality, style conformance, and safety.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from core.db import get_db_session
from core.models.mailbox import Mailbox

log = structlog.get_logger(__name__)


async def run_nightly_evals() -> dict:
    """Run evaluation suite across all active mailboxes."""
    from subagents.eval import EvalAgent, EvalTask

    results = {"mailboxes_evaluated": 0, "evals_run": 0, "failures": 0, "reports": []}
    eval_types = ["triage", "draft_quality", "style_conformance", "safety"]

    async with get_db_session() as session:
        mailboxes_result = await session.execute(
            select(Mailbox).where(
                Mailbox.is_active == True,  # noqa: E712
                Mailbox.is_connected == True,  # noqa: E712
            )
        )
        mailboxes = mailboxes_result.scalars().all()

    agent = EvalAgent()

    for mailbox in mailboxes:
        mailbox_report = {"mailbox_id": str(mailbox.id), "evals": {}}

        for eval_type in eval_types:
            try:
                task = EvalTask(
                    user_id=mailbox.user_id,
                    mailbox_id=mailbox.id,
                    correlation_id=str(uuid.uuid4()),
                    eval_type=eval_type,
                    time_window_hours=24,
                    sample_limit=100,
                )
                response = await agent.run(task)

                if response.ok and response.payload:
                    payload = response.payload
                    mailbox_report["evals"][eval_type] = {
                        "passed": payload.passed,
                        "pass_rate": payload.pass_rate,
                        "fail_count": payload.fail_count,
                        "total": payload.total_evaluated,
                    }
                    if not payload.passed:
                        log.warning(
                            "nightly_eval.threshold_breach",
                            mailbox_id=str(mailbox.id),
                            eval_type=eval_type,
                            pass_rate=payload.pass_rate,
                            threshold=payload.threshold,
                        )
                else:
                    mailbox_report["evals"][eval_type] = {"error": str(response.error)}
                    results["failures"] += 1

                results["evals_run"] += 1

            except Exception as exc:
                results["failures"] += 1
                mailbox_report["evals"][eval_type] = {"error": str(exc)}
                log.error(
                    "nightly_eval.failed",
                    mailbox_id=str(mailbox.id),
                    eval_type=eval_type,
                    error=str(exc),
                )

        # Gold-eval pass — feature-flagged off until connectors land.
        from core.config import settings as _settings
        if _settings.gold_eval_enabled:
            try:
                from core.gold_eval.adapter import run_all_gold_evals
                gold_reports = await run_all_gold_evals(
                    user_id=mailbox.user_id, mailbox_id=mailbox.id
                )
                mailbox_report["gold_evals"] = [
                    {
                        "eval_type": g.eval_type,
                        "passed": g.passed,
                        "pass_rate": g.pass_rate,
                        "fail_count": g.fail_count,
                        "total": g.total_evaluated,
                    }
                    for g in gold_reports
                ]
            except Exception as exc:
                log.error(
                    "nightly_eval.gold_failed",
                    mailbox_id=str(mailbox.id),
                    error=str(exc),
                )

        results["mailboxes_evaluated"] += 1
        results["reports"].append(mailbox_report)

    log.info(
        "nightly_eval.complete",
        mailboxes=results["mailboxes_evaluated"],
        evals=results["evals_run"],
        failures=results["failures"],
    )
    return results
