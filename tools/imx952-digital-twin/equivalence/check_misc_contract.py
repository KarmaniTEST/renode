#!/usr/bin/env python3
"""Validate the executable i.MX952 MISC layer against its pinned contract.

This gate proves structural consistency for the functional model only. It does
not prove physical register side effects, PCA2131/I2C timing, PHY behavior,
board-event generation or interrupt latency.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT.parents[2] / "scripts" / "pydev" / "nxp_imx952_system_manager_misc.py"
DEFAULT_CONTRACT = ROOT / "contracts" / "imx952_misc_contract.json"

EXPECTED_SOURCE = {
    "commit": "44f76dcb32945a60e08ea0133700b820349efbd3",
    "implementation_blob_sha": "87431fb162f7938238a68b4732f97bfd1c7f05ab",
    "protocol_header_blob_sha": "9cbe547f306a91dee839dbf63651f802bc72ed0b",
    "device_control_header_blob_sha": "85c14e377ac6ae7c69fde11886e58501280ad694",
    "device_control_source_blob_sha": "3008bc27a889cc45afb105c4d468484d16cb0420",
    "board_control_header_blob_sha": "22b61e72d817b74902a155cf93e87c1e984df512",
    "board_control_source_blob_sha": "bfc33a8482b956bdd4639ef88ab363a2600d2f83",
    "generated_config_blob_sha": "75db444cccfdef07de458cfc210211ee7de13796",
    "pca2131_backend_blob_sha": "f781baa79e3130eaa7335204682e872971e11a63",
}

EXPECTED_CONSTANTS = {
    "_MISC_PROTOCOL": 0x84,
    "_MISC_VERSION": 0x00010001,
    "_MISC_CTRL_FLAG_BRD": 0x8000,
    "_MISC_DEVICE_CONTROL_COUNT": 10,
    "_MISC_BOARD_CONTROL_COUNT": 8,
    "_MISC_REASON_COUNT": 32,
    "_MISC_CONTROL_EVENT_MESSAGE_ID": 0,
    "_MISC_MESSAGE_TYPE_NOTIFICATION": 3,
    "_MISC_M7_NOTIFY_CHANNEL": 1,
    "_MISC_APNS_NOTIFY_CHANNEL": 3,
    "_MISC_NOTIFY_QUEUE_LIMIT": 8,
    "_MISC_MAX_VAL": 23,
    "_MISC_MAX_ARG": 22,
    "_MISC_PCA2131_MAX_EXT": 21,
    "_INTERNAL_MISC_CONTROL_TRIGGER": 0x1F4,
}

EXPECTED_MASKS = {
    0: 0x00000001,
    1: 0x0000FF0E,
    2: 0x000001FF,
    3: 0x0003FE00,
    4: 0x07FC0000,
    5: 0x00000080,
    6: 0x0000003F,
    7: 0x00000FC0,
    8: 0x00000001,
    9: 0x00000007,
}

EXPECTED_PERMISSIONS = {
    0: {14: 2, 15: 255, 16: 255},
    1: {},
    2: {
        0: 255, 1: 255, 2: 255, 3: 255, 4: 255,
        5: 255, 6: 255, 7: 255, 8: 255, 9: 255,
        10: 2, 11: 2, 12: 2, 13: 2, 14: 2,
    },
}

REQUIRED_FUNCTIONS = {
    "_misc_protocols_for_agent",
    "_misc_decode_control",
    "_misc_process_control_set",
    "_misc_process_control_get",
    "_misc_process_control_action",
    "_misc_process_control_notify",
    "_misc_process_ext_set",
    "_misc_process_ext_get",
    "_misc_emit_board_event",
    "_misc_queue_notification",
    "_misc_try_dispatch_notification",
}


def eval_node(node: ast.AST, env: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise ValueError(node.id)
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        value = eval_node(node.operand, env)
        if isinstance(node.op, ast.UAdd):
            return +value
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.Invert):
            return ~value
        raise ValueError(type(node.op).__name__)
    if isinstance(node, ast.BinOp):
        left = eval_node(node.left, env)
        right = eval_node(node.right, env)
        if isinstance(node.op, ast.LShift):
            return left << right
        if isinstance(node.op, ast.RShift):
            return left >> right
        if isinstance(node.op, ast.BitOr):
            return left | right
        if isinstance(node.op, ast.BitAnd):
            return left & right
        if isinstance(node.op, ast.BitXor):
            return left ^ right
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        raise ValueError(type(node.op).__name__)
    if isinstance(node, ast.Dict):
        return {
            eval_node(key, env): eval_node(value, env)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.List):
        return [eval_node(element, env) for element in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(eval_node(element, env) for element in node.elts)
    if isinstance(node, ast.Set):
        return {eval_node(element, env) for element in node.elts}
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set"
        and len(node.args) == 1
    ):
        return set(eval_node(node.args[0], env))
    raise ValueError(type(node).__name__)


def assignments(tree: ast.Module) -> Dict[str, Any]:
    env: Dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            env[target.id] = eval_node(node.value, env)
        except (ValueError, TypeError, KeyError):
            continue
    return env


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)

    model_text = args.model.read_text(encoding="utf-8")
    tree = ast.parse(model_text, filename=str(args.model))
    env = assignments(tree)
    functions: Set[str] = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    errors: List[str] = []

    if contract.get("schema_version") != 3:
        errors.append("MISC contract schema_version must be 3")
    protocol = contract.get("protocol", {})
    if protocol.get("id") != "0x84" or protocol.get("version") != "0x00010001":
        errors.append("MISC protocol ID/version differs from NXP MISC 1.1")
    source = protocol.get("source", {})
    for key, expected in EXPECTED_SOURCE.items():
        if source.get(key) != expected:
            errors.append(f"MISC source {key} differs from pinned value")

    for name, expected in EXPECTED_CONSTANTS.items():
        if env.get(name) != expected:
            errors.append(f"{name}={env.get(name)!r} does not match {expected!r}")

    if env.get("_MISC_DEVICE_MASKS") != EXPECTED_MASKS:
        errors.append("Executable MISC device-control masks differ from pinned source")
    if env.get("_MISC_CONTROL_PERMISSIONS") != EXPECTED_PERMISSIONS:
        errors.append("Executable MISC agent/control permission map differs from mx952evk")

    missing = sorted(REQUIRED_FUNCTIONS - functions)
    if missing:
        errors.append(f"MISC executable functions missing: {missing}")

    inventory = contract.get("inventory", {})
    if inventory != {
        "device_control_count": 10,
        "board_control_count": 8,
        "reset_reason_count": 32,
        "board_wire_flag": "0x8000",
    }:
        errors.append("MISC contract inventory differs from pinned 10/8/32 surface")

    contract_masks = {
        int(entry["id"]): int(entry["mask"], 16)
        for entry in contract.get("device_controls", [])
    }
    if contract_masks != EXPECTED_MASKS:
        errors.append("MISC contract device masks differ from executable/source map")

    contract_permissions = {
        int(agent_id): {
            int(control_id): {"NOTIFY": 2, "ALL": 255}[permission]
            for control_id, permission in data.get("controls", {}).items()
        }
        for agent_id, data in contract.get("agent_permissions", {}).items()
    }
    if contract_permissions != EXPECTED_PERMISSIONS:
        errors.append("MISC contract permissions differ from executable/source map")

    payload_limits = contract.get("payload_limits", {})
    if payload_limits.get("control_value_words") != 23:
        errors.append("MISC control value-word limit must be 23")
    if payload_limits.get("action_argument_words") != 22:
        errors.append("MISC action argument-word limit must be 22")
    if payload_limits.get("extended_value_words") != 21:
        errors.append("MISC extended value-word limit must be 21")

    notify = contract.get("notification_delivery", {})
    expected_transport = {
        "M7": {"local_channel": 1, "global_channel": 1, "mu_doorbell": 1},
        "AP-NS": {"local_channel": 3, "global_channel": 6, "mu_doorbell": 1},
    }
    if notify.get("message_id") != 0 or notify.get("queue_class") != "NORMAL":
        errors.append("MISC control events must use notification message 0 on normal queue")
    if notify.get("transport") != expected_transport:
        errors.append("MISC normal P2A transport differs from mx952evk topology")
    if notify.get("event_flags") != {"input_low": 1, "input_high": 2}:
        errors.append("MISC board-event flags differ from source low/high encoding")
    if notify.get("eligible_board_local_ids") != [0, 1, 2, 3, 4]:
        errors.append("MISC notification-eligible board controls differ from source")

    deterministic = contract.get("deterministic_model_inputs", {})
    if deterministic.get("board_control_trigger_offset") != "0x1F4":
        errors.append("MISC deterministic board trigger differs from executable model")
    if "not a physical register" not in deterministic.get("classification", ""):
        errors.append("MISC board trigger must remain classified as test instrumentation")

    for marker in (
        "_bbm_protocols_for_agent(agent_id)",
        "SMT_MESSAGE_HEADER",
        "SMT_PAYLOAD",
        "SMT_LENGTH",
        "MU_GSR",
        "misc_notify_queue.append",
        "misc_notify_queue.pop(0)",
        "misc_pca2131_registers",
        "misc_test_action_count",
    ):
        if marker not in model_text:
            errors.append(f"MISC executable behavior marker missing: {marker}")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "model": str(args.model),
        "contract": str(args.contract),
        "device_controls": len(EXPECTED_MASKS),
        "agent_permission_counts": {
            str(agent): len(permissions)
            for agent, permissions in EXPECTED_PERMISSIONS.items()
        },
        "normal_channels": {"M7": 1, "AP-NS": 3},
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
