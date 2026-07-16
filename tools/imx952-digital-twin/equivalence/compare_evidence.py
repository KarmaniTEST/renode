#!/usr/bin/env python3
"""Compare normalized i.MX952 evidence captured from hardware and the digital twin.

The comparator is intentionally dependency-free so the same qualification logic can
run in CI, on a lab host, or on an offline engineering workstation.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

SCHEMA_VERSION = 1


class EvidenceError(ValueError):
    pass


@dataclass
class RuleResult:
    key: str
    kind: str
    passed: bool
    required: bool
    reference: Any = None
    candidate: Any = None
    message: str = ""
    delta: float | None = None
    allowed_delta: float | None = None


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except OSError as exc:
        raise EvidenceError(f"Cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"Top-level JSON value in {path} must be an object")
    return value


def validate_evidence(document: Mapping[str, Any], name: str) -> None:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError(
            f"{name}: unsupported schema_version {document.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION}"
        )
    target = document.get("target")
    observations = document.get("observations")
    if not isinstance(target, dict):
        raise EvidenceError(f"{name}: target must be an object")
    if not isinstance(observations, dict):
        raise EvidenceError(f"{name}: observations must be an object")
    for key, observation in observations.items():
        if not isinstance(key, str) or not key:
            raise EvidenceError(f"{name}: observation keys must be non-empty strings")
        if not isinstance(observation, dict) or "value" not in observation:
            raise EvidenceError(f"{name}: observation {key!r} must be an object containing value")


def validate_profile(profile: Mapping[str, Any]) -> None:
    if profile.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError("profile: unsupported schema_version")
    rules = profile.get("rules")
    if not isinstance(rules, list) or not rules:
        raise EvidenceError("profile: rules must be a non-empty list")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise EvidenceError(f"profile: rule {index} must be an object")
        if not isinstance(rule.get("key"), str) or not rule["key"]:
            raise EvidenceError(f"profile: rule {index} needs a non-empty key")
        if rule.get("kind", "exact") not in {"exact", "numeric", "set", "sequence", "regex"}:
            raise EvidenceError(f"profile: rule {rule['key']} has unsupported kind")


def obs_value(document: Mapping[str, Any], key: str) -> Tuple[bool, Any, Mapping[str, Any] | None]:
    observation = document["observations"].get(key)
    if observation is None:
        return False, None, None
    return True, observation.get("value"), observation


def target_mismatches(reference: Mapping[str, Any], candidate: Mapping[str, Any], profile: Mapping[str, Any]) -> List[str]:
    expected = profile.get("required_target", {})
    mismatches: List[str] = []
    for field, expected_value in expected.items():
        ref_value = reference["target"].get(field)
        cand_value = candidate["target"].get(field)
        if ref_value != expected_value:
            mismatches.append(f"reference target.{field}={ref_value!r}, expected {expected_value!r}")
        if cand_value != expected_value:
            mismatches.append(f"candidate target.{field}={cand_value!r}, expected {expected_value!r}")
    return mismatches


def compare_exact(reference: Any, candidate: Any, _: Mapping[str, Any]) -> Tuple[bool, str, float | None, float | None]:
    passed = reference == candidate
    return passed, "values match" if passed else "values differ", None, None


def compare_numeric(reference: Any, candidate: Any, rule: Mapping[str, Any]) -> Tuple[bool, str, float | None, float | None]:
    if isinstance(reference, bool) or isinstance(candidate, bool):
        return False, "numeric comparison does not accept booleans", None, None
    try:
        ref = float(reference)
        cand = float(candidate)
    except (TypeError, ValueError):
        return False, "numeric comparison requires numeric values", None, None
    if not math.isfinite(ref) or not math.isfinite(cand):
        return False, "numeric comparison requires finite values", None, None
    abs_tolerance = float(rule.get("abs_tolerance", 0.0))
    rel_tolerance_pct = float(rule.get("rel_tolerance_pct", 0.0))
    delta = abs(cand - ref)
    relative_allowance = abs(ref) * rel_tolerance_pct / 100.0
    allowed = max(abs_tolerance, relative_allowance)
    passed = delta <= allowed
    message = f"delta={delta:g}, allowed={allowed:g}"
    return passed, message, delta, allowed


def compare_set(reference: Any, candidate: Any, _: Mapping[str, Any]) -> Tuple[bool, str, float | None, float | None]:
    if not isinstance(reference, list) or not isinstance(candidate, list):
        return False, "set comparison requires JSON arrays", None, None
    try:
        passed = set(reference) == set(candidate)
    except TypeError:
        return False, "set comparison requires hashable array members", None, None
    return passed, "sets match" if passed else "sets differ", None, None


def compare_sequence(reference: Any, candidate: Any, rule: Mapping[str, Any]) -> Tuple[bool, str, float | None, float | None]:
    if not isinstance(reference, list) or not isinstance(candidate, list):
        return False, "sequence comparison requires JSON arrays", None, None
    ignore = set(rule.get("ignore_values", []))
    ref = [value for value in reference if value not in ignore]
    cand = [value for value in candidate if value not in ignore]
    passed = ref == cand
    return passed, "sequences match" if passed else "sequences differ", None, None


def compare_regex(reference: Any, candidate: Any, rule: Mapping[str, Any]) -> Tuple[bool, str, float | None, float | None]:
    pattern = rule.get("pattern")
    if pattern is None:
        pattern = reference
    if not isinstance(pattern, str) or not isinstance(candidate, str):
        return False, "regex comparison requires a string pattern and candidate", None, None
    try:
        passed = re.fullmatch(pattern, candidate) is not None
    except re.error as exc:
        return False, f"invalid regex: {exc}", None, None
    return passed, "regex matched" if passed else f"candidate does not match {pattern!r}", None, None


COMPARATORS = {
    "exact": compare_exact,
    "numeric": compare_numeric,
    "set": compare_set,
    "sequence": compare_sequence,
    "regex": compare_regex,
}


def compare_documents(reference: Mapping[str, Any], candidate: Mapping[str, Any], profile: Mapping[str, Any]) -> Dict[str, Any]:
    validate_evidence(reference, "reference")
    validate_evidence(candidate, "candidate")
    validate_profile(profile)

    target_errors = target_mismatches(reference, candidate, profile)
    results: List[RuleResult] = []

    for rule in profile["rules"]:
        key = rule["key"]
        kind = rule.get("kind", "exact")
        required = bool(rule.get("required", True))
        ref_present, ref_value, ref_obs = obs_value(reference, key)
        cand_present, cand_value, cand_obs = obs_value(candidate, key)

        if not ref_present or not cand_present:
            missing = []
            if not ref_present:
                missing.append("reference")
            if not cand_present:
                missing.append("candidate")
            passed = not required
            results.append(
                RuleResult(
                    key=key,
                    kind=kind,
                    passed=passed,
                    required=required,
                    reference=ref_value,
                    candidate=cand_value,
                    message=f"missing observation in {', '.join(missing)}",
                )
            )
            continue

        expected_unit = rule.get("unit")
        if expected_unit is not None:
            ref_unit = ref_obs.get("unit") if ref_obs else None
            cand_unit = cand_obs.get("unit") if cand_obs else None
            if ref_unit != expected_unit or cand_unit != expected_unit:
                results.append(
                    RuleResult(
                        key=key,
                        kind=kind,
                        passed=False,
                        required=required,
                        reference=ref_value,
                        candidate=cand_value,
                        message=f"unit mismatch: reference={ref_unit!r}, candidate={cand_unit!r}, expected={expected_unit!r}",
                    )
                )
                continue

        passed, message, delta, allowed = COMPARATORS[kind](ref_value, cand_value, rule)
        results.append(
            RuleResult(
                key=key,
                kind=kind,
                passed=passed,
                required=required,
                reference=ref_value,
                candidate=cand_value,
                message=message,
                delta=delta,
                allowed_delta=allowed,
            )
        )

    required_failures = [result for result in results if result.required and not result.passed]
    verdict = "PASS" if not target_errors and not required_failures else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": verdict,
        "reference_target": reference["target"],
        "candidate_target": candidate["target"],
        "profile": profile.get("name", "unnamed"),
        "target_mismatches": target_errors,
        "summary": {
            "rules": len(results),
            "passed": sum(result.passed for result in results),
            "failed": sum(not result.passed for result in results),
            "required_failed": len(required_failures),
        },
        "results": [asdict(result) for result in results],
    }


def render_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"Equivalence verdict: {report['verdict']}",
        f"Profile: {report['profile']}",
        (
            "Rules: {rules}, passed: {passed}, failed: {failed}, required failed: {required_failed}".format(
                **report["summary"]
            )
        ),
    ]
    for mismatch in report["target_mismatches"]:
        lines.append(f"TARGET FAIL: {mismatch}")
    for result in report["results"]:
        marker = "PASS" if result["passed"] else "FAIL"
        required = "required" if result["required"] else "optional"
        lines.append(f"{marker:4} {result['key']} [{result['kind']}, {required}] - {result['message']}")
    return "\n".join(lines)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path, help="Physical-board evidence JSON")
    parser.add_argument("--candidate", required=True, type=Path, help="Digital-twin evidence JSON")
    parser.add_argument("--profile", required=True, type=Path, help="Comparison profile JSON")
    parser.add_argument("--output", type=Path, help="Write machine-readable report JSON")
    parser.add_argument("--quiet", action="store_true", help="Do not print the human-readable report")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        reference = load_json(args.reference)
        candidate = load_json(args.candidate)
        profile = load_json(args.profile)
        report = compare_documents(reference, candidate, profile)
    except EvidenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not args.quiet:
        print(render_text(report))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
