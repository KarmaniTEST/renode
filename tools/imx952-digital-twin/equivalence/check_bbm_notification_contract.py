#!/usr/bin/env python3
"""Validate the executable i.MX952 BBM notification layer against its contract.

This is a structural functional-model gate. It prevents drift in protocol IDs,
normal P2A channel selection, event encoding and bounded queue behavior. It does
not claim physical RTC/button generation or interrupt-latency equivalence.
"""

from __future__ import annotations

import ast
import argparse
import json
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent
PYDEV = ROOT.parents[2] / "scripts" / "pydev"
DEFAULT_MODEL = PYDEV / "nxp_imx952_system_manager_bbm.py"
DEFAULT_CONTRACT = ROOT / "contracts" / "imx952_bbm_contract.json"

EXPECTED_SOURCE_COMMIT = "44f76dcb32945a60e08ea0133700b820349efbd3"
EXPECTED_IMPLEMENTATION_BLOB = "73fdc3c132bf9b8e766a3973933d9836d8c1a8df"
EXPECTED_HEADER_BLOB = "c1ff487eb4b76e98177eb5c5f9b0f313795b8109"

EXPECTED_CONSTANTS = {
    "_BBM_PROTOCOL": 0x81,
    "_BBM_VERSION": 0x00010000,
    "_BBM_RTC_EVENT_MESSAGE_ID": 0,
    "_BBM_BUTTON_EVENT_MESSAGE_ID": 1,
    "_BBM_MESSAGE_TYPE_NOTIFICATION": 3,
    "_BBM_M7_NOTIFY_CHANNEL": 1,
    "_BBM_APNS_NOTIFY_CHANNEL": 3,
    "_BBM_NOTIFY_QUEUE_LIMIT": 8,
    "_BBM_NOTIFY_RTC_ALARM": 1,
    "_BBM_NOTIFY_RTC_ROLLOVER": 2,
    "_BBM_NOTIFY_RTC_UPDATED": 4,
    "_BBM_NOTIFY_BUTTON_DETECT": 1,
    "_INTERNAL_BBM_RTC_TRIGGER": 0x1E8,
    "_INTERNAL_BBM_BUTTON_TRIGGER": 0x1EC,
}

REQUIRED_FUNCTIONS = {
    "_bbm_notification_header",
    "_bbm_notify_channel_free",
    "_bbm_try_dispatch_notification",
    "_bbm_queue_notification",
    "_bbm_emit_rtc_event",
    "_bbm_emit_button_event",
}


