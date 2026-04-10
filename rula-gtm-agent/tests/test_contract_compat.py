from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.integrations.contract_compat import (
    ContractVersionError,
    require_export_contract,
    validate_lineage_export_dict,
)
from src.integrations.ingestion import validate_commitment_ingest_dict
from src.schemas.evidence_artifact import CommitmentEvidenceArtifact, LineageExportBlock


def test_lineage_rejects_unknown_schema() -> None:
    with pytest.raises(ValidationError, match="unsupported lineage"):
        LineageExportBlock(schema_version="99.0")


def test_ingest_rejects_unknown_schema() -> None:
    with pytest.raises(ValidationError, match="unsupported ingest"):
        CommitmentEvidenceArtifact(
            evidence_id="e1",
            source_type="email",
            raw_text="x",
            schema_version="2.0",
        )


def test_validate_lineage_dict() -> None:
    validate_lineage_export_dict({"schema_version": "1.0", "correlation_id": "c"})
    with pytest.raises(ContractVersionError):
        validate_lineage_export_dict({"schema_version": "0.0"})


def test_validate_commitment_ingest_dict() -> None:
    validate_commitment_ingest_dict({"schema_version": "1.0"})
    with pytest.raises(ContractVersionError):
        validate_commitment_ingest_dict({"schema_version": "bad"})


def test_require_export_contract() -> None:
    require_export_contract(None)
    require_export_contract("1")
    with pytest.raises(ContractVersionError):
        require_export_contract("99")
