#!/usr/bin/env python3
"""Fail-closed production boot artifact readiness gate for i.MX952 EVK B0."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from parse_imx95_container_v2 import inspect_file
from validate_boot_artifacts import validate_manifest

PINNED_MKIMAGE_COMMIT = "1b577853ae1afe1f26cdef27548da52fb424af48"
PINNED_TARGET = {"soc": "i.MX952", "revision": "B0", "board": "i.MX952 EVK"}


def validate_readiness(manifest: Dict[str, Any], root: Path) -> Dict[str, Any]:
    identity = validate_manifest(manifest, root)
    errors: List[str] = list(identity.get("errors", []))
    containers: List[Dict[str, Any]] = []

    if manifest.get("target") != PINNED_TARGET:
        errors.append("target identity differs from pinned i.MX952 EVK B0")
    if manifest.get("container_version") != 2:
        errors.append("container_version must be 2")
    if manifest.get("source_baseline", {}).get("imx_mkimage_commit") != PINNED_MKIMAGE_COMMIT:
        errors.append("imx-mkimage source commit differs from pinned baseline")

    required_hashes_ready = True
    for artifact in manifest.get("artifacts", []):
        if not artifact.get("required", True):
            continue
        name = artifact.get("name", "unnamed")
        expected_hash = str(artifact.get("sha256") or "").lower()
        if not expected_hash:
            required_hashes_ready = False
            errors.append(f"required artifact hash is not pinned: {name}")

    for artifact in manifest.get("artifacts", []):
        rule = artifact.get("container_validation")
        if not rule:
            continue
        path = (root / artifact["path"]).resolve()
        if not path.is_file():
            continue
        offsets = rule.get("offsets")
        parsed_offsets = None
        if offsets:
            parsed_offsets = [int(value, 0) if isinstance(value, str) else int(value)
                              for value in offsets]
        report = inspect_file(path, parsed_offsets, rule.get("required_stages", []))
        containers.append({"artifact": artifact["name"], "report": report})
        if report["verdict"] != "PASS":
            errors.append(f"container validation failed: {artifact['name']}")

    if not containers:
        errors.append("manifest does not define any container_validation rules")

    ready = (
        identity.get("verdict") == "PASS"
        and required_hashes_ready
        and containers
        and all(item["report"]["verdict"] == "PASS" for item in containers)
        and not errors
    )
    return {
        "verdict": "PASS" if ready else "BLOCKED",
        "execution_readiness": "READY_FOR_EXECUTION" if ready else "BLOCKED",
        "target": manifest.get("target"),
        "artifact_identity": identity,
        "container_validations": containers,
        "errors": errors,
        "qualification_boundary": [
            "READY_FOR_EXECUTION proves pinned artifact hashes and container structure/hash/stage presence.",
            "It does not prove signature authentication, Boot ROM, ELE, OEI, DDR training, ATF or U-Boot execution.",
            "Runtime and physical-board evidence remain mandatory for production-boot or physical-equivalence claims."
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = validate_readiness(manifest, args.root)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