def safe_integer_expression(node: ast.AST) -> int | None:
    """Evaluate a deliberately small integer-only AST expression subset."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.UnaryOp):
        operand = safe_integer_expression(node.operand)
        if operand is None:
            return None
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Invert):
            return ~operand
        return None
    if isinstance(node, ast.BinOp):
        left = safe_integer_expression(node.left)
        right = safe_integer_expression(node.right)
        if left is None or right is None:
            return None
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
        return None
    return None


def integer_assignments(tree: ast.Module) -> Dict[str, int]:
    values: Dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = safe_integer_expression(node.value)
        if value is not None:
            values[target.id] = value
    return values


def integer_set_assignments(tree: ast.Module) -> Dict[str, Set[int]]:
    values: Dict[str, Set[int]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "set"
            and len(value.args) == 1
        ):
            continue
        try:
            parsed = ast.literal_eval(value.args[0])
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, (list, tuple, set)) and all(isinstance(item, int) for item in parsed):
            values[target.id] = set(parsed)
    return values


def function_names(tree: ast.Module) -> Set[str]:
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)

    model_text = args.model.read_text(encoding="utf-8")
    tree = ast.parse(model_text, filename=str(args.model))
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    constants = integer_assignments(tree)
    sets = integer_set_assignments(tree)
    functions = function_names(tree)
    errors: List[str] = []

    if contract.get("schema_version") != 2:
        errors.append("BBM contract schema_version must be 2")

    protocol = contract.get("protocol", {})
    if protocol.get("id") != "0x81" or protocol.get("version") != "0x00010000":
        errors.append("BBM protocol ID/version differs from NXP BBM 1.0")

    source = protocol.get("source", {})
    if source.get("commit") != EXPECTED_SOURCE_COMMIT:
        errors.append("BBM source commit differs from the pinned NXP baseline")
    if source.get("implementation_blob_sha") != EXPECTED_IMPLEMENTATION_BLOB:
        errors.append("BBM implementation blob differs from the pinned source")
    if source.get("protocol_header_blob_sha") != EXPECTED_HEADER_BLOB:
        errors.append("BBM protocol-header blob differs from the pinned source")

    for name, expected in EXPECTED_CONSTANTS.items():
        actual = constants.get(name)
        if actual != expected:
            errors.append(f"{name}={actual!r} does not match expected {expected!r}")

    if sets.get("_BBM_ALLOWED_AGENTS") != {0, 2}:
        errors.append("BBM executable visibility must remain restricted to M7 and AP-NS")

    missing_functions = sorted(REQUIRED_FUNCTIONS - functions)
    if missing_functions:
        errors.append(f"BBM notification functions missing: {missing_functions}")

    notifications = contract.get("notifications", {})
    if notifications.get("message_ids") != {"rtc_event": 0, "button_event": 1}:
        errors.append("BBM notification message IDs must remain RTC=0 and button=1")
    if notifications.get("message_type") != "SCMI_NOTIFICATION":
        errors.append("BBM P2A events must use SCMI notification message type")

    queues = notifications.get("queues", {})
    if queues.get("class") != "NORMAL":
        errors.append("BBM events must use the normal P2A queue")
    if queues.get("modeled_queue_limit_messages") != 8:
        errors.append("BBM modeled queue limit differs from executable bounded queue")
    if queues.get("overflow_policy") != "drop_new_and_count":
        errors.append("BBM queue overflow policy differs from executable behavior")

    transport = notifications.get("transport", {})
    expected_transport = {
        "M7": {"agent_id": 0, "local_channel": 1, "global_channel": 1, "mu_doorbell": 1},
        "AP-NS": {"agent_id": 2, "local_channel": 3, "global_channel": 6, "mu_doorbell": 1},
    }
    if transport != expected_transport:
        errors.append("BBM normal P2A transport mapping differs from mx952evk topology")

    if notifications.get("rtc_subscription_bits") != {
        "alarm": 0,
        "rollover": 1,
        "updated": 2,
    }:
        errors.append("BBM RTC subscription bit map differs from NXP source")

    rtc_encoding = notifications.get("rtc_event_encoding", {})
    if rtc_encoding != {
        "rtc_id_bits": "31:24",
        "updated_bit": 2,
        "rollover_bit": 1,
        "alarm_bit": 0,
    }:
        errors.append("BBM RTC notification payload encoding differs from NXP source")

    if notifications.get("button_subscription_bit") != 0:
        errors.append("BBM button subscription must use bit 0")
    if notifications.get("button_event_detected_bit") != 0:
        errors.append("BBM button event must use detected bit 0")

    test_inputs = notifications.get("deterministic_test_inputs", {})
    if test_inputs.get("rtc_trigger_offset") != "0x1E8":
        errors.append("BBM RTC test trigger offset differs from executable layer")
    if test_inputs.get("button_trigger_offset") != "0x1EC":
        errors.append("BBM button test trigger offset differs from executable layer")
    if "not physical registers" not in test_inputs.get("classification", ""):
        errors.append("BBM deterministic triggers must remain classified as test instrumentation")

    for required_text in (
        "SMT_CHANNEL_STATUS",
        "SMT_MESSAGE_HEADER",
        "SMT_PAYLOAD",
        "SMT_LENGTH",
        "MU_GSR",
        "_update_m7_scmi_irq()",
        "bbm_notify_queue.append",
        "bbm_notify_queue.pop(0)",
    ):
        if required_text not in model_text:
            errors.append(f"BBM executable layer is missing required behavior marker: {required_text}")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "model": str(args.model),
        "contract": str(args.contract),
        "normal_channels": {"M7": constants.get("_BBM_M7_NOTIFY_CHANNEL"), "AP-NS": constants.get("_BBM_APNS_NOTIFY_CHANNEL")},
        "message_ids": {"rtc": constants.get("_BBM_RTC_EVENT_MESSAGE_ID"), "button": constants.get("_BBM_BUTTON_EVENT_MESSAGE_ID")},
        "queue_limit": constants.get("_BBM_NOTIFY_QUEUE_LIMIT"),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
