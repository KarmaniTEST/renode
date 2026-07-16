#!/usr/bin/env python3
"""Validate execution-capable hybrid backends for missing i.MX952 blocks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List

PINNED_TARGET = {"soc": "i.MX952", "revision": "B0", "board": "i.MX952 EVK"}
EXPECTED_SUBSYSTEMS = {"gic_its_msi", "netc", "usb", "pcie_hsio", "gpu", "npu"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _integer(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError("integer value required")


def _validate_file(record: Dict[str, Any], root: Path, label: str, errors: List[str]):
    if not isinstance(record, dict):
        errors.append(f"{label}: file record is missing")
        return None
    relative = record.get("path")
    expected = str(record.get("sha256") or "").lower()
    if not relative:
        errors.append(f"{label}: path is missing")
        return None
    if not SHA256_RE.fullmatch(expected):
        errors.append(f"{label}: SHA-256 is missing or invalid")
    path = (root / relative).resolve()
    if not path.is_file():
        errors.append(f"{label}: file is missing: {relative}")
        return None
    actual = sha256_file(path)
    if expected and actual != expected:
        errors.append(f"{label}: SHA-256 mismatch")
    return {"path": str(path), "sha256": actual, "size_bytes": path.stat().st_size}


def validate_manifest(manifest: Dict[str, Any], root: Path, mode: str) -> Dict[str, Any]:
    errors: List[str] = []
    results: Dict[str, Any] = {}

    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if manifest.get("target") != PINNED_TARGET:
        errors.append("target identity differs from i.MX952 EVK B0")
    evidence_class = manifest.get("evidence_class", "production")
    accepted = set(manifest.get("accepted_backend_kinds", []))
    subsystems = manifest.get("subsystems", {})
    if set(subsystems) != EXPECTED_SUBSYSTEMS:
        errors.append("subsystem inventory differs from the six mandatory backend blocks")

    evidence_contract = manifest.get("physical_evidence_contract", {})
    identity_fields = evidence_contract.get("identity_fields", [])
    file_fields = evidence_contract.get("file_fields", [])
    physical_fields = evidence_contract.get("required_fields", [])

    for name in sorted(EXPECTED_SUBSYSTEMS):
        entry = subsystems.get(name, {})
        item_errors: List[str] = []
        if not entry.get("enabled"):
            item_errors.append("backend is disabled")

        kind = entry.get("backend_kind")
        if kind not in accepted:
            item_errors.append("backend kind is missing or not accepted")

        source = entry.get("source", {})
        if not source.get("repository"):
            item_errors.append("source repository is missing")
        if not COMMIT_RE.fullmatch(str(source.get("commit") or "").lower()):
            item_errors.append("immutable 40-character source commit is missing")

        artifact_result = _validate_file(
            entry.get("artifact", {}), root, f"{name} artifact", item_errors
        )

        mandatory = set(entry.get("mandatory_capabilities", []))
        provided = set(entry.get("provided_capabilities", []))
        if not mandatory:
            item_errors.append("mandatory capability contract is empty")
        missing_capabilities = sorted(mandatory - provided)
        unknown_capabilities = sorted(provided - mandatory)
        if missing_capabilities:
            item_errors.append(f"mandatory capabilities missing: {missing_capabilities}")
        if unknown_capabilities:
            item_errors.append(f"uncontracted capabilities declared: {unknown_capabilities}")

        ranges = entry.get("mmio_ranges", [])
        parsed_ranges = []
        if not ranges:
            item_errors.append("MMIO ranges are missing")
        for index, region in enumerate(ranges):
            try:
                base = _integer(region.get("base"))
                size = _integer(region.get("size"))
                if base < 0 or size <= 0:
                    raise ValueError()
                parsed_ranges.append((base, base + size, index))
            except (AttributeError, TypeError, ValueError):
                item_errors.append(f"MMIO range {index} is invalid")
        parsed_ranges.sort()
        for previous, current in zip(parsed_ranges, parsed_ranges[1:]):
            if current[0] < previous[1]:
                item_errors.append(f"MMIO ranges overlap: {previous[2]} and {current[2]}")

        routes = entry.get("interrupt_routes", [])
        if not routes:
            item_errors.append("interrupt routes are missing")
        for index, route in enumerate(routes):
            if not isinstance(route, dict) or not route.get("source") or not route.get("target"):
                item_errors.append(f"interrupt route {index} is invalid")

        test_results = []
        tests = entry.get("deterministic_tests", [])
        if not tests:
            item_errors.append("deterministic tests are missing")
        for index, test in enumerate(tests):
            if not isinstance(test, dict) or not test.get("name"):
                item_errors.append(f"deterministic test {index} has no name")
                continue
            file_result = _validate_file(
                test, root, f"{name} test {test.get('name')}", item_errors
            )
            if file_result:
                file_result["name"] = test["name"]
                test_results.append(file_result)

        physical_results = {}
        physical = entry.get("physical_evidence")
        if mode == "full-physical":
            if evidence_class != "production":
                item_errors.append("synthetic evidence cannot satisfy full-physical mode")
            if not isinstance(physical, dict):
                item_errors.append("physical evidence is missing")
            else:
                for field in identity_fields:
                    value = physical.get(field)
                    if not isinstance(value, dict) or not value:
                        item_errors.append(f"physical identity missing: {field}")
                for field in file_fields:
                    result = _validate_file(
                        physical.get(field), root,
                        f"{name} physical evidence {field}", item_errors
                    )
                    if result:
                        physical_results[field] = result
                for field in physical_fields:
                    if field not in physical or physical[field] in (None, "", {}):
                        item_errors.append(f"physical evidence field missing: {field}")
                if physical.get("comparison_result") != "PASS":
                    item_errors.append("physical comparison result is not PASS")
                tolerances = physical.get("timing_tolerances")
                if not isinstance(tolerances, dict) or not tolerances:
                    item_errors.append("timing tolerances are missing")

        results[name] = {
            "verdict": "READY" if not item_errors else "BLOCKED",
            "backend_kind": kind,
            "source": source,
            "artifact": artifact_result,
            "mandatory_capability_count": len(mandatory),
            "provided_capability_count": len(provided),
            "tests": test_results,
            "physical_evidence_files": physical_results,
            "errors": item_errors,
        }
        errors.extend(f"{name}: {message}" for message in item_errors)

    ready = not errors
    return {
        "verdict": "READY" if ready else "BLOCKED",
        "mode": mode,
        "evidence_class": evidence_class,
        "target": manifest.get("target"),
        "subsystems": results,
        "errors": errors,
        "claim_boundary": [
            "Functional readiness proves declared executable backend capabilities and immutable artifacts only.",
            "Synthetic fixtures validate this gate but are not subsystem evidence.",
            "Full physical readiness verifies immutable EVK evidence files, PASS differential results and timing tolerances for every subsystem."
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--mode", choices=("functional", "full-physical"), default="functional")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = validate_manifest(manifest, args.root, args.mode)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
