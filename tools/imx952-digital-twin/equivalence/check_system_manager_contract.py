#!/usr/bin/env python3
"""Check that the executable i.MX952 SCMI candidate matches its pinned contract.

This is a structural qualification gate. It does not prove physical equivalence; it
prevents accidental drift between executable model layers and source-derived
contracts, including generated per-agent Clock and Pinctrl permission maps.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent
PYDEV = ROOT.parents[2] / "scripts" / "pydev"
CONTRACTS = ROOT / "contracts"
DEFAULT_MODEL = PYDEV / "nxp_imx952_system_manager_full.py"
DEFAULT_BBM_MODEL = PYDEV / "nxp_imx952_system_manager_bbm.py"
DEFAULT_MISC_MODEL = PYDEV / "nxp_imx952_system_manager_misc.py"
DEFAULT_CLOCK_MODEL = PYDEV / "nxp_imx952_system_manager_clock.py"
DEFAULT_PINCTRL_MODEL = PYDEV / "nxp_imx952_system_manager_pinctrl.py"
DEFAULT_CONTRACT = CONTRACTS / "imx952_system_manager_contract.json"
DEFAULT_CLOCK_CONTRACT = CONTRACTS / "imx952_clock_permissions.generated.json"
DEFAULT_PINCTRL_CONTRACT = CONTRACTS / "imx952_pinctrl_permissions.contract.json"

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
    "0x19": "_PINCTRL_VERSION",
    "0x80": "SCMI_NXP_LMM_VERSION",
    "0x81": "_BBM_VERSION",
    "0x84": "_MISC_VERSION",
}

EXPECTED_CLOCK_COUNTS = {"0": 5, "1": 9, "2": 92}
EXPECTED_CLOCK_HEADER_SHA256 = "c3b6289c5263bc208f7942055516592177c0c31fcf876da9d1b9f720ffd7aa9f"
EXPECTED_PINCTRL_PIN_COUNTS = {"0": 2, "1": 0, "2": 131}
EXPECTED_PINCTRL_DAISY_COUNTS = {"0": 7, "1": 0, "2": 125}
EXPECTED_PIN_HEADER_SHA256 = "aab6757a0706dc73151819b66969af3208941a6edb6f159b348c30dc605aba51"
EXPECTED_SCMI_CONFIG_SHA256 = "608e103fa601f33825d1c669c4aeb70e77d7fe9ae86a0fd46326e87b183e68d4"
EXPECTED_M7_PINS = {18, 19}
EXPECTED_M7_DAISIES = {0, 69, 70, 71, 72, 73, 74}
EXPECTED_APNS_PIN_EXCLUDE = {18, 19, 123, 124, 129, 130, 133, 138, 139}
EXPECTED_APNS_DAISY_EXCLUDE = {0, 69, 70, 71, 72, 73, 74, 102, 103, 104}


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


def integer_set_assignments(path: Path) -> Dict[str, Set[int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: Dict[str, Set[int]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue

        value = node.value
        elements = None
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            elements = value.elts
        elif (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "set"
            and len(value.args) == 1
            and isinstance(value.args[0], (ast.List, ast.Tuple, ast.Set))
        ):
            elements = value.args[0].elts

        if elements is None:
            continue
        parsed: Set[int] = set()
        valid = True
        for element in elements:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, int):
                valid = False
                break
            parsed.add(element.value)
        if valid:
            result[target.id] = parsed
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


def validate_pinctrl_contract(
    contract: dict,
    pinctrl_contract: dict,
    constants: Dict[str, int],
    pinctrl_sets: Dict[str, Set[int]],
    errors: List[str],
) -> None:
    if pinctrl_contract.get("global_pin_count") != 140:
        errors.append("Pinctrl contract must contain the global 140-pin i.MX952 inventory")
    if pinctrl_contract.get("global_daisy_count") != 135:
        errors.append("Pinctrl contract must contain the global 135-daisy i.MX952 inventory")

    pinctrl_source = pinctrl_contract.get("source", {})
    if pinctrl_source.get("pin_header_sha256") != EXPECTED_PIN_HEADER_SHA256:
        errors.append("Pinctrl contract pin-header SHA-256 does not match pinned NXP source")
    if pinctrl_source.get("generated_config_sha256") != EXPECTED_SCMI_CONFIG_SHA256:
        errors.append("Pinctrl contract SCMI-config SHA-256 does not match pinned NXP source")

    agents = pinctrl_contract.get("agents", {})
    pin_counts = {
        agent_id: int(agent_data.get("pin_count", -1))
        for agent_id, agent_data in agents.items()
    }
    daisy_counts = {
        agent_id: int(agent_data.get("daisy_count", -1))
        for agent_id, agent_data in agents.items()
    }
    if pin_counts != EXPECTED_PINCTRL_PIN_COUNTS:
        errors.append(f"Pinctrl pin counts {pin_counts} do not match pinned 2/0/131 map")
    if daisy_counts != EXPECTED_PINCTRL_DAISY_COUNTS:
        errors.append(f"Pinctrl daisy counts {daisy_counts} do not match pinned 7/0/125 map")

    if set(agents.get("0", {}).get("pin_ids", [])) != EXPECTED_M7_PINS:
        errors.append("Pinctrl M7 pin IDs do not match pinned GPIO_IO14/GPIO_IO15 permissions")
    if set(agents.get("0", {}).get("daisy_ids", [])) != EXPECTED_M7_DAISIES:
        errors.append("Pinctrl M7 daisy IDs do not match pinned CAN1/LPTMR2/LPUART3 permissions")
    if agents.get("1", {}).get("pin_ids") != [] or agents.get("1", {}).get("daisy_ids") != []:
        errors.append("Pinctrl AP-S contract must have no pin or daisy mutation permissions")

    apns = agents.get("2", {})
    pin_rule = apns.get("pin_rule", {})
    daisy_rule = apns.get("daisy_rule", {})
    if (
        pin_rule.get("range_start") != 0
        or pin_rule.get("range_end_inclusive") != 139
        or set(pin_rule.get("exclude", [])) != EXPECTED_APNS_PIN_EXCLUDE
    ):
        errors.append("Pinctrl AP-NS pin rule differs from pinned source-derived projection")
    if (
        daisy_rule.get("range_start") != 0
        or daisy_rule.get("range_end_inclusive") != 134
        or set(daisy_rule.get("exclude", [])) != EXPECTED_APNS_DAISY_EXCLUDE
    ):
        errors.append("Pinctrl AP-NS daisy rule differs from pinned source-derived projection")

    main_pinctrl = contract.get("pinctrl_permissions", {})
    if main_pinctrl.get("global_pin_count") != 140:
        errors.append("System Manager contract must preserve the global 140-pin ID space")
    if main_pinctrl.get("global_daisy_count") != 135:
        errors.append("System Manager contract must preserve the global 135-daisy ID space")
    if main_pinctrl.get("agent_pin_counts") != EXPECTED_PINCTRL_PIN_COUNTS:
        errors.append("System Manager contract Pinctrl pin counts do not match 2/0/131")
    if main_pinctrl.get("agent_daisy_counts") != EXPECTED_PINCTRL_DAISY_COUNTS:
        errors.append("System Manager contract Pinctrl daisy counts do not match 7/0/125")

    source_hashes = main_pinctrl.get("source_hashes", {})
    if source_hashes.get("devices/MIMX952/sm/dev_sm_pin.h") != EXPECTED_PIN_HEADER_SHA256:
        errors.append("System Manager contract Pinctrl pin-header hash differs from compact contract")
    if source_hashes.get("configs/mx952evk/config_scmi.h") != EXPECTED_SCMI_CONFIG_SHA256:
        errors.append("System Manager contract Pinctrl SCMI-config hash differs from compact contract")

    contract_pin_counts = {
        str(agent.get("id")): agent.get("pinctrl_pin_permission_count")
        for agent in contract.get("agents", [])
    }
    contract_daisy_counts = {
        str(agent.get("id")): agent.get("pinctrl_daisy_permission_count")
        for agent in contract.get("agents", [])
    }
    if contract_pin_counts != EXPECTED_PINCTRL_PIN_COUNTS:
        errors.append(
            f"System Manager agent Pinctrl pin counts {contract_pin_counts} do not match 2/0/131"
        )
    if contract_daisy_counts != EXPECTED_PINCTRL_DAISY_COUNTS:
        errors.append(
            f"System Manager agent Pinctrl daisy counts {contract_daisy_counts} do not match 7/0/125"
        )

    if constants.get("_PINCTRL_PROTOCOL") != 0x19:
        errors.append("Pinctrl policy layer protocol ID is not SCMI Pinctrl 0x19")
    if constants.get("_PINCTRL_VERSION") != 0x00010000:
        errors.append("Pinctrl policy layer version is not the pinned NXP 1.0 contract")
    if constants.get("_PIN_COUNT") != 140 or constants.get("_DAISY_COUNT") != 135:
        errors.append("Pinctrl policy layer inventory does not preserve 140 pins and 135 daisies")

    if pinctrl_sets.get("_M7_PIN_IDS") != EXPECTED_M7_PINS:
        errors.append("Pinctrl executable M7 pin set differs from compact contract")
    if pinctrl_sets.get("_M7_DAISY_IDS") != EXPECTED_M7_DAISIES:
        errors.append("Pinctrl executable M7 daisy set differs from compact contract")
    if pinctrl_sets.get("_APNS_PIN_EXCLUDE") != EXPECTED_APNS_PIN_EXCLUDE:
        errors.append("Pinctrl executable AP-NS pin exclusions differ from compact contract")
    if pinctrl_sets.get("_APNS_DAISY_EXCLUDE") != EXPECTED_APNS_DAISY_EXCLUDE:
        errors.append("Pinctrl executable AP-NS daisy exclusions differ from compact contract")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--bbm-model", type=Path, default=DEFAULT_BBM_MODEL)
    parser.add_argument("--misc-model", type=Path, default=DEFAULT_MISC_MODEL)
    parser.add_argument("--clock-model", type=Path, default=DEFAULT_CLOCK_MODEL)
    parser.add_argument("--pinctrl-model", type=Path, default=DEFAULT_PINCTRL_MODEL)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--clock-contract", type=Path, default=DEFAULT_CLOCK_CONTRACT)
    parser.add_argument("--pinctrl-contract", type=Path, default=DEFAULT_PINCTRL_CONTRACT)
    args = parser.parse_args(argv)

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    clock_contract = json.loads(args.clock_contract.read_text(encoding="utf-8"))
    pinctrl_contract = json.loads(args.pinctrl_contract.read_text(encoding="utf-8"))
    model_paths = [
        args.model,
        args.bbm_model,
        args.misc_model,
        args.clock_model,
        args.pinctrl_model,
    ]
    constants = merged_assignments(model_paths)
    pinctrl_sets = integer_set_assignments(args.pinctrl_model)
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
    if "0x19" in implemented:
        validate_pinctrl_contract(
            contract, pinctrl_contract, constants, pinctrl_sets, errors
        )

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
        "models": [str(path) for path in model_paths],
        "contract": str(args.contract),
        "clock_contract": str(args.clock_contract),
        "pinctrl_contract": str(args.pinctrl_contract),
        "implemented_protocols": sorted(implemented),
        "clock_permission_counts": normalize_agent_counts(clock_contract),
        "pinctrl_pin_counts": {
            key: data.get("pin_count")
            for key, data in pinctrl_contract.get("agents", {}).items()
        },
        "pinctrl_daisy_counts": {
            key: data.get("daisy_count")
            for key, data in pinctrl_contract.get("agents", {}).items()
        },
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
