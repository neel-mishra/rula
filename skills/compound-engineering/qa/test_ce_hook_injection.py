#!/usr/bin/env python3
"""
QA harness for `.cursor/hooks/inject-compound-engineering-pretool.py`.

Runs the hook as a subprocess (same as Cursor preToolUse) and asserts:
- CE heading is injected when missing
- Inferred domain matches architecture keywords (or explicit domain: override)
- Pass-through when CE already present or path is not a plan target

Usage (from repo root):
  python3 skills/compound-engineering/qa/test_ce_hook_injection.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".cursor" / "hooks" / "inject-compound-engineering-pretool.py"

CE = "## Compound Engineering"


def run_hook(payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"hook exit {proc.returncode} stderr={proc.stderr!r}")
    return json.loads(proc.stdout)


def assert_in(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: expected {needle!r} in:\n{text[:2000]}")


def main() -> int:
    if not HOOK.is_file():
        print(f"Missing hook at {HOOK}", file=sys.stderr)
        return 2

    cases: list[tuple[str, dict, callable]] = []

    def cp(name: str, overview: str, plan: str, agent: str, expect_domain: str) -> None:
        payload = {
            "tool_name": "CreatePlan",
            "tool_input": {"name": name, "overview": overview, "plan": plan},
            "agent_message": agent,
        }

        def check(out: dict, _e=expect_domain) -> None:
            plan_out = out.get("updated_input", {}).get("plan", "")
            assert_in(plan_out, CE, "CreatePlan CE")
            assert_in(plan_out, f"**Inferred domain:** `{_e}`", "CreatePlan domain")

        cases.append((f"CreatePlan:{expect_domain}", payload, check))

    def wr(path: str, contents: str, agent: str, expect_domain: str) -> None:
        payload = {
            "tool_name": "Write",
            "tool_input": {"path": path, "contents": contents},
            "agent_message": agent,
        }

        def check(out: dict, _e=expect_domain) -> None:
            c = out.get("updated_input", {}).get("contents", "")
            assert_in(c, CE, "Write CE")
            assert_in(c, f"**Inferred domain:** `{_e}`", "Write domain")

        cases.append((f"Write:{expect_domain}", payload, check))

    def ap(patch: str, agent: str, expect_domain: str) -> None:
        payload = {"tool_name": "ApplyPatch", "tool_input": patch, "agent_message": agent}

        def check(out: dict, _e=expect_domain) -> None:
            ui = out.get("updated_input")
            text = ui if isinstance(ui, str) else (ui or {}).get("patch", "")
            assert_in(text, CE, "ApplyPatch CE")
            assert_in(text, f"**Inferred domain:** `{_e}`", "ApplyPatch domain")

        cases.append((f"ApplyPatch:{expect_domain}", payload, check))

    # --- Architecture scenarios (keyword → domain) ---
    cp("Zero-trust API", "RBAC and token claims", "# Plan\nShip OAuth2.", "", "security")
    cp("Ledger pipeline", "Schema validation and migration", "# Plan\nVersion tables.", "", "data-integrity")
    # Avoid "slo" in the name — it maps to reliability before observability in keyword order.
    cp("Telemetry platform", "Metrics, logs, tracing", "# Plan\nDashboards.", "", "observability")
    cp("Rollout", "Canary and feature flags", "# Plan\nGo-live.", "", "release-management")
    cp("Resilience", "Error budget and incident response", "# Plan\nRollback.", "", "reliability")
    cp("Importer", "Ingest and normalize source data", "# Plan\nParse input.", "", "ingestion")
    cp("Connectors", "Downstream export handoff", "# Plan\nPayload delivery.", "", "output-handoff")
    cp("Compliance", "Retention and audit trail policy", "# Plan\nTriage.", "", "governance")

    wr(
        ".cursor/plans/qa-security.plan.md",
        "# Write plan\nImplement authorization.",
        "secrets and permissions",
        "security",
    )

    ap(
        "*** Begin Patch\n"
        "*** Add File: .cursor/plans/qa-patch.plan.md\n"
        "+# Patch plan\n"
        "+Add telemetry and alerts for the service.\n"
        "*** End Patch\n",
        "",
        "observability",
    )

    ap(
        "*** Begin Patch\n"
        "*** Update File: .cursor/plans/existing.plan.md\n"
        "@@\n"
        " # Existing\n"
        "+# tweak\n"
        "*** End Patch\n",
        "deploy rollout",
        "release-management",
    )

    # Explicit domain overrides noisy corpus
    cp("Mixed", "auth tokens everywhere", "# Plan\n", "domain:data-integrity also schema work", "data-integrity")

    # Pass-through: CE already in plan
    def check_no_inject(out: dict) -> None:
        if "updated_input" in out:
            raise AssertionError(f"expected no updated_input, got keys {out.keys()}")

    cases.append(
        (
            "CreatePlan:already_has_CE",
            {
                "tool_name": "CreatePlan",
                "tool_input": {
                    "name": "X",
                    "overview": "y",
                    "plan": f"# P\n\n{CE}\n\ndone.\n",
                },
                "agent_message": "",
            },
            check_no_inject,
        )
    )

    # Pass-through: non-plan write
    cases.append(
        (
            "Write:non_plan",
            {
                "tool_name": "Write",
                "tool_input": {"path": "src/app.ts", "contents": "// no ce"},
                "agent_message": "auth",
            },
            check_no_inject,
        )
    )

    failed = 0
    for label, payload, check in cases:
        try:
            out = run_hook(payload)
            if out.get("permission") != "allow":
                raise AssertionError(f"permission={out.get('permission')!r}")
            check(out)
            print(f"PASS  {label}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {label}: {e}")

    if failed:
        print(f"\n{failed} case(s) failed.", file=sys.stderr)
        return 1
    print(f"\nAll {len(cases)} cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
