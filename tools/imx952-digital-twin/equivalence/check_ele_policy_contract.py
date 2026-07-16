#!/usr/bin/env python3
"""Validate the source-pinned secure-default i.MX952 ELE policy."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = ROOT.parents[2] / "scripts" / "pydev" / "nxp_imx952_ele.py"
CONTRACT = ROOT / "contracts" / "imx952_ele_policy_contract.json"

EXPECTED = {
    "ELE_VERSION": 6,
    "ELE_VERSION_FW": 7,
    "ELE_CMD_TAG": 0x17,
    "ELE_RESP_TAG": 0xE1,
    "ELE_MAX_ADDR": 0xE0000000,
    "ELE_MAX_TEST_RNG_BYTES": 4096,
    "ELE_TEST_CONTROL": 0x3F0,
    "ELE_TEST_MAGIC": 0x54455354,
    "ELE_PERMISSION_DENIED_FAILURE_IND": 0xF3,
    "ELE_INVALID_MESSAGE_FAILURE_IND": 0xF4,
    "ELE_DISABLED_FEATURE_FAILURE_IND": 0xB6,
}


def parse(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values = {}
    functions = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.add(node.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
            if isinstance(target, ast.Name) and isinstance(value, ast.Constant) and isinstance(value.value, int):
                values[target.id] = value.value
    return values, functions, path.read_text(encoding="utf-8")


def main():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    values, functions, text = parse(MODEL)
    errors = []

    if contract.get("schema_version") != 1 or contract.get("target") != "i.MX952 EVK B0":
        errors.append("schema or target differs")
    source = contract.get("source", {})
    if source.get("commit") != "6eeef838dac4ddbc06ff14450531a95e8c5cb346":
        errors.append("source commit differs")
    if source.get("api_header", {}).get("git_blob_sha") != "989c93ce98dcd7758931fa9e06610e2755d26f6b":
        errors.append("API header blob differs")
    if source.get("api_implementation", {}).get("git_blob_sha") != "75b3e2df6ce457e12aebdffc32ea8ce8d8fb90b0":
        errors.append("API implementation blob differs")
    if len(contract.get("safe_default_commands", [])) != 11:
        errors.append("safe command count differs")
    if len(contract.get("test_only_commands", [])) != 1:
        errors.append("test-only command count differs")
    if len(contract.get("secure_default_denied_commands", [])) != 15:
        errors.append("secure-default denial count differs")

    for name, expected in EXPECTED.items():
        if values.get(name) != expected:
            errors.append("constant differs: " + name)
    for name in ("_write_test_random", "_address_valid", "_success", "_failure", "_process_request"):
        if name not in functions:
            errors.append("function missing: " + name)

    markers = (
        "test_rng_enabled = False",
        "elif not test_rng_enabled:",
        "command in ELE_SECURE_DENY_COMMANDS",
        "ELE_FW_VERSION_VALUE = 0",
        "ELE_FW_SHA1_VALUE = 0",
        "value == ELE_TEST_MAGIC",
    )
    for marker in markers:
        if marker not in text:
            errors.append("policy marker missing: " + marker)

    result = {"verdict": "PASS" if not errors else "FAIL", "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
