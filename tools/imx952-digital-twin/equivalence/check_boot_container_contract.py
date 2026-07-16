#!/usr/bin/env python3
"""Validate the pinned i.MX952 B0 container-v2 parser contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARSER = ROOT / "parse_imx95_container_v2.py"
CONTRACT = ROOT / "contracts" / "imx952_boot_container_v2_contract.json"

EXPECTED_SOURCE_BLOBS = {
    "container_implementation": "00e578039a73c7bc8ab9e0f0765b4a72ccc9b51f",
    "common_header": "fc5613ff62c1aa9ae8ad60966a9aa8ab271bbe38",
    "imx952_recipe": "4316962978802c615f6d55a8c32b110aa8955950",
}
EXPECTED_CONSTANTS = {
    "CONTAINER_TAG": 0x87,
    "CONTAINER_VERSION": 2,
    "CONTAINER_HEADER_SIZE": 16,
    "IMAGE_DESCRIPTOR_SIZE": 128,
    "SIGNATURE_HEADER_SIZE": 16,
    "MAX_IMAGES": 16,
    "SCAN_ALIGNMENT": 0x400,
    "HASH_FLAG_MASK": 0x300,
}
EXPECTED_STAGES = {
    "ATF": 0x8A200000,
    "U_BOOT": 0x90200000,
    "TEE": 0x8C000000,
    "M7_A55_ALIAS": 0x303C0000,
    "M33_OEI": 0x1FFC0000,
}


def parse_module(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants = {}
    dictionaries = {}
    functions = set()
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
            constants[target.id] = value.value
        elif isinstance(value, ast.Dict):
            parsed = {}
            valid = True
            for key, item in zip(value.keys, value.values):
                if not (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and isinstance(item, ast.Constant)
                    and isinstance(item.value, int)
                ):
                    valid = False
                    break
                parsed[key.value] = item.value
            if valid:
                dictionaries[target.id] = parsed
    return constants, dictionaries, functions, path.read_text(encoding="utf-8")


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    constants, dictionaries, functions, text = parse_module(PARSER)
    errors = []

    if contract.get("schema_version") != 1:
        errors.append("boot container contract schema_version must be 1")
    target = contract.get("target", {})
    if target != {"soc": "i.MX952", "revision": "B0", "board": "i.MX952 EVK"}:
        errors.append("target identity differs from pinned EVK B0 baseline")

    source = contract.get("source", {})
    if source.get("repository") != "nxp-imx/imx-mkimage":
        errors.append("source repository differs from official NXP imx-mkimage")
    if source.get("commit") != "1b577853ae1afe1f26cdef27548da52fb424af48":
        errors.append("imx-mkimage commit differs from pinned baseline")
    for key, expected in EXPECTED_SOURCE_BLOBS.items():
        if source.get(key, {}).get("git_blob_sha") != expected:
            errors.append(f"source blob differs: {key}")

    fmt = contract.get("container_format", {})
    expected_format = {
        "tag": "0x87",
        "version": 2,
        "scan_alignment": "0x400",
        "header_size": 16,
        "header_struct": "<BHBIHBBHH",
        "image_descriptor_size": 128,
        "image_descriptor_struct": "<IIQQII64s32s",
        "signature_header_size": 16,
        "signature_header_struct": "<BHBHHHHI",
        "maximum_images": 16,
    }
    for key, expected in expected_format.items():
        if fmt.get(key) != expected:
            errors.append(f"container format differs: {key}")

    for name, expected in EXPECTED_CONSTANTS.items():
        if constants.get(name) != expected:
            errors.append(f"parser constant differs: {name}")
    if dictionaries.get("PINNED_STAGES") != EXPECTED_STAGES:
        errors.append("pinned stage destinations differ from i.MX952 recipe")

    required_functions = {
        "parse_container", "inspect_file", "_candidate_offsets",
        "_digest_region", "_stage_names", "main",
    }
    missing = sorted(required_functions - functions)
    if missing:
        errors.append(f"parser functions missing: {missing}")

    executable = contract.get("executable", {})
    if executable.get("parser") != "tools/imx952-digital-twin/equivalence/parse_imx95_container_v2.py":
        errors.append("parser path differs")
    if executable.get("checker") != "tools/imx952-digital-twin/equivalence/check_boot_container_contract.py":
        errors.append("checker path differs")
    if executable.get("unit_test") != "tools/imx952-digital-twin/equivalence/tests/test_imx95_container_v2.py":
        errors.append("unit-test path differs")

    for marker in (
        'struct.Struct("<BHBIHBBHH")',
        'struct.Struct("<IIQQII64s32s")',
        'struct.Struct("<BHBHHHHI")',
        "descriptor hash mismatch",
        "READY_FOR_EXECUTION",
        "Signature-block fields are parsed but cryptographic signatures are not authenticated.",
    ):
        if marker not in text:
            errors.append(f"parser behavior marker missing: {marker}")

    print(json.dumps({
        "verdict": "PASS" if not errors else "FAIL",
        "contract": str(CONTRACT),
        "parser": str(PARSER),
        "errors": errors,
    }, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
