from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.ingestion.normalizer import NormalizedMessage
    from app.agents.triage_agent import TriageAgentOutput
    from app.agents.draft_agent import DraftAgentOutput

from app.telemetry.events import _sha256


class EvalHarness:
    """Records agent samples for offline eval and computes running metrics."""

    async def record_triage_sample(
        self,
        input: "NormalizedMessage",
        output: "TriageAgentOutput",
        human_label: str | None = None,
        db=None,
    ) -> None:
        if db is None:
            return
        from app.repositories.eval_repo import EvalRepository
        repo = EvalRepository(db)
        await repo.create_sample(
            sample_type="triage",
            input_hash=_sha256({"message_id": input.message_id, "subject": input.subject}),
            output_hash=_sha256({"priority": output.priority, "confidence": output.confidence}),
            model_output={
                "priority": output.priority,
                "confidence": output.confidence,
                "rationale": output.rationale,
            },
            human_label=human_label,
        )

    async def record_draft_sample(
        self,
        input: dict[str, Any],
        output: "DraftAgentOutput",
        accepted: bool | None = None,
        db=None,
    ) -> None:
        if db is None:
            return
        from app.repositories.eval_repo import EvalRepository
        repo = EvalRepository(db)
        score = 1.0 if accepted is True else (0.0 if accepted is False else None)
        await repo.create_sample(
            sample_type="draft",
            input_hash=_sha256(input),
            output_hash=_sha256({"body": output.draft_body[:100]}),
            model_output={"confidence": output.confidence},
            score=score,
        )

    async def compute_triage_metrics(self, since: datetime, db=None) -> dict:
        """Return precision, recall, f1 for labeled triage samples since `since`."""
        if db is None:
            return {}
        from app.repositories.eval_repo import EvalRepository
        repo = EvalRepository(db)
        samples = await repo.get_triage_samples(since, with_human_label=True)
        if not samples:
            return {"precision": None, "recall": None, "f1": None, "sample_count": 0}

        # Binary: "urgent" = positive class
        tp = sum(
            1 for s in samples
            if s.model_output.get("priority") == "urgent" and s.human_label == "urgent"
        )
        fp = sum(
            1 for s in samples
            if s.model_output.get("priority") == "urgent" and s.human_label != "urgent"
        )
        fn = sum(
            1 for s in samples
            if s.model_output.get("priority") != "urgent" and s.human_label == "urgent"
        )

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "sample_count": len(samples),
        }

    async def compute_draft_acceptance_rate(self, since: datetime, db=None) -> float:
        """Return fraction of drafts accepted (score=1.0) since `since`."""
        if db is None:
            return 0.0
        from app.repositories.eval_repo import EvalRepository
        repo = EvalRepository(db)
        samples = await repo.get_draft_samples(since)
        scored = [s for s in samples if s.score is not None]
        if not scored:
            return 0.0
        return sum(s.score for s in scored) / len(scored)
