#!/usr/bin/env python3
"""Validate the executable M7-only i.MX952 FuSa priority contract.

This is structural functional-contract validation. It does not prove physical
fault generation, safety reaction timing, interrupt latency or silicon equivalence.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent
PYDEV = ROOT.parents[2] / "scripts" / "pydev"
DEFAULT_MODEL = PYDEV / "nxp_imx952_system_manager_fusa.py"
DEFAULT_CONTRACT = ROOT / "contracts" / "imx952_fusa_priority_contract.json"

EXPECTED_SOURCE_BLOBS = {
    "generated_agent_config": "75db444cccfdef07de458cfc210211ee7de13796",
    "generated_transport_config": "ca8e3b640d195a7dd8571f853ff319bc9a09ea8c",
    "fusa_protocol": "3b246af8595ca3d693b85230bf035bc5b0059135",
    "fusa_api": "faa9f088795f72889acb40f320c37c45c7bb2145",
    "fault_header": "d74d8869c76c528d96ffe79d34d6bb7fc66f6920",
}

EXPECTED_CONSTANTS = {
    "_FUSA_PROTOCOL": 0x83,
    "_FUSA_VERSION": 0x00010000,
    "_FUSA_FAULT_COUNT": 89,
    "_FUSA_SEENV_ID_COUNT": 1,
    "_FUSA_SEENV_LM_COUNT": 1,
    "_FUSA_PRIORITY_CHANNEL": 2,
    "_FUSA_PRIORITY_QUEUE_LIMIT": 8,
    "_FUSA_NOTIFY_FEENV_STATE_EVENT": 0,
    "_FUSA_NOTIFY_FAULT_EVENT": 2,
    "_INTERNAL_FUSA_FEENV_TRIGGER": 0x1E4,
    "_INTERNAL_FUSA_FAULT_TRIGGER": 0x1F8,
}

EXPECTED_COMMANDS = {
    "PROTOCOL_VERSION",
    "PROTOCOL_ATTRIBUTES",
    "PROTOCOL_MESSAGE_ATTRIBUTES",
    "FUSA_FEENV_STATE_GET",
    "FUSA_FEENV_STATE_NOTIFY",
    "FUSA_SEENV_STATE_GET",
    "FUSA_SEENV_STATE_SET",
    "FUSA_FAULT_GET",
    "FUSA_FAULT_SET",
    "FUSA_FAULT_GROUP_NOTIFY",
    "NEGOTIATE_PROTOCOL_VERSION",
}
EXPECTED_NOT_IMPLEMENTED = {"FUSA_SCHECK_EVNTRIG", "FUSA_SCHECK_TEST_EXEC"}
EXPECTED_FAULT_IDS = {21, 22, 23, 38, 39}
EXPECTED_FAULT_NAMES = {
    21: "WDOG5",
    22: "SW0",
    23: "SW1",
    38: "M7_LOCKUP",
    39: "M7_RESET",
}
REQUIRED_FUNCTIONS = {
    "_fusa_fault_allowed",
    "_fusa_process_fault_get",
    "_fusa_process_fault_set",
    "_fusa_process_fault_group_notify",
    "_fusa_queue_priority",
    "_fusa_queue_feenv_event",
    "_fusa_queue_fault_event",
    "_fusa_try_dispatch_priority",
}


def parse_model(path: Path) -> tuple[Dict[str, int], Dict[str, Set[int]], Set[str], str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    integers: Dict[str, int] = {}
    sets: Dict[str, Set[int]] = {}
    functions: Set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.add(node.name)
            continue
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, int):
            integers[target.id] = value.value
            continue
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "set"
            and len(value.args) == 1
            and isinstance(value.args[0], (ast.List, ast.Tuple, ast.Set))
        ):
            parsed: Set[int] = set()
            valid = True
            for element in value.args[0].elts:
                if not isinstance(element, ast.Constant) or not isinstance(element.value, int):
                    valid = False
                    break
                parsed.add(element.value)
            if valid:
                sets[target.id] = parsed
    return integers, sets, functions, text


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    constants, sets, functions, model_text = parse_model(args.model)
    errors: List[str] = []

    if contract.get("schema_version") != 2:
        errors.append("FuSa contract schema_version must be 2")

    source = contract.get("source", {})
    if source.get("repository") != "nxp-imx/imx-sm":
        errors.append("FuSa contract must use the official nxp-imx/imx-sm source")
    if source.get("commit") != "44f76dcb32945a60e08ea0133700b820349efbd3":
        errors.append("FuSa contract source commit differs from the pinned i.MX952 baseline")
    for key, expected_blob in EXPECTED_SOURCE_BLOBS.items():
        actual_blob = source.get(key, {}).get("git_blob_sha")
        if actual_blob != expected_blob:
            errors.append(f"FuSa source blob {key} differs from pinned value")

    protocol = contract.get("protocol", {})
    if protocol.get("id") != "0x83":
        errors.append("FuSa contract protocol ID must be 0x83")
    if protocol.get("version") != "0x00010000":
        errors.append("FuSa contract version must be 1.0")
    if protocol.get("visible_agents") != [0]:
        errors.append("FuSa surface must remain M7-only")
    if protocol.get("permission") != "ALL" or protocol.get("seenv_id") != 1:
        errors.append("FuSa contract must preserve M7 fusaPerms=ALL and seenvId=1")
    if set(protocol.get("implemented_commands", [])) != EXPECTED_COMMANDS:
        errors.append("FuSa implemented command inventory differs from fault-enabled surface")
    if set(protocol.get("not_implemented_commands", [])) != EXPECTED_NOT_IMPLEMENTED:
        errors.append("FuSa unimplemented command boundary differs from S-check-only remainder")

    inventory = contract.get("inventory", {})
    if inventory.get("global_fault_count") != 89:
        errors.append("FuSa global fault inventory must remain 89")
    if inventory.get("seenv_id_count") != 1 or inventory.get("seenv_lm_count") != 1:
        errors.append("FuSa S-EENV inventory must remain one ID and one LM")
    contract_faults = {
        int(entry.get("id")): entry.get("name")
        for entry in inventory.get("m7_permitted_faults", [])
    }
    if contract_faults != EXPECTED_FAULT_NAMES:
        errors.append("FuSa contract M7 fault permission map differs from pinned 21/22/23/38/39")
    if sets.get("_FUSA_M7_FAULT_IDS") != EXPECTED_FAULT_IDS:
        errors.append("FuSa executable M7 fault IDs differ from pinned permission map")

    transport = contract.get("priority_transport", {})
    if transport.get("agent") != "M7":
        errors.append("FuSa priority transport must remain M7-only")
    if transport.get("local_channel") != 2 or transport.get("global_smt_channel") != 2:
        errors.append("FuSa priority transport must remain on local/global channel 2")
    if transport.get("mu_instance") != 0 or transport.get("mu_doorbell") != 2:
        errors.append("FuSa priority transport MU mapping differs from pinned topology")
    if transport.get("scmi_message_type") != 3:
        errors.append("FuSa P2A events must use SCMI notification message type")
    if transport.get("notification_message_ids") != {
        "FUSA_FEENV_STATE_EVENT": 0,
        "FUSA_FAULT_EVENT": 2,
    }:
        errors.append("FuSa notification message IDs must remain state=0 and fault=2")
    if transport.get("queue_limit") != 8:
        errors.append("FuSa bounded priority queue limit must remain 8")

    for name, expected in EXPECTED_CONSTANTS.items():
        actual = constants.get(name)
        if actual != expected:
            errors.append(f"FuSa executable constant {name}={actual!r} expected {expected!r}")

    missing_functions = sorted(REQUIRED_FUNCTIONS - functions)
    if missing_functions:
        errors.append(f"FuSa fault/priority functions missing: {missing_functions}")

    deterministic = contract.get("deterministic_evidence_inputs", {})
    if deterministic.get("feenv_state_trigger", {}).get("offset") != "0x1E4":
        errors.append("FuSa F-EENV test trigger differs from executable model")
    if deterministic.get("fault_trigger", {}).get("offset") != "0x1F8":
        errors.append("FuSa fault test trigger differs from executable model")
    if "not an i.MX952 production register" not in deterministic.get("classification", ""):
        errors.append("FuSa deterministic triggers must remain classified as test instrumentation")

    evidence = set(contract.get("qualification_evidence", []))
    required_evidence = {
        "scripts/pydev/nxp_imx952_system_manager_fusa.py",
        "tests/platforms/NXP_IMX952_FUSA_PRIORITY.robot",
        "tests/platforms/NXP_IMX952_FUSA_FAULTS.robot",
    }
    if evidence != required_evidence:
        errors.append("FuSa qualification evidence does not include both state and fault suites")

    for marker in (
        "(flags & 0x3) != 0",
        "fusa_fault_notify.add",
        "fusa_fault_notify.discard",
        "fusa_priority_queue.append((message_id, list(words)))",
        "fusa_priority_queue.pop(0)",
        "[_FUSA_NOTIFY_FAULT_EVENT]" if False else "_FUSA_NOTIFY_FAULT_EVENT",
        "SMT_MESSAGE_HEADER",
        "SMT_PAYLOAD",
        "SMT_LENGTH",
        "MU_GSR",
    ):
        if marker not in model_text:
            errors.append(f"FuSa executable behavior marker missing: {marker}")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "model": str(args.model),
        "contract": str(args.contract),
        "protocol": protocol.get("id"),
        "visible_agents": protocol.get("visible_agents"),
        "priority_channel": transport.get("local_channel"),
        "permitted_fault_ids": sorted(sets.get("_FUSA_M7_FAULT_IDS", set())),
        "notification_message_ids": transport.get("notification_message_ids"),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
