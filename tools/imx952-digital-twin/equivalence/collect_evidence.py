#!/usr/bin/env python3
"""Collect normalized i.MX952 equivalence evidence from files, commands and literals.

Capture plans are JSON and intentionally transport-agnostic. A physical-board plan can
invoke ssh, lab-control CLIs or parse UART logs; a digital-twin plan can invoke Renode
helpers or parse Renode logs. Both produce the same evidence schema consumed by
compare_evidence.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

SCHEMA_VERSION = 1


class CollectionError(RuntimeError):
    pass


def load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CollectionError(f"Cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CollectionError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CollectionError(f"{path}: top-level JSON value must be an object")
    return data


def resolve_path(plan_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (plan_path.parent / path).resolve()


def convert(value: Any, conversion: str | None) -> Any:
    if conversion is None or conversion == "string":
        return value
    if conversion == "int":
        if isinstance(value, int):
            return value
        return int(str(value).strip(), 0)
    if conversion == "float":
        return float(value)
    if conversion == "json":
        return json.loads(value) if isinstance(value, str) else value
    if conversion == "lower":
        return str(value).lower()
    if conversion == "upper":
        return str(value).upper()
    raise CollectionError(f"Unsupported conversion {conversion!r}")


def regex_extract(text: str, source: Mapping[str, Any], all_matches: bool) -> Any:
    pattern = source.get("pattern")
    if not isinstance(pattern, str):
        raise CollectionError("regex source requires string pattern")
    flags = re.MULTILINE
    if source.get("ignore_case"):
        flags |= re.IGNORECASE
    try:
        compiled = re.compile(pattern, flags)
    except re.error as exc:
        raise CollectionError(f"Invalid regex {pattern!r}: {exc}") from exc
    group = source.get("group", 1)
    if all_matches:
        matches = list(compiled.finditer(text))
        if not matches:
            raise CollectionError(f"Pattern {pattern!r} did not match")
        values = [match.group(group) for match in matches]
        return [convert(value, source.get("convert")) for value in values]
    match = compiled.search(text)
    if not match:
        raise CollectionError(f"Pattern {pattern!r} did not match")
    return convert(match.group(group), source.get("convert"))


def run_command(source: Mapping[str, Any], cwd: Path) -> str:
    argv = source.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
        raise CollectionError("command source requires non-empty string argv array")
    timeout = float(source.get("timeout_seconds", 30.0))
    env = None
    if "env" in source:
        if not isinstance(source["env"], dict):
            raise CollectionError("command env must be an object")
        import os
        env = os.environ.copy()
        env.update({str(key): str(value) for key, value in source["env"].items()})
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0 and not source.get("allow_nonzero", False):
        raise CollectionError(
            f"Command {argv!r} failed with {result.returncode}: {result.stderr.strip()}"
        )
    stream = source.get("stream", "stdout")
    if stream == "stdout":
        return result.stdout
    if stream == "stderr":
        return result.stderr
    if stream == "combined":
        return result.stdout + result.stderr
    raise CollectionError(f"Unsupported command stream {stream!r}")


def collect_source(source: Mapping[str, Any], plan_path: Path) -> Any:
    source_type = source.get("type")
    if source_type == "literal":
        return source.get("value")

    if source_type == "sha256":
        path_value = source.get("path")
        if not isinstance(path_value, str):
            raise CollectionError("sha256 source requires path")
        path = resolve_path(plan_path, path_value)
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise CollectionError(f"Cannot hash {path}: {exc}") from exc
        return digest.hexdigest()

    if source_type in {"text_regex", "text_regex_all"}:
        path_value = source.get("path")
        if not isinstance(path_value, str):
            raise CollectionError(f"{source_type} source requires path")
        path = resolve_path(plan_path, path_value)
        try:
            text = path.read_text(encoding=source.get("encoding", "utf-8"), errors="replace")
        except OSError as exc:
            raise CollectionError(f"Cannot read {path}: {exc}") from exc
        return regex_extract(text, source, all_matches=source_type.endswith("_all"))

    if source_type in {"command_regex", "command_regex_all", "command_json"}:
        output = run_command(source, plan_path.parent)
        if source_type == "command_json":
            try:
                return json.loads(output)
            except json.JSONDecodeError as exc:
                raise CollectionError(f"Command output is not JSON: {exc}") from exc
        return regex_extract(output, source, all_matches=source_type.endswith("_all"))

    raise CollectionError(f"Unsupported source type {source_type!r}")


def validate_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise CollectionError(f"Unsupported schema_version {plan.get('schema_version')!r}")
    if not isinstance(plan.get("target"), dict):
        raise CollectionError("Plan target must be an object")
    observations = plan.get("observations")
    if not isinstance(observations, list) or not observations:
        raise CollectionError("Plan observations must be a non-empty list")
    seen = set()
    for item in observations:
        if not isinstance(item, dict):
            raise CollectionError("Each observation plan must be an object")
        key = item.get("key")
        if not isinstance(key, str) or not key:
            raise CollectionError("Each observation plan needs a non-empty key")
        if key in seen:
            raise CollectionError(f"Duplicate observation key {key!r}")
        seen.add(key)
        if not isinstance(item.get("source"), dict):
            raise CollectionError(f"Observation {key!r} needs a source object")


def collect(plan: Mapping[str, Any], plan_path: Path) -> Dict[str, Any]:
    validate_plan(plan)
    observations: Dict[str, Dict[str, Any]] = {}
    errors = []
    for item in plan["observations"]:
        key = item["key"]
        required = bool(item.get("required", True))
        try:
            value = collect_source(item["source"], plan_path)
            observation: Dict[str, Any] = {"value": value}
            if "unit" in item:
                observation["unit"] = item["unit"]
            if "source_note" in item:
                observation["source_note"] = item["source_note"]
            observations[key] = observation
        except (CollectionError, subprocess.TimeoutExpired, ValueError) as exc:
            if required:
                errors.append(f"{key}: {exc}")
            else:
                observations[key] = {"value": None, "collection_error": str(exc)}
    if errors:
        raise CollectionError("Required observations failed:\n  " + "\n  ".join(errors))
    return {
        "schema_version": SCHEMA_VERSION,
        "target": dict(plan["target"]),
        "capture": {
            "plan": plan.get("name", plan_path.name),
            "unix_time": time.time(),
        },
        "observations": observations,
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path, help="Capture plan JSON")
    parser.add_argument("--output", required=True, type=Path, help="Evidence JSON output")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = load_json(args.plan)
        evidence = collect(plan, args.plan.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except CollectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Collected {len(evidence['observations'])} observations -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
