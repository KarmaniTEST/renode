#!/usr/bin/env python3
"""Release gate for the i.MX952 digital twin.

The gate is intentionally strict. It distinguishes a qualified functional engineering
release from a full physical-equivalence release. Full physical equivalence is refused
unless every mandatory subsystem is explicitly marked FULL_EQUIVALENCE and a hardware
reference comparison report passes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent

MANDATORY_FULL_EQUIVALENCE = [
    "cpu_execution",
    "boot_rom",
    "ele",
    "system_manager",
    "gic_its_msi",
    "netc",
    "usb",
    "pcie_hsio",
    "gpu",
    "npu",
    "timing",
]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def find_status_entry(document: Dict[str, Any], name: str) -> Dict[str, Any] | None:
    candidates = document.get("subsystems", [])
    if isinstance(candidates, dict):
        value = candidates.get(name)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"status": value}
        return None
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        key = entry.get("id") or entry.get("name") or entry.get("subsystem")
        if key == name:
            return entry
    return None


def run_unit_tests() -> None:
    tests_dir = ROOT / "tests"
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(tests_dir),
        "-p",
        "test_*.py",
        "-v",
    ]
    subprocess.run(command, check=True)


def validate_baseline(baseline: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    target = baseline.get("target", {})
    for key in ("soc", "revision", "board"):
        if not target.get(key):
            errors.append(f"authoritative baseline is missing target.{key}")
    if not baseline.get("authoritative_sources"):
        errors.append("authoritative baseline has no pinned sources")
    return errors


def validate_full_status(status: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for subsystem in MANDATORY_FULL_EQUIVALENCE:
        entry = find_status_entry(status, subsystem)
        if entry is None:
            errors.append(f"missing mandatory subsystem status: {subsystem}")
            continue
        maturity = str(entry.get("status") or entry.get("maturity") or "").upper()
        if maturity != "FULL_EQUIVALENCE":
            errors.append(f"{subsystem}: {maturity or 'UNKNOWN'} != FULL_EQUIVALENCE")
    return errors


def validate_report(report: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if report.get("verdict") != "PASS":
        errors.append("hardware-vs-twin comparison verdict is not PASS")
    if report.get("target_mismatches"):
        errors.append("hardware-vs-twin comparison contains target mismatches")
    summary = report.get("summary", {})
    if summary.get("required_failed", 0) != 0:
        errors.append("hardware-vs-twin comparison has required failures")
    return errors


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("engineering", "full-physical"),
        default="engineering",
        help="engineering validates the open-source professional package; full-physical also requires complete hardware-correlated equivalence",
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=ROOT / "EQUIVALENCE_STATUS.json",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=ROOT / "AUTHORITATIVE_BASELINE.json",
    )
    parser.add_argument(
        "--comparison-report",
        type=Path,
        help="required for --mode full-physical",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="skip unit tests; intended only when tests already ran in the same CI job",
    )
    args = parser.parse_args(argv)

    errors: List[str] = []
    baseline = load_json(args.baseline)
    status = load_json(args.status)
    errors.extend(validate_baseline(baseline))

    if not args.skip_tests:
        try:
            run_unit_tests()
        except subprocess.CalledProcessError as exc:
            errors.append(f"equivalence framework tests failed with exit code {exc.returncode}")

    if args.mode == "full-physical":
        errors.extend(validate_full_status(status))
        if args.comparison_report is None:
            errors.append("--comparison-report is required for full-physical qualification")
        elif not args.comparison_report.exists():
            errors.append(f"comparison report not found: {args.comparison_report}")
        else:
            errors.extend(validate_report(load_json(args.comparison_report)))

    result = {
        "mode": args.mode,
        "verdict": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "target": baseline.get("target", {}),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
