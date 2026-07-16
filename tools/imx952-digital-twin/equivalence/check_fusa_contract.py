#!/usr/bin/env python3
"""Validate the pinned i.MX952 FuSa functional contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = ROOT.parents[2] / "scripts" / "pydev" / "nxp_imx952_system_manager_fusa.py"
CONTRACT = ROOT / "contracts" / "imx952_fusa_priority_contract.json"

EXPECTED_COMMANDS = {
    "PROTOCOL_VERSION", "PROTOCOL_ATTRIBUTES", "PROTOCOL_MESSAGE_ATTRIBUTES",
    "FUSA_FEENV_STATE_GET", "FUSA_FEENV_STATE_NOTIFY",
    "FUSA_SEENV_STATE_GET", "FUSA_SEENV_STATE_SET",
    "FUSA_FAULT_GET", "FUSA_FAULT_SET", "FUSA_FAULT_GROUP_NOTIFY",
    "FUSA_SCHECK_EVNTRIG", "FUSA_SCHECK_TEST_EXEC",
    "NEGOTIATE_PROTOCOL_VERSION",
}
EXPECTED_FAULTS = {21: "WDOG5", 22: "SW0", 23: "SW1", 38: "M7_LOCKUP", 39: "M7_RESET"}
EXPECTED_OVERLAY = {
    "model": "scripts/pydev/nxp_imx952_system_manager_fusa_scheck.py",
    "contract": "tools/imx952-digital-twin/equivalence/contracts/imx952_fusa_scheck_contract.json",
    "checker": "tools/imx952-digital-twin/equivalence/check_fusa_scheck_contract.py",
}
EXPECTED_BLOBS = {
    "generated_agent_config": "75db444cccfdef07de458cfc210211ee7de13796",
    "generated_transport_config": "ca8e3b640d195a7dd8571f853ff319bc9a09ea8c",
    "fusa_protocol": "3b246af8595ca3d693b85230bf035bc5b0059135",
    "fusa_api": "faa9f088795f72889acb40f320c37c45c7bb2145",
    "fault_header": "d74d8869c76c528d96ffe79d34d6bb7fc66f6920",
}
EXPECTED_CONSTANTS = {
    "_FUSA_PROTOCOL": 0x83,
    "_FUSA_VERSION": 0x10000,
    "_FUSA_FAULT_COUNT": 89,
    "_FUSA_PRIORITY_CHANNEL": 2,
    "_FUSA_PRIORITY_QUEUE_LIMIT": 8,
    "_FUSA_NOTIFY_FEENV_STATE_EVENT": 0,
    "_FUSA_NOTIFY_FAULT_EVENT": 2,
    "_INTERNAL_FUSA_FEENV_TRIGGER": 0x1E4,
    "_INTERNAL_FUSA_FAULT_TRIGGER": 0x1F8,
}


def assignments(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    ints, sets, funcs = {}, {}, set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs.add(node.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, int):
                ints[name] = value.value
            elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "set" and value.args:
                arg = value.args[0]
                if isinstance(arg, (ast.List, ast.Tuple, ast.Set)):
                    parsed = {e.value for e in arg.elts if isinstance(e, ast.Constant) and isinstance(e.value, int)}
                    if len(parsed) == len(arg.elts):
                        sets[name] = parsed
    return ints, sets, funcs, path.read_text(encoding="utf-8")


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    ints, sets, funcs, text = assignments(MODEL)
    errors = []

    if contract.get("schema_version") != 3:
        errors.append("schema_version must be 3")
    source = contract.get("source", {})
    if source.get("repository") != "nxp-imx/imx-sm" or source.get("commit") != "44f76dcb32945a60e08ea0133700b820349efbd3":
        errors.append("source identity differs")
    for key, value in EXPECTED_BLOBS.items():
        if source.get(key, {}).get("git_blob_sha") != value:
            errors.append(f"source blob differs: {key}")

    protocol = contract.get("protocol", {})
    if protocol.get("id") != "0x83" or protocol.get("version") != "0x00010000":
        errors.append("protocol identity differs")
    if protocol.get("visible_agents") != [0] or protocol.get("permission") != "ALL":
        errors.append("M7-only policy differs")
    if set(protocol.get("implemented_commands", [])) != EXPECTED_COMMANDS:
        errors.append("command inventory differs")
    if protocol.get("not_implemented_commands") != []:
        errors.append("software-visible command remainder is not empty")
    if protocol.get("scheck_overlay") != EXPECTED_OVERLAY:
        errors.append("S-check overlay differs")

    inventory = contract.get("inventory", {})
    faults = {int(x["id"]): x["name"] for x in inventory.get("m7_permitted_faults", [])}
    if inventory.get("global_fault_count") != 89 or faults != EXPECTED_FAULTS:
        errors.append("fault inventory differs")
    if sets.get("_FUSA_M7_FAULT_IDS") != set(EXPECTED_FAULTS):
        errors.append("executable permission set differs")

    transport = contract.get("priority_transport", {})
    if transport.get("local_channel") != 2 or transport.get("global_smt_channel") != 2 or transport.get("queue_limit") != 8:
        errors.append("priority transport differs")
    if transport.get("notification_message_ids") != {"FUSA_FEENV_STATE_EVENT": 0, "FUSA_FAULT_EVENT": 2}:
        errors.append("notification IDs differ")

    for name, value in EXPECTED_CONSTANTS.items():
        if ints.get(name) != value:
            errors.append(f"constant differs: {name}")
    for name in ("_fusa_process_fault_get", "_fusa_process_fault_set", "_fusa_process_fault_group_notify", "_fusa_queue_priority", "_fusa_try_dispatch_priority"):
        if name not in funcs:
            errors.append(f"function missing: {name}")
    for marker in ("fusa_fault_notify.add", "fusa_priority_queue.pop(0)", "SMT_MESSAGE_HEADER", "MU_GSR"):
        if marker not in text:
            errors.append(f"marker missing: {marker}")

    evidence = set(contract.get("qualification_evidence", []))
    expected_evidence = {
        "scripts/pydev/nxp_imx952_system_manager_fusa.py",
        "scripts/pydev/nxp_imx952_system_manager_fusa_scheck.py",
        "tests/platforms/NXP_IMX952_FUSA_PRIORITY.robot",
        "tests/platforms/NXP_IMX952_FUSA_FAULTS.robot",
        "tests/platforms/NXP_IMX952_FUSA_SCHECK.robot",
    }
    if evidence != expected_evidence:
        errors.append("evidence set differs")

    print(json.dumps({"verdict": "PASS" if not errors else "FAIL", "errors": errors}, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
