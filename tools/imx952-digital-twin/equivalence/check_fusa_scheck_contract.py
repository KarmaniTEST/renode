#!/usr/bin/env python3
"""Validate the source-bounded i.MX952 FuSa S-check wrapper.

This gate proves structural and deterministic functional behavior only. It does
not prove SCST/SAF execution, physical fault handling or safety timing.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent
PYDEV = ROOT.parents[2] / "scripts" / "pydev"
DEFAULT_MODEL = PYDEV / "nxp_imx952_system_manager_fusa_scheck.py"
DEFAULT_CONTRACT = ROOT / "contracts" / "imx952_fusa_scheck_contract.json"

EXPECTED_CONSTANTS = {
    "_SCHECK_PROTOCOL": 0x83,
    "_SCHECK_EVENT_COMMAND": 0x0B,
    "_SCHECK_TEST_EXEC_COMMAND": 0x0E,
    "_SCHECK_MESSAGE_ATTRIBUTES": 0x02,
    "_SCHECK_EVENT_COUNT_OFFSET": 0x200,
    "_SCHECK_LAST_TEST_ID_OFFSET": 0x204,
    "_SCHECK_TEST_EXEC_COUNT_OFFSET": 0x208,
}
EXPECTED_FUNCTIONS = {
    "_scheck_restore_request",
    "_scheck_publish_evidence",
    "_scheck_complete_response",
}
EXPECTED_SOURCE_BLOBS = {
    "fusa_protocol": "3b246af8595ca3d693b85230bf035bc5b0059135",
    "lmm_fusa_backend": "1f091a9b95af04f5ba137ce23b565da60c3fc3bd",
    "generated_agent_config": "75db444cccfdef07de458cfc210211ee7de13796",
}


def parse_model(path: Path) -> tuple[Dict[str, int], Set[str], str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    constants: Dict[str, int] = {}
    functions: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.add(node.name)
            continue
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        if (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, int)
        ):
            constants[target.id] = value.value
    return constants, functions, text


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    constants, functions, model_text = parse_model(args.model)
    errors: List[str] = []

    if contract.get("schema_version") != 1:
        errors.append("FuSa S-check contract schema_version must be 1")
    if contract.get("target") != "i.MX952 EVK B0":
        errors.append("FuSa S-check target must remain i.MX952 EVK B0")

    source = contract.get("source", {})
    if source.get("repository") != "nxp-imx/imx-sm":
        errors.append("FuSa S-check must use the official NXP System Manager source")
    if source.get("commit") != "44f76dcb32945a60e08ea0133700b820349efbd3":
        errors.append("FuSa S-check source commit differs from the pinned baseline")
    for key, expected_blob in EXPECTED_SOURCE_BLOBS.items():
        if source.get(key, {}).get("git_blob_sha") != expected_blob:
            errors.append(f"FuSa S-check source blob {key} differs from pinned value")

    protocol = contract.get("protocol", {})
    if protocol.get("id") != "0x83" or protocol.get("version") != "0x00010000":
        errors.append("FuSa S-check protocol must remain FuSa 0x83 version 1.0")
    if protocol.get("visible_agents") != [0] or protocol.get("agent") != "M7":
        errors.append("FuSa S-check surface must remain M7-only")
    if protocol.get("permission") != "ALL":
        errors.append("M7 FuSa permission must remain ALL")

    commands = {entry.get("id"): entry for entry in protocol.get("commands", [])}
    if set(commands) != {"0x0B", "0x0E"}:
        errors.append("FuSa S-check command IDs must remain 0x0B and 0x0E")
    if commands.get("0x0B", {}).get("name") != "FUSA_SCHECK_EVNTRIG":
        errors.append("FuSa command 0x0B name differs from pinned source")
    if commands.get("0x0E", {}).get("name") != "FUSA_SCHECK_TEST_EXEC":
        errors.append("FuSa command 0x0E name differs from pinned source")
    if commands.get("0x0B", {}).get("required_permission") != "EXCLUSIVE":
        errors.append("FUSA_SCHECK_EVNTRIG permission must remain EXCLUSIVE")
    if commands.get("0x0E", {}).get("required_permission") != "SET":
        errors.append("FUSA_SCHECK_TEST_EXEC permission must remain SET")

    for name, expected in EXPECTED_CONSTANTS.items():
        if constants.get(name) != expected:
            errors.append(
                f"FuSa S-check executable constant {name}={constants.get(name)!r} "
                f"expected {expected!r}"
            )

    missing_functions = sorted(EXPECTED_FUNCTIONS - functions)
    if missing_functions:
        errors.append(f"FuSa S-check wrapper functions missing: {missing_functions}")

    executable = contract.get("executable_model", {})
    if executable.get("layer") != "scripts/pydev/nxp_imx952_system_manager_fusa_scheck.py":
        errors.append("FuSa S-check executable layer path differs from contract")
    if executable.get("lower_layer") != "scripts/pydev/nxp_imx952_system_manager_fusa.py":
        errors.append("FuSa S-check must preserve the qualified FuSa lower layer")
    if executable.get("event_count_offset") != "0x200":
        errors.append("FuSa S-check event-count evidence offset differs")
    if executable.get("last_test_id_offset") != "0x204":
        errors.append("FuSa S-check last-test evidence offset differs")
    if executable.get("test_exec_count_offset") != "0x208":
        errors.append("FuSa S-check test-count evidence offset differs")
    if "not i.MX952 production registers" not in executable.get(
        "instrumentation_classification", ""
    ):
        errors.append("FuSa S-check evidence registers must remain test instrumentation")

    required_markers = (
        'execfile("scripts/pydev/nxp_imx952_system_manager_fusa.py")',
        "_SCHECK_PRE_WORDS[0] & 0xFFFFFFFF",
        "fusa_scheck_event_count += 1",
        "fusa_scheck_test_exec_count += 1",
        "_set_response(0, SCMI_SUCCESS, [0])",
        "_set_response(0, SCMI_SUCCESS, [])",
        "_write32(MU_GSR, _read32(MU_GSR) | 0x1)",
    )
    for marker in required_markers:
        if marker not in model_text:
            errors.append(f"FuSa S-check executable marker missing: {marker}")

    evidence = set(contract.get("qualification_evidence", []))
    expected_evidence = {
        "tests/platforms/NXP_IMX952_FUSA_SCHECK.robot",
        "tools/imx952-digital-twin/equivalence/check_fusa_scheck_contract.py",
    }
    if evidence != expected_evidence:
        errors.append("FuSa S-check qualification evidence set differs")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "model": str(args.model),
        "contract": str(args.contract),
        "commands": sorted(commands),
        "visible_agents": protocol.get("visible_agents"),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
