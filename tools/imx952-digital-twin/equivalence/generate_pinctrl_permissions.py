#!/usr/bin/env python3
"""Generate exact i.MX952 EVK SCMI Pinctrl permissions from pinned NXP source.

The generator derives the 140 physical pin IDs and 135 daisy IDs from the MIMX952
device header, then extracts per-agent `pinPerms` and `daisyPerms` from the generated
mx952evk SCMI configuration. Later `DEV_SM_PIN_TYPE_*` configuration constants are
not part of the physical pin inventory. Source SHA-256 hashes are embedded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

PINNED_REPOSITORY = "nxp-imx/imx-sm"
PINNED_COMMIT = "44f76dcb32945a60e08ea0133700b820349efbd3"
PIN_HEADER_PATH = "devices/MIMX952/sm/dev_sm_pin.h"
SCMI_CONFIG_PATH = "configs/mx952evk/config_scmi.h"
RAW_BASE = f"https://raw.githubusercontent.com/{PINNED_REPOSITORY}/{PINNED_COMMIT}"
AGENT_NAMES = {0: "M7", 1: "AP-S", 2: "AP-NS"}

PIN_RE = re.compile(r"^\s*#define\s+(DEV_SM_PIN_[A-Z0-9_]+)\s+([0-9]+)U\b")
DAISY_RE = re.compile(r"^\s*#define\s+(DEV_SM_DAISY_[A-Z0-9_]+)\s+([0-9]+)U\b")
NUM_PIN_RE = re.compile(r"^\s*#define\s+DEV_SM_NUM_PIN\s+([0-9]+)U\b")
NUM_DAISY_RE = re.compile(r"^\s*#define\s+DEV_SM_NUM_DAISY\s+([0-9]+)U\b")
AGENT_RE = re.compile(r"^\s*#define\s+SM_SCMI_AGNT([0-9]+)_CONFIG\b")
PIN_PERMISSION_RE = re.compile(
    r"\.pinPerms\[(DEV_SM_PIN_[A-Z0-9_]+)\]\s*=\s*(SM_SCMI_PERM_[A-Z0-9_]+)"
)
DAISY_PERMISSION_RE = re.compile(
    r"\.daisyPerms\[(DEV_SM_DAISY_[A-Z0-9_]+)\]\s*=\s*(SM_SCMI_PERM_[A-Z0-9_]+)"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "imx952-pinctrl-contract-generator"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def load_text(path: Path | None, url: str) -> Tuple[str, str]:
    if path is not None:
        return path.read_text(encoding="utf-8"), str(path)
    return fetch_text(url), url


def parse_inventory(header_text: str) -> Tuple[Dict[str, int], Dict[str, int], int, int]:
    pins: Dict[str, int] = {}
    daisies: Dict[str, int] = {}
    declared_pins = -1
    declared_daisies = -1
    in_pin_index_block = False
    in_daisy_index_block = False

    for line in header_text.splitlines():
        match = NUM_PIN_RE.match(line)
        if match:
            declared_pins = int(match.group(1), 10)
            in_pin_index_block = True
            continue

        match = NUM_DAISY_RE.match(line)
        if match:
            declared_daisies = int(match.group(1), 10)
            continue

        match = DAISY_RE.match(line)
        if match:
            in_pin_index_block = False
            in_daisy_index_block = True
            daisies[match.group(1)] = int(match.group(2), 10)
            continue

        if in_pin_index_block:
            match = PIN_RE.match(line)
            if match:
                pins[match.group(1)] = int(match.group(2), 10)
                continue

        if in_daisy_index_block:
            # The first DEV_SM_PIN_TYPE_* definition marks the end of daisy IDs.
            if line.lstrip().startswith("#define DEV_SM_PIN_TYPE_"):
                in_daisy_index_block = False
                continue
            match = DAISY_RE.match(line)
            if match:
                daisies[match.group(1)] = int(match.group(2), 10)

    if len(pins) != declared_pins:
        raise ValueError(
            f"parsed {len(pins)} physical pins but DEV_SM_NUM_PIN declares {declared_pins}"
        )
    if len(daisies) != declared_daisies:
        raise ValueError(
            f"parsed {len(daisies)} daisies but DEV_SM_NUM_DAISY declares {declared_daisies}"
        )
    return pins, daisies, declared_pins, declared_daisies


def parse_permissions(config_text: str) -> Dict[int, Dict[str, List[Tuple[str, str]]]]:
    result: Dict[int, Dict[str, List[Tuple[str, str]]]] = {
        0: {"pins": [], "daisies": []},
        1: {"pins": [], "daisies": []},
        2: {"pins": [], "daisies": []},
    }
    current_agent: int | None = None

    for line in config_text.splitlines():
        agent_match = AGENT_RE.match(line)
        if agent_match:
            current_agent = int(agent_match.group(1), 10)
            result.setdefault(current_agent, {"pins": [], "daisies": []})
            continue
        if current_agent is None:
            continue

        pin_match = PIN_PERMISSION_RE.search(line)
        if pin_match:
            result[current_agent]["pins"].append(
                (pin_match.group(1), pin_match.group(2))
            )

        daisy_match = DAISY_PERMISSION_RE.search(line)
        if daisy_match:
            result[current_agent]["daisies"].append(
                (daisy_match.group(1), daisy_match.group(2))
            )

        if line.strip().rstrip("\\").strip() == "}":
            current_agent = None

    return result


def make_entries(
    permissions: List[Tuple[str, str]], inventory: Dict[str, int], prefix: str
) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    missing = []
    for symbol, permission in permissions:
        if symbol not in inventory:
            missing.append(symbol)
            continue
        entries.append(
            {
                "id": inventory[symbol],
                "symbol": symbol,
                "name": symbol.removeprefix(prefix),
                "permission": permission.removeprefix("SM_SCMI_PERM_"),
            }
        )
    if missing:
        raise ValueError(f"permission symbols missing from device header: {sorted(missing)}")
    entries.sort(key=lambda item: (item["id"], item["symbol"]))
    return entries


def build_contract(
    header_text: str,
    config_text: str,
    header_source: str,
    config_source: str,
) -> Dict[str, object]:
    pins, daisies, pin_count, daisy_count = parse_inventory(header_text)
    permissions = parse_permissions(config_text)

    agents: Dict[str, object] = {}
    for agent_id in sorted(permissions):
        pin_entries = make_entries(
            permissions[agent_id]["pins"], pins, "DEV_SM_PIN_"
        )
        daisy_entries = make_entries(
            permissions[agent_id]["daisies"], daisies, "DEV_SM_DAISY_"
        )
        agents[str(agent_id)] = {
            "name": AGENT_NAMES.get(agent_id, f"AGENT-{agent_id}"),
            "pin_count": len(pin_entries),
            "daisy_count": len(daisy_entries),
            "pins": pin_entries,
            "daisies": daisy_entries,
        }

    return {
        "schema_version": 1,
        "target": "i.MX952 EVK",
        "source": {
            "repository": PINNED_REPOSITORY,
            "commit": PINNED_COMMIT,
            "pin_header": PIN_HEADER_PATH,
            "generated_config": SCMI_CONFIG_PATH,
            "pin_header_input": header_source,
            "generated_config_input": config_source,
            "pin_header_sha256": sha256_text(header_text),
            "generated_config_sha256": sha256_text(config_text),
        },
        "global_pin_count": pin_count,
        "global_daisy_count": daisy_count,
        "agents": agents,
        "qualification_policy": [
            "Pin and daisy IDs are derived from the pinned MIMX952 device header.",
            "Only generated pinPerms and daisyPerms entries grant agent mutation permission.",
            "The generated contract proves source traceability, not physical pad electrical behavior or timing equivalence."
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin-header", type=Path)
    parser.add_argument("--scmi-config", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("imx952-pinctrl-permissions-generated.json")
    )
    args = parser.parse_args()

    header_text, header_source = load_text(
        args.pin_header, f"{RAW_BASE}/{PIN_HEADER_PATH}"
    )
    config_text, config_source = load_text(
        args.scmi_config, f"{RAW_BASE}/{SCMI_CONFIG_PATH}"
    )
    contract = build_contract(header_text, config_text, header_source, config_source)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "verdict": "PASS",
        "output": str(args.output),
        "global_pin_count": contract["global_pin_count"],
        "global_daisy_count": contract["global_daisy_count"],
        "agent_counts": {
            key: {
                "pins": value["pin_count"],
                "daisies": value["daisy_count"],
            }
            for key, value in contract["agents"].items()
        },
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
