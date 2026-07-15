#!/usr/bin/env python3
"""Validate and fingerprint the production i.MX952 boot artifact set.

This tool does not claim Boot ROM equivalence. It creates the immutable artifact identity
required before hardware and digital-twin boot traces can be compared meaningfully.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_manifest(manifest: Dict[str, Any], root: Path) -> Dict[str, Any]:
    errors: List[str] = []
    resolved: List[Dict[str, Any]] = []

    target = manifest.get("target", {})
    if target.get("soc") != "i.MX952":
        errors.append("manifest target.soc must be i.MX952")
    if not target.get("revision"):
        errors.append("manifest target.revision is required")
    if manifest.get("container_version") is None:
        errors.append("container_version is required")

    for artifact in manifest.get("artifacts", []):
        name = artifact.get("name")
        relative = artifact.get("path")
        required = bool(artifact.get("required", True))
        if not name or not relative:
            errors.append("every artifact requires name and path")
            continue

        path = (root / relative).resolve()
        record: Dict[str, Any] = {
            "name": name,
            "path": str(path),
            "required": required,
            "exists": path.is_file(),
        }

        if not path.is_file():
            if required:
                errors.append(f"required artifact missing: {name} ({relative})")
            resolved.append(record)
            continue

        size = path.stat().st_size
        digest = sha256_file(path)
        record["size_bytes"] = size
        record["sha256"] = digest
        if size == 0:
            errors.append(f"artifact is empty: {name}")

        expected_hash = str(artifact.get("sha256") or "").lower()
        if expected_hash and expected_hash != digest:
            errors.append(f"SHA-256 mismatch for {name}")

        resolved.append(record)

    return {
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "target": target,
        "container_version": manifest.get("container_version"),
        "artifacts": resolved,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = validate_manifest(manifest, args.root)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
