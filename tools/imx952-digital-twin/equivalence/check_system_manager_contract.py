#!/usr/bin/env python3
"""Check that the executable i.MX952 SCMI candidate matches its pinned contract.

This is a structural qualification gate. It does not prove physical equivalence; it
prevents accidental drift between the model's advertised protocol IDs/versions and
the source-derived contract used by the qualification program.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT.parents[2] / "scripts" / "pydev" / "nxp_imx952_system_manager_full.py"
DEFAULT_CONTRACT = ROOT / "contracts" / "imx952_system_manager_contract.json"

PROTOCOL_CONSTANTS = {
    "0x10": "SCMI_PROTOCOL_BASE",
    "0x11": "SCMI_PROTOCOL_POWER",
    "0x12": "SCMI_PROTOCOL_SYSTEM",
    "0x13": "SCMI_PROTOCOL_PERF",
    "0x14": "SCMI_PROTOCOL_CLOCK",
    "0x15": "SCMI_PROTOCOL_SENSOR",
    "0x19": "SCMI_PROTOCOL_PINCTRL",
    "0x82": "SCMI_PROTOCOL_NXP_CPU",
}

VERSION_CONSTANTS = {
    "0x11": "SCMI_POWER_VERSION",
    "0x12": "SCMI_SYSTEM_VERSION",
    "0x13": "SCMI_PERF_VERSION",
    "0x14": "SCMI_CLOCK_VERSION",
    "0x15": "SCMI_SENSOR_VERSION",
}


def integer_assignments(path: Path) -> Dict[str, int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: Dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, int):
            result[target.id] = value.value
    return result


def normalize_hex(value: int) -> str:
    return f"0x{value:02X}"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    constants = integer_assignments(args.model)
    errors: List[str] = []

    implemented = set(contract.get("candidate_implemented_protocols", []))
    for protocol_id in sorted(implemented):
        constant_name = PROTOCOL_CONSTANTS.get(protocol_id)
        if constant_name is None:
            errors.append(f"contract marks {protocol_id} implemented but no checker mapping exists")
            continue
        actual = constants.get(constant_name)
        if actual is None:
            errors.append(f"model is missing {constant_name} for implemented {protocol_id}")
            continue
        if normalize_hex(actual) != protocol_id.upper().replace("0X", "0x"):
            # Compare numerically to avoid formatting differences.
            if actual != int(protocol_id, 16):
                errors.append(
                    f"{constant_name}={hex(actual)} does not match contract protocol {protocol_id}"
                )

    known_versions = contract.get("known_protocol_versions", {})
    for protocol_id, constant_name in VERSION_CONSTANTS.items():
        if protocol_id not in implemented:
            continue
        expected_text = known_versions.get(protocol_id)
        if expected_text is None:
            errors.append(f"implemented {protocol_id} has no pinned protocol version")
            continue
        actual = constants.get(constant_name)
        if actual is None:
            errors.append(f"model is missing version constant {constant_name}")
            continue
        expected = int(expected_text, 16)
        if actual != expected:
            errors.append(
                f"{constant_name}={hex(actual)} does not match pinned {expected_text}"
            )

    sensor_ids = {entry["id"] for entry in contract.get("device_sensors", [])}
    if sensor_ids != {0, 1}:
        errors.append(f"unexpected i.MX952 device-sensor inventory: {sorted(sensor_ids)}")
    if constants.get("SENSOR_TEMP_ANA") != 0 or constants.get("SENSOR_TEMP_A55") != 1:
        errors.append("model sensor IDs do not match the pinned i.MX952 sensor header")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "model": str(args.model),
        "contract": str(args.contract),
        "implemented_protocols": sorted(implemented),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
