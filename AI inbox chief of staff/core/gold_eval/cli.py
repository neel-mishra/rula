"""argparse CLI for gold-eval operations.

Subcommands:
    extract      — trigger sample extraction (no-op until connectors live)
    list         — list samples (filter by type / unlabeled)
    label        — interactive labeler for a single sample
    version-cut  — snapshot is_active samples into a new dataset version
    version-activate — flip is_latest on a tag

Run with `python -m core.gold_eval.cli <subcommand> ...`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from core.config import settings
from core.db import get_db_session
from core.models.gold_sample import (
    GoldDatasetVersion,
    GoldFixtureType,
    GoldSample,
    GoldSampleLabel,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _emit(obj: Any) -> None:
    print(json.dumps(obj, default=str, indent=2))


async def _list_samples(
    fixture_type: str | None,
    unlabeled: bool,
    limit: int,
) -> list[dict[str, Any]]:
    async with get_db_session() as session:
        q = select(GoldSample).where(GoldSample.is_active.is_(True))
        if fixture_type:
            q = q.where(GoldSample.fixture_type == GoldFixtureType(fixture_type))
        q = q.order_by(GoldSample.created_at.desc()).limit(limit)
        rows = (await session.execute(q)).scalars().all()
        out = []
        for r in rows:
            label_count_q = await session.execute(
                select(GoldSampleLabel).where(GoldSampleLabel.gold_sample_id == r.id)
            )
            labels = label_count_q.scalars().all()
            if unlabeled and labels:
                continue
            out.append(
                {
                    "id": str(r.id),
                    "fixture_type": r.fixture_type.value,
                    "stratum": r.stratum.value,
                    "label_count": len(labels),
                    "subject_preview": (r.scrubbed_payload or {}).get("subject", "")[:80],
                }
            )
        return out


# ── Subcommand handlers ────────────────────────────────────────────────────


def cmd_extract(args: argparse.Namespace) -> int:
    if not settings.gold_sampling_enabled:
        _emit(
            {
                "status": "deferred",
                "reason": "gold_sampling_enabled=False; activate after Gmail OAuth + connectors land",
                "mailbox_id": args.mailbox_id,
            }
        )
        return 0
    # Real call: dispatch to the worker. Kept light here since the
    # worker holds the Gmail-read code path.
    from workers.gold_sample_extraction import extract_gold_samples

    result = asyncio.run(
        extract_gold_samples(
            mailbox_id=uuid.UUID(args.mailbox_id),
            dry_run=args.dry_run,
        )
    )
    _emit(result)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = asyncio.run(_list_samples(args.fixture_type, args.unlabeled, args.limit))
    _emit(rows)
    return 0


def cmd_label(args: argparse.Namespace) -> int:
    return asyncio.run(_label_one(args))


async def _label_one(args: argparse.Namespace) -> int:
    sample_id = uuid.UUID(args.sample_id)
    async with get_db_session() as session:
        sample = await session.get(GoldSample, sample_id)
        if not sample:
            print(f"Sample {sample_id} not found", file=sys.stderr)
            return 1
        print(json.dumps(sample.scrubbed_payload, indent=2, default=str))
        print(f"\nLabeling for fixture_type={sample.fixture_type.value}")

        prompts = _LABEL_PROMPTS.get(sample.fixture_type, [])
        labels: dict[str, Any] = {}
        for field, prompt, parser in prompts:
            raw = input(f"{prompt}: ").strip()
            try:
                labels[field] = parser(raw) if parser else raw
            except Exception as exc:
                print(f"  bad input ({exc}); skipping {field}", file=sys.stderr)

        rationale = input("Rationale (optional): ").strip()
        labeler_id = uuid.UUID(args.labeler_id) if args.labeler_id else None

        row = GoldSampleLabel(
            id=uuid.uuid4(),
            gold_sample_id=sample.id,
            label_type=sample.fixture_type.value,
            labeled_by_user_id=labeler_id,
            labels=labels,
            rationale=rationale or None,
        )
        session.add(row)
        await session.flush()
        _emit({"label_id": str(row.id), "labels": labels})
        return 0


def _parse_csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


_LABEL_PROMPTS: dict[GoldFixtureType, list[tuple[str, str, Any]]] = {
    GoldFixtureType.TRIAGE: [
        ("outcome", "Expected outcome (inbox|archive|brief|spam)", None),
        ("rule", "Matching rule name (or 'llm')", None),
    ],
    GoldFixtureType.DRAFT: [
        ("grounding_spans", "Grounding span sentence indices, comma-separated", _parse_csv),
        ("acceptable_variants", "Acceptable phrasing variants, comma-separated", _parse_csv),
        ("hallucination_sentinels", "Phrases that disqualify (csv)", _parse_csv),
    ],
    GoldFixtureType.BRIEF: [
        ("category", "Brief category", None),
        ("should_include", "Should include in brief? (y/n)", lambda s: s.lower().startswith("y")),
        ("summary", "One-line summary", None),
    ],
    GoldFixtureType.MEMORY: [
        ("extractable_rule", "Extractable rule? (y/n)", lambda s: s.lower().startswith("y")),
        ("expected_scope", "Expected scope (mailbox_specific|user_global)", None),
    ],
    GoldFixtureType.SAFETY: [
        ("injection_vector", "Injection vector? (y/n)", lambda s: s.lower().startswith("y")),
        ("expected_block_reason", "Expected block reason (or 'none')", None),
    ],
}


async def _cut_version(args: argparse.Namespace) -> int:
    async with get_db_session() as session:
        active_q = await session.execute(
            select(GoldSample.id).where(GoldSample.is_active.is_(True))
        )
        ids = [str(row[0]) for row in active_q.all()]
        version = GoldDatasetVersion(
            id=uuid.uuid4(),
            tag=args.tag,
            notes=args.notes,
            is_latest=False,
            sample_ids=ids,
        )
        session.add(version)
        await session.flush()
        _emit({"id": str(version.id), "tag": version.tag, "samples": len(ids)})
        return 0


async def _activate_version(args: argparse.Namespace) -> int:
    async with get_db_session() as session:
        await session.execute(update(GoldDatasetVersion).values(is_latest=False))
        target = await session.execute(
            select(GoldDatasetVersion).where(GoldDatasetVersion.tag == args.tag)
        )
        row = target.scalar_one_or_none()
        if not row:
            print(f"Tag {args.tag} not found", file=sys.stderr)
            return 1
        row.is_latest = True
        await session.flush()
        _emit({"tag": row.tag, "is_latest": True, "samples": len(row.sample_ids)})
        return 0


def cmd_version_cut(args: argparse.Namespace) -> int:
    return asyncio.run(_cut_version(args))


def cmd_version_activate(args: argparse.Namespace) -> int:
    return asyncio.run(_activate_version(args))


# ── Entrypoint ─────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gold-eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser("extract", help="Trigger sample extraction")
    p_extract.add_argument("--mailbox-id", required=True)
    p_extract.add_argument("--dry-run", action="store_true", default=True)
    p_extract.set_defaults(func=cmd_extract)

    p_list = sub.add_parser("list", help="List samples")
    p_list.add_argument("--fixture-type", default=None)
    p_list.add_argument("--unlabeled", action="store_true")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=cmd_list)

    p_label = sub.add_parser("label", help="Label one sample")
    p_label.add_argument("--sample-id", required=True)
    p_label.add_argument("--labeler-id", default=None)
    p_label.set_defaults(func=cmd_label)

    p_cut = sub.add_parser("version-cut", help="Snapshot is_active samples into a new version tag")
    p_cut.add_argument("--tag", required=True)
    p_cut.add_argument("--notes", default="")
    p_cut.set_defaults(func=cmd_version_cut)

    p_act = sub.add_parser("version-activate", help="Flip is_latest on a tag")
    p_act.add_argument("--tag", required=True)
    p_act.set_defaults(func=cmd_version_activate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
