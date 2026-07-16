#!/usr/bin/env python3
"""Validate the complete MISC overlay against main and standalone contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
DEFAULT_MAIN = ROOT / "contracts" / "imx952_system_manager_contract.json"
DEFAULT_MISC = ROOT / "contracts" / "imx952_misc_contract.json"
DEFAULT_OVERLAY = ROOT / "contracts" / "imx952_system_manager_misc_overlay.json"

EXPECTED_RESOURCES = {
    "0": {"agent": "M7", "misc_controls": [14, 15, 16], "protocol_visible": True, "non_base_protocol_count": 11},
    "1": {"agent": "AP-S", "misc_controls": [], "protocol_visible": False, "non_base_protocol_count": 5},
    "2": {"agent": "AP-NS", "misc_controls": list(range(15)), "protocol_visible": True, "non_base_protocol_count": 9},
}

EXPECTED_TRANSPORT = {
    "normal_notifications": {
        "M7": {"local_channel": 1, "global_channel": 1, "mu_doorbell": 1},
        "AP-NS": {"local_channel": 3, "global_channel": 6, "mu_doorbell": 1},
    },
    "priority_notifications_unchanged": {
        "M7": {"local_channel": 2, "global_channel": 2, "mu_doorbell": 2}
    },
}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-contract", type=Path, default=DEFAULT_MAIN)
    parser.add_argument("--misc-contract", type=Path, default=DEFAULT_MISC)
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY)
    args = parser.parse_args(argv)

    main_contract = json.loads(args.main_contract.read_text(encoding="utf-8"))
    misc_contract = json.loads(args.misc_contract.read_text(encoding="utf-8"))
    overlay = json.loads(args.overlay.read_text(encoding="utf-8"))
    errors: List[str] = []

    if overlay.get("schema_version") != 1:
        errors.append("MISC overlay schema_version must be 1")
    if main_contract.get("schema_version", 0) < 9:
        errors.append("main System Manager contract is older than schema 9")
    if misc_contract.get("schema_version") != 3:
        errors.append("authoritative standalone MISC contract must be schema 3")

    applies = overlay.get("applies_to", {})
    if applies.get("historical_gate") != "misc_first_slice":
        errors.append("overlay must explicitly supersede the historical misc_first_slice gate")
    if "misc_first_slice" not in main_contract:
        errors.append("historical MISC first slice is missing from main contract")

    supersedes = overlay.get("supersedes", {})
    if supersedes.get("authoritative_schema_version") != 3:
        errors.append("overlay does not pin standalone MISC schema 3")
    if supersedes.get("authoritative_contract") != "tools/imx952-digital-twin/equivalence/contracts/imx952_misc_contract.json":
        errors.append("overlay authoritative MISC contract path differs from expected")

    if overlay.get("agent_resources") != EXPECTED_RESOURCES:
        errors.append("overlay agent resource/protocol inventory differs from qualified 3/0/15 map")
    if overlay.get("transport") != EXPECTED_TRANSPORT:
        errors.append("overlay normal/priority channel topology differs from qualified topology")

    main_channels = {
        int(entry["global_id"]): (entry["agent"], entry["direction"])
        for entry in main_contract.get("smt_channels", [])
    }
    expected_channels = {
        0: ("M7", "A2P"),
        1: ("M7", "P2A_NOTIFY"),
        2: ("M7", "P2A_PRIORITY"),
        3: ("AP-S", "A2P"),
        4: ("AP-S", "P2A_NOTIFY"),
        5: ("AP-NS", "A2P"),
        6: ("AP-NS", "P2A_NOTIFY"),
    }
    if main_channels != expected_channels:
        errors.append("main contract seven-channel SMT topology differs from overlay assumptions")

    misc_permissions = misc_contract.get("agent_permissions", {})
    misc_control_ids = {
        agent_id: sorted(int(control_id) for control_id in data.get("controls", {}))
        for agent_id, data in misc_permissions.items()
    }
    overlay_control_ids = {
        agent_id: data["misc_controls"]
        for agent_id, data in overlay.get("agent_resources", {}).items()
    }
    if misc_control_ids != overlay_control_ids:
        errors.append("overlay resource IDs differ from standalone MISC permissions")

    evidence = set(overlay.get("qualification_evidence", []))
    required_evidence = {
        "tools/imx952-digital-twin/equivalence/contracts/imx952_misc_contract.json",
        "tools/imx952-digital-twin/equivalence/check_misc_contract.py",
        "scripts/pydev/nxp_imx952_system_manager_misc.py",
        "tests/platforms/NXP_IMX952_MISC.robot",
        ".github/workflows/imx952-misc.yml",
    }
    if evidence != required_evidence:
        errors.append("MISC overlay qualification evidence is incomplete or unexpected")
    if "Physical control side effects" not in overlay.get("claim_boundary", ""):
        errors.append("MISC overlay must retain explicit physical claim boundary")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "main_contract_schema": main_contract.get("schema_version"),
        "misc_contract_schema": misc_contract.get("schema_version"),
        "agent_control_counts": {
            agent_id: len(data["misc_controls"])
            for agent_id, data in overlay.get("agent_resources", {}).items()
        },
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
