#!/usr/bin/env python3
"""Check that the executable i.MX952 SCMI candidate matches its pinned contract.

This is a structural qualification gate. It does not prove physical equivalence; it
prevents accidental drift between executable model layers and source-derived
contracts, including the generated per-agent i.MX952 clock permission map.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent
PYDEV = ROOT.parents[2] / "scripts" / "pydev"
CONTRACTS = ROOT / "contracts"
DEFAULT_MODEL = PYDEV / "nxp_imx952_system_manager_full.py"
DEFAULT_BBM_MODEL = PYDEV / "nxp_imx952_system_manager_bbm.py"
DEFAULT_MISC_MODEL = PYDEV / "nxp_imx952_system_manager_misc.py"
DEFAULT_CLOCK_MODEL = PYDEV / "nxp_imx952_system_manager_clock.py"
DEFAULT_CONTRACT = CONTRACTS / "imx952_system_manager_contract.json"
DEFAULT_CLOCK_CONTRACT = CONTRACTS / "imx952_clock_permissions.generated.json"

PROTOCOL_CONSTANTS = {
    "0x10": "SCMI_PROTOCOL_BASE",
    "0x11": "SCMI_PROTOCOL_POWER",
    "0x12": "SCMI_PROTOCOL_SYSTEM",
    "0x13": "SCMI_PROTOCOL_PERF",
    "0x14": "SCMI_PROTOCOL_CLOCK",
    "0x15": "SCMI_PROTOCOL_SENSOR",
    "0x19": "SCMI_PROTOCOL_PINCTRL",
    "0x80": "SCMI_PROTOCOL_NXP_LMM",
    "0x81": "_BBM_PROTOCOL",
    "0x82": "SCMI_PROTOCOL_NXP_CPU",
    "0x84": "_MISC_PROTOCOL",
}

VERSION_CONSTANTS = {
    "0x11": "SCMI_POWER_VERSION",
    "0x12": "SCMI_SYSTEM_VERSION",
    "0x13": "SCMI_PERF_VERSION",
    "0x14": "SCMI_CLOCK_VERSION",
    "0x15": "SCMI_SENSOR_VERSION",
    "0x80": "SCMI_NXP_LMM_VERSION",
    "0x81": "_BBM_VERSION",
    "0x84": "_MISC_VERSION",
}

EXPECTED_CLOCK_COUNTS = {"0": 5, "1": 9, "2": 92}
EXPECTED_CLOCK_HEADER_SHA256 = "c3b6289c5263bc208f7942055516592177c0c31fcf876da9d1b9f720ffd7aa9f"
EXPECTED_SCMI_CONFIG_SHA256 = "608e103fa601f33825d1c669c4aeb70e77d7fe9ae86a0fd46326e87b183e68d4"


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


def merged_assignments(paths: List[Path]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for path in paths:
        result.update(integer_assignments(path))
    return result


def normalize_agent_counts(clock_contract: dict) -> Dict[str, int]:
    return {
        agent_id: int(agent_data.get("clock_count", -1))
        for agent_id, agent_data in clock_contract.get("agents", {}).items()
    }


def validate_clock_contract(
    contract: dict,
    clock_contract: dict,
    constants: Dict[str, int],
    errors: List[str],
) -> None:
    if clock_contract.get("device_clock_definition_count") != 198:
        errors.append("generated clock contract must contain the global 198-clock i.MX952 inventory")

    generated_counts = normalize_agent_counts(clock_contract)
    if generated_counts != EXPECTED_CLOCK_COUNTS:
        errors.append(
            f"generated clock permission counts {generated_counts} do not match pinned 5/9/92 map"
        )

    clock_source = clock_contract.get("source", {})
    if clock_source.get("clock_header_sha256") != EXPECTED_CLOCK_HEADER_SHA256:
        errors.append("generated clock contract header SHA-256 does not match pinned NXP source")
    if clock_source.get("generated_config_sha256") != EXPECTED_SCMI_CONFIG_SHA256:
        errors.append("generated clock contract SCMI config SHA-256 does not match pinned NXP source")

    main_clock = contract.get("clock_permissions", {})
    if main_clock.get("global_clock_count") != 198:
        errors.append("System Manager contract must preserve the global 198-clock ID space")
    if main_clock.get("agent_counts") != EXPECTED_CLOCK_COUNTS:
        errors.append("System Manager contract clock agent counts do not match generated 5/9/92 map")

    source_hashes = main_clock.get("source_hashes", {})
    if source_hashes.get("devices/MIMX952/sm/dev_sm_clock.h") != EXPECTED_CLOCK_HEADER_SHA256:
        errors.append("System Manager contract clock-header hash differs from generated clock contract")
    if source_hashes.get("configs/mx952evk/config_scmi.h") != EXPECTED_SCMI_CONFIG_SHA256:
        errors.append("System Manager contract SCMI-config hash differs from generated clock contract")

    agent_counts = {
        str(agent.get("id")): agent.get("clock_permission_count")
        for agent in contract.get("agents", [])
    }
    if agent_counts != EXPECTED_CLOCK_COUNTS:
        errors.append(
            f"System Manager agent clock_permission_count values {agent_counts} do not match 5/9/92"
        )

    if constants.get("_CLOCK_PROTOCOL") != 0x14:
        errors.append("Clock policy layer protocol ID is not SCMI Clock 0x14")
    if constants.get("_CLOCK_COUNT") != 198:
        errors.append("Clock policy layer does not preserve the global 198-clock inventory")
    if constants.get("_CLOCK_PERMISSION_ALL_BITS") != 0xE0000000:
        errors.append("Clock policy layer permission bitmap differs from state|parent|rate contract")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--bbm-model", type=Path, default=DEFAULT_BBM_MODEL)
    parser.add_argument("--misc-model", type=Path, default=DEFAULT_MISC_MODEL)
    parser.add_argument("--clock-model", type=Path, default=DEFAULT_CLOCK_MODEL)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--clock-contract", type=Path, default=DEFAULT_CLOCK_CONTRACT)
    args = parser.parse_args(argv)

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    clock_contract = json.loads(args.clock_contract.read_text(encoding="utf-8"))
    constants = merged_assignments(
        [args.model, args.bbm_model, args.misc_model, args.clock_model]
    )
    errors: List[str] = []

    implemented = set(contract.get("candidate_implemented_protocols", []))
    for protocol_id in sorted(implemented):
        constant_name = PROTOCOL_CONSTANTS.get(protocol_id)
        if constant_name is None:
            errors.append(f"contract marks {protocol_id} implemented but no checker mapping exists")
            continue
        actual = constants.get(constant_name)
        if actual is None:
            errors.append(f"model layers are missing {constant_name} for implemented {protocol_id}")
            continue
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
            errors.append(f"model layers are missing version constant {constant_name}")
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

    lm_ids = {entry["id"] for entry in contract.get("logical_machines", [])}
    if lm_ids != {1, 2}:
        errors.append(f"unexpected i.MX952 logical-machine inventory: {sorted(lm_ids)}")
    if constants.get("LM_M7") != 1 or constants.get("LM_AP") != 2:
        errors.append("model logical-machine IDs do not match the pinned mx952evk SCMI instances")

    if "0x14" in implemented:
        validate_clock_contract(contract, clock_contract, constants, errors)

    bbm_contract = contract.get("bbm_resources", {})
    if "0x81" in implemented:
        if bbm_contract.get("gprs") != list(range(8)):
            errors.append("BBM GPR inventory does not match the pinned i.MX952 8-GPR contract")
        rtc_ids = [entry.get("id") for entry in bbm_contract.get("rtcs", [])]
        if rtc_ids != [0, 1]:
            errors.append(f"unexpected i.MX952 BBM RTC inventory: {rtc_ids}")

    if "0x84" in implemented:
        misc = contract.get("misc_first_slice", {})
        controls = misc.get("controls", [])
        if controls != [{"id": 9, "name": "COMBO_PHY", "permission": "ALL"}]:
            errors.append("MISC first slice must remain restricted to AP-NS COMBO_PHY control 9")
        if constants.get("_MISC_COMBO_PHY") != 9:
            errors.append("MISC model COMBO_PHY control ID does not match the pinned i.MX952 contract")
        if constants.get("_MISC_DEVICE_CONTROL_COUNT") != 10:
            errors.append("MISC device-control count does not match i.MX952 DEV_SM_NUM_CTRL")
        if constants.get("_MISC_BOARD_CONTROL_COUNT") != 8:
            errors.append("MISC board-control count does not match the i.MX952 EVK board header")
        if constants.get("_MISC_REASON_COUNT") != 32:
            errors.append("MISC reset-reason count does not match i.MX952 DEV_SM_NUM_REASON")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "models": [
            str(args.model),
            str(args.bbm_model),
            str(args.misc_model),
            str(args.clock_model),
        ],
        "contract": str(args.contract),
        "clock_contract": str(args.clock_contract),
        "implemented_protocols": sorted(implemented),
        "clock_permission_counts": normalize_agent_counts(clock_contract),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
