#!/usr/bin/env python3
"""Generate a verified, halted post-authentication ATF/U-Boot Renode plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from validate_boot_readiness import validate_readiness

REQUIRED_STAGES = ("ATF", "U_BOOT")
DEFAULT_PLATFORM = "platforms/boards/nxp_imx952_evk_full.repl"
A55_CPUS = tuple(f"sysbus.a55_{index}" for index in range(4))


def _one(items, message):
    if len(items) != 1:
        raise ValueError(f"{message}: found {len(items)}")
    return items[0]


def _stage(report: Dict[str, Any], name: str):
    image = _one([
        image for container in report.get("containers", [])
        for image in container.get("images", []) if name in image.get("stages", [])
    ], f"expected exactly one {name} image")
    if not image.get("hash_match") or image.get("errors"):
        raise ValueError(f"{name} image did not pass descriptor hash validation")
    return image


def generate_plan(manifest: Dict[str, Any], root: Path, platform=DEFAULT_PLATFORM,
                  allow_synthetic_fixture=False) -> Dict[str, Any]:
    evidence_class = manifest.get("evidence_class", "production")
    if evidence_class != "production" and not allow_synthetic_fixture:
        raise ValueError("non-production manifest requires --allow-synthetic-fixture")
    readiness = validate_readiness(manifest, root)
    if readiness.get("verdict") != "PASS":
        raise ValueError("boot artifact readiness is BLOCKED")

    artifact = _one([
        item for item in manifest.get("artifacts", []) if item.get("execution_source")
    ], "manifest must mark exactly one execution_source")
    report_item = _one([
        item for item in readiness.get("container_validations", [])
        if item.get("artifact") == artifact["name"]
    ], "execution_source container validation missing")
    report = report_item["report"]
    stages = {name: _stage(report, name) for name in REQUIRED_STAGES}
    source = Path(report["input"]).resolve().as_posix()
    entry = int(stages["ATF"]["entry"], 0)

    steps = []
    for name in REQUIRED_STAGES:
        image = stages[name]
        steps.append({
            "stage": name,
            "source_file": source,
            "source_offset": image["absolute_data_offset"],
            "size_bytes": image["size_bytes"],
            "destination": image["destination"],
            "entry": image["entry"],
            "calculated_hash": image["calculated_hash"],
        })

    lines = [
        ':name: i.MX952 verified post-authentication execution candidate',
        ':description: Loads hash-verified ATF and U-Boot; no Boot ROM/ELE/AHAB success claim',
        '', '$name?="imx952-verified-post-auth"', 'using sysbus', 'mach create $name',
        f'machine LoadPlatformDescription @{platform}', '',
        '# Keep every A55 halted while verified stage bytes are loaded.',
    ] + [f'{cpu} IsHalted true' for cpu in A55_CPUS]
    for step in steps:
        lines += [
            '', f'# {step["stage"]}: verified descriptor hash {step["calculated_hash"]}',
            f'sysbus LoadBinary @{source} {step["destination"]} sysbus.a55_0 '
            f'{step["source_offset"]} 0x{step["size_bytes"]:X}',
        ]
    lines += [
        '', f'sysbus.a55_0 PC 0x{entry:X}', '',
        '# Explicit operator-controlled start; generation never auto-runs the CPU.',
        'macro startVerifiedAtf', '"""', '    sysbus.a55_0 IsHalted false', '"""', ''
    ]
    return {
        "verdict": "PASS",
        "classification": "SYNTHETIC_EXECUTION_FIXTURE" if evidence_class != "production"
                          else "PRODUCTION_POST_AUTH_EXECUTION_CANDIDATE",
        "evidence_class": evidence_class,
        "platform": platform,
        "readiness": readiness,
        "execution_source": artifact["name"],
        "load_steps": steps,
        "entry_stage": "ATF",
        "entry_address": f"0x{entry:016X}",
        "auto_start": False,
        "resc": "\n".join(lines),
        "qualification_boundary": [
            "Verified post-authentication bytes are loaded while all A55 cores remain halted.",
            "Boot ROM reset, boot-source selection and AHAB signature authentication are not implemented.",
            "startVerifiedAtf is an execution experiment, not a production-boot pass."
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--platform", default=DEFAULT_PLATFORM)
    parser.add_argument("--output-resc", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--allow-synthetic-fixture", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    try:
        plan = generate_plan(manifest, args.root, args.platform, args.allow_synthetic_fixture)
    except ValueError as exc:
        blocked = {"verdict": "BLOCKED", "errors": [str(exc)]}
        args.output_json.write_text(json.dumps(blocked, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(blocked, indent=2))
        return 2
    args.output_resc.write_text(plan.pop("resc"), encoding="utf-8")
    args.output_json.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
