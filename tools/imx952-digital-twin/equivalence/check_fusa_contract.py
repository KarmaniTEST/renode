#!/usr/bin/env python3
"""Validate the executable M7-only i.MX952 FuSa priority contract.

This is structural and functional-contract validation. It does not prove physical
fault generation, safety reaction timing, interrupt latency or silicon equivalence.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Dict, List

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
    "_INTERNAL_FUSA_FEENV_TRIGGER": 0x1E4,
}

EXPECTED_COMMANDS = {
    "PROTOCOL_VERSION",
    "PROTOCOL_ATTRIBUTES",
    "PROTOCOL_MESSAGE_ATTRIBUTES",
    "FUSA_FEENV_STATE_GET",
    "FUSA_FEENV_STATE_NOTIFY",
    "FUSA_SEENV_STATE_GET",
    "FUSA_SEENV_STATE_SET",
    "NEGOTIATE_PROTOCOL_VERSION",
}


def integer_assignments(path: Path) -> Dict[str, int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: Dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        if (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, int)
        ):
            result[target.id] = value.value
    return result


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    constants = integer_assignments(args.model)
    errors: List[str] = []

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
        errors.append("FuSa first slice must remain M7-only")
    if protocol.get("permission") != "ALL" or protocol.get("seenv_id") != 1:
        errors.append("FuSa contract must preserve M7 fusaPerms=ALL and seenvId=1")
    if set(protocol.get("implemented_commands", [])) != EXPECTED_COMMANDS:
        errors.append("FuSa implemented command inventory differs from qualified first slice")

    inventory = contract.get("inventory", {})
    if inventory != {"fault_count": 89, "seenv_id_count": 1, "seenv_lm_count": 1}:
        errors.append("FuSa inventory must remain 89 faults, one S-EENV ID and one S-EENV LM")

    transport = contract.get("priority_transport", {})
    expected_transport = {
        "agent": "M7",
        "local_channel": 2,
        "global_smt_channel": 2,
        "mu_instance": 0,
        "mu_doorbell": 2,
        "notification_message_id": 0,
        "notification_name": "FUSA_FEENV_STATE_EVENT",
        "scmi_message_type": 3,
        "queue_limit": 8,
        "busy_channel_policy": "Preserve queued event order and dispatch the next event only after the agent marks SMT channel 2 free.",
    }
    if transport != expected_transport:
        errors.append("FuSa priority transport mapping differs from pinned M7 channel-2 contract")

    for name, expected in EXPECTED_CONSTANTS.items():
        actual = constants.get(name)
        if actual != expected:
            errors.append(f"FuSa executable constant {name}={actual!r} expected {expected!r}")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "model": str(args.model),
        "contract": str(args.contract),
        "protocol": protocol.get("id"),
        "visible_agents": protocol.get("visible_agents"),
        "priority_channel": transport.get("local_channel"),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
