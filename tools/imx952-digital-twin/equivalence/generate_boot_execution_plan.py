#!/usr/bin/env python3
"""Generate a fail-closed Renode post-authentication execution candidate.

The plan loads only byte ranges that passed artifact identity and container
hash validation. It does not emulate or bypass a successful Boot ROM/ELE/AHAB
result: the CPU remains halted and an explicit start macro is emitted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from validate_boot_readiness import validate_readiness

REQUIRED_STAGES = ("ATF", "U_BOOT")
DEFAULT_PLATFORM = "platforms/boards/nxp_imx952_evk_full.repl"


def _integer(value: str) -> int:
    return int(value, 0)


def _find_execution_container(manifest: Dict[str, Any], readiness: Dict[str, Any]):
    configured = [
        artifact["name"] for artifact in manifest.get("artifacts", [])
        if artifact.get("execution_source")
    ]
    if len(configured) != 1:
        raise ValueError("manifest must mark exactly one container artifact as execution_source")
    name = configured[0]
    for item in readiness.get("container_validations", []):
        if item.get("artifact") == name:
            return name, item["report"]
    raise ValueError(f"execution_source container was not validated: {name}")


def _select_stage(report: Dict[str, Any], stage: str) -> Dict[str, Any]:
    matches = [
        image
        for container in report.get("containers", [])
        for image in container.get("images", [])
        if stage in image.get("stages", [])
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {stage} image, found {len(matches)}")
    image = matches[0]
    if not image.get("hash_match") or image.get("errors"):
        raise ValueError(f"{stage} image did not pass descriptor hash validation")
    return image


def generate_plan(
    manifest: Dict[str, Any], root: Path, platform: str = DEFAULT_PLATFORM,
    allow_synthetic_fixture: bool = False,
) -> Dict[str, Any]:
    evidence_class = manifest.get("evidence_class", "production")
    if evidence_class != "production" and not allow_synthetic_fixture:
        raise ValueError("non-production manifest requires --allow-synthetic-fixture")

    readiness = validate_readiness(manifest, root)
    if readiness.get("verdict") != "PASS":
        raise ValueError("boot artifact readiness is BLOCKED")

    artifact_name, report = _find_execution_container(manifest, readiness)
    stages = {stage: _select_stage(report, stage) for stage in REQUIRED_STAGES}
    container_path = Path(report["input"]).resolve().as_posix()
    atf_entry = _integer(stages["ATF"]["entry"])

    load_steps: List[Dict[str, Any]] = []
    for stage in REQUIRED_STAGES:
        image = stages[stage]
        load_steps.append({
            "stage": stage,
            "source_artifact": artifact_name,
            "source_file": container_path,
            "source_offset": image["absolute_data_offset"],
            "size_bytes": image["size_bytes"],
            "destination": image["destination"],
            "entry": image["entry"],
            "calculated_hash": image["calculated_hash"],
        })

    lines = [
        ':name: i.MX952 verified post-authentication execution candidate',
        ':description: Loads hash-verified ATF and U-Boot stages; does not claim Boot ROM/ELE/AHAB success',
        '',
        '$name?="imx952-verified-post-auth"',
        'using sysbus',
        'mach create $name',
        f'machine LoadPlatformDescription @{platform}',
        '',
        '# Keep every A55 halted while verified stage bytes are loaded.',
        'a55_0 IsHalted true',
        'a55_1 IsHalted true',
        'a55_2 IsHalted true',
        'a55_3 IsHalted true',
    ]
    for step in load_steps:
        lines.extend([
            '',
            f'# {step["stage"]}: verified descriptor hash {step["calculated_hash"]}',
            'sysbus LoadBinary '
            f'@{step["source_file"]} {step["destination"]} a55_0 '
            f'{step["source_offset"]} 0x{step["size_bytes"]:X}',
        ])
    lines.extend([
        '',
        f'a55_0 PC 0x{atf_entry:X}',
        '',
        '# Explicit operator-controlled start; generation never auto-runs the CPU.',
        'macro startVerifiedAtf',
        '"""',
        '    a55_0 IsHalted false',
        '"""',
        '',
    ])

    classification = (
        "SYNTHETIC_EXECUTION_FIXTURE" if evidence_class != "production"
        else "PRODUCTION_POST_AUTH_EXECUTION_CANDIDATE"
    )
    return {
        "verdict": "PASS",
        "classification": classification,
        "evidence_class": evidence_class,
        "platform": platform,
        "readiness": readiness,
        "execution_source": artifact_name,
        "load_steps": load_steps,
        "entry_stage": "ATF",
        "entry_address": f"0x{atf_entry:016X}",
        "auto_start": False,
        "resc": "\n".join(lines),
        "qualification_boundary": [
            "The plan loads verified post-authentication stage bytes and leaves the CPU halted.",
            "It does not implement Boot ROM reset state, boot-source selection or AHAB signature authentication.",
            "Running startVerifiedAtf is a post-authentication execution experiment, not a production-boot pass.",
        ],
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
        plan = generate_plan(
            manifest, args.root, args.platform, args.allow_synthetic_fixture
        )
    except ValueError as exc:
        blocked = {"verdict": "BLOCKED", "errors": [str(exc)]}
        text = json.dumps(blocked, indent=2, sort_keys=True)
        print(text)
        args.output_json.write_text(text + "\n", encoding="utf-8")
        return 2

    args.output_resc.write_text(plan["resc"], encoding="utf-8")
    serializable = dict(plan)
    del serializable["resc"]
    text = json.dumps(serializable, indent=2, sort_keys=True)
    print(text)
    args.output_json.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
