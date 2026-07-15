#!/usr/bin/env python3
"""Generate the exact i.MX952 EVK SCMI clock-permission map from pinned NXP source.

The generator intentionally derives IDs from the device clock header and permissions
from the generated mx952evk SCMI configuration instead of maintaining a hand-written
clock inventory. The output is deterministic and records SHA-256 hashes of both source
files so a generated contract can be traced to exact input bytes.
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
CLOCK_HEADER_PATH = "devices/MIMX952/sm/dev_sm_clock.h"
SCMI_CONFIG_PATH = "configs/mx952evk/config_scmi.h"
RAW_BASE = f"https://raw.githubusercontent.com/{PINNED_REPOSITORY}/{PINNED_COMMIT}"

AGENT_NAMES = {0: "M7", 1: "AP-S", 2: "AP-NS"}

CLOCK_DEFINE_RE = re.compile(
    r"^\s*#define\s+(DEV_SM_CLK_[A-Z0-9_]+)\s+([0-9]+)U?\s*(?:/\*.*)?$"
)
AGENT_DEFINE_RE = re.compile(r"^\s*#define\s+SM_SCMI_AGNT([0-9]+)_CONFIG\b")
CLOCK_PERMISSION_RE = re.compile(
    r"\.clkPerms\[(DEV_SM_CLK_[A-Z0-9_]+)\]\s*=\s*(SM_SCMI_PERM_[A-Z0-9_]+)"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "imx952-clock-contract-generator"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
    return data.decode("utf-8")


def load_text(path: Path | None, url: str) -> Tuple[str, str]:
    if path is not None:
        text = path.read_text(encoding="utf-8")
        return text, str(path)
    return fetch_text(url), url


def parse_clock_ids(header_text: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for line in header_text.splitlines():
        match = CLOCK_DEFINE_RE.match(line)
        if match:
            result[match.group(1)] = int(match.group(2), 10)
    if not result:
        raise ValueError("no DEV_SM_CLK_* numeric definitions were found")
    return result


def parse_agent_clock_permissions(config_text: str) -> Dict[int, List[Tuple[str, str]]]:
    result: Dict[int, List[Tuple[str, str]]] = {0: [], 1: [], 2: []}
    current_agent: int | None = None

    for line in config_text.splitlines():
        agent_match = AGENT_DEFINE_RE.match(line)
        if agent_match:
            current_agent = int(agent_match.group(1), 10)
            result.setdefault(current_agent, [])
            continue

        if current_agent is None:
            continue

        permission_match = CLOCK_PERMISSION_RE.search(line)
        if permission_match:
            result[current_agent].append(
                (permission_match.group(1), permission_match.group(2))
            )

        # Generated macro body closes on a standalone `}` optionally followed by `\`.
        stripped = line.strip().rstrip("\\").strip()
        if stripped == "}":
            current_agent = None

    if not any(result.values()):
        raise ValueError("no agent clock permissions were found")
    return result


def build_contract(
    header_text: str,
    config_text: str,
    header_source: str,
    config_source: str,
) -> Dict[str, object]:
    clock_ids = parse_clock_ids(header_text)
    permissions = parse_agent_clock_permissions(config_text)

    agents: Dict[str, object] = {}
    referenced_symbols = set()
    for agent_id in sorted(permissions):
        entries = []
        for symbol, permission in permissions[agent_id]:
            referenced_symbols.add(symbol)
            if symbol not in clock_ids:
                raise ValueError(
                    f"generated config references {symbol}, but the pinned clock header has no numeric ID"
                )
            entries.append(
                {
                    "id": clock_ids[symbol],
                    "symbol": symbol,
                    "name": symbol.removeprefix("DEV_SM_CLK_"),
                    "permission": permission.removeprefix("SM_SCMI_PERM_"),
                }
            )
        entries.sort(key=lambda item: (item["id"], item["symbol"]))
        agents[str(agent_id)] = {
            "name": AGENT_NAMES.get(agent_id, f"AGENT-{agent_id}"),
            "clock_count": len(entries),
            "clocks": entries,
        }

    duplicate_ids: Dict[int, List[str]] = {}
    for symbol, clock_id in clock_ids.items():
        duplicate_ids.setdefault(clock_id, []).append(symbol)
    aliases = [
        {"id": clock_id, "symbols": sorted(symbols)}
        for clock_id, symbols in sorted(duplicate_ids.items())
        if len(symbols) > 1
    ]

    return {
        "schema_version": 1,
        "target": "i.MX952 EVK",
        "source": {
            "repository": PINNED_REPOSITORY,
            "commit": PINNED_COMMIT,
            "clock_header": CLOCK_HEADER_PATH,
            "generated_config": SCMI_CONFIG_PATH,
            "clock_header_input": header_source,
            "generated_config_input": config_source,
            "clock_header_sha256": sha256_text(header_text),
            "generated_config_sha256": sha256_text(config_text),
        },
        "device_clock_definition_count": len(clock_ids),
        "referenced_permission_symbol_count": len(referenced_symbols),
        "agents": agents,
        "numeric_id_aliases": aliases,
        "qualification_policy": [
            "Only clocks present in an agent's generated clkPerms table may be exposed to that agent.",
            "Permission hierarchy must be interpreted according to NXP sm/doc/config.md.",
            "Clock IDs are derived from the pinned MIMX952 device header, never copied from the Linux DTS numbering.",
            "This contract proves source traceability, not physical clock-tree timing equivalence."
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clock-header", type=Path)
    parser.add_argument("--scmi-config", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("imx952-clock-permissions-generated.json"),
    )
    args = parser.parse_args()

    header_text, header_source = load_text(
        args.clock_header, f"{RAW_BASE}/{CLOCK_HEADER_PATH}"
    )
    config_text, config_source = load_text(
        args.scmi_config, f"{RAW_BASE}/{SCMI_CONFIG_PATH}"
    )
    contract = build_contract(header_text, config_text, header_source, config_source)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "verdict": "PASS",
        "output": str(args.output),
        "device_clock_definition_count": contract["device_clock_definition_count"],
        "agent_clock_counts": {
            key: value["clock_count"] for key, value in contract["agents"].items()
        },
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
