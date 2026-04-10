"""Shared lineage / evidence vocabulary for exports and future ingest (GAP-X1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LineageExportBlock(BaseModel):
    """Optional block appended to CRM exports when lineage is enabled."""

    schema_version: str = "1.0"

    @field_validator("schema_version")
    @classmethod
    def _check_lineage_schema(cls, v: str) -> str:
        from src.integrations.contract_compat import require_lineage_schema

        require_lineage_schema(v, component="lineage_export")
        return v
    correlation_id: str | None = None
    prospecting_run_id: str | None = None
    map_run_id: str | None = None
    evidence_id: str | None = None
    source_type: str | None = None
    captured_at: str | None = None  # ISO-8601 UTC

    def to_dict_omit_none(self) -> dict[str, Any]:
        d = self.model_dump()
        return {k: v for k, v in d.items() if v is not None}


class CommitmentEvidenceArtifact(BaseModel):
    """Canonical commitment evidence shape for future HTTP ingest; fields align with docs/ingest_contract.md."""

    evidence_id: str
    source_type: str
    raw_text: str
    raw_ref: str | None = None
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    prospecting_run_id: str | None = None
    schema_version: str = "1.0"

    @field_validator("schema_version")
    @classmethod
    def _check_ingest_schema(cls, v: str) -> str:
        from src.integrations.contract_compat import require_ingest_schema

        require_ingest_schema(v, component="commitment_evidence")
        return v
