from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import EvalSample


class EvalRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_sample(
        self,
        sample_type: str,
        input_hash: str,
        output_hash: str,
        model_output: dict[str, Any],
        human_label: str | None = None,
        score: float | None = None,
        model_version: str = "",
    ) -> EvalSample:
        sample = EvalSample(
            sample_type=sample_type,
            input_hash=input_hash,
            output_hash=output_hash,
            model_output=model_output,
            human_label=human_label,
            score=score,
            model_version=model_version,
        )
        self.db.add(sample)
        await self.db.commit()
        await self.db.refresh(sample)
        return sample

    async def get_triage_samples(
        self,
        since: datetime,
        with_human_label: bool = True,
    ) -> list[EvalSample]:
        q = select(EvalSample).where(
            and_(
                EvalSample.sample_type == "triage",
                EvalSample.created_at >= since,
            )
        )
        if with_human_label:
            q = q.where(EvalSample.human_label.isnot(None))
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get_draft_samples(self, since: datetime) -> list[EvalSample]:
        result = await self.db.execute(
            select(EvalSample).where(
                and_(
                    EvalSample.sample_type == "draft",
                    EvalSample.created_at >= since,
                )
            )
        )
        return list(result.scalars().all())
