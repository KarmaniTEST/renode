from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validate_hybrid_backends import validate_manifest  # noqa: E402

TEMPLATE = ROOT / "plans" / "imx952_hybrid_backends.template.json"


class HybridBackendGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.template = json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def _file_record(self, name: str, content: bytes):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {"path": name, "sha256": hashlib.sha256(content).hexdigest()}

    def _complete(self, evidence_class="synthetic_fixture", physical=False):
        manifest = copy.deepcopy(self.template)
        manifest["evidence_class"] = evidence_class
        for index, (name, entry) in enumerate(sorted(manifest["subsystems"].items())):
            entry["enabled"] = True
            entry["backend_kind"] = "verilator"
            entry["source"] = {
                "repository": f"fixture/{name}",
                "commit": "%040x" % (index + 1),
            }
            entry["artifact"] = self._file_record(
                f"artifacts/{name}.so", f"backend-{name}".encode()
            )
            entry["provided_capabilities"] = list(entry["mandatory_capabilities"])
            entry["mmio_ranges"] = [{
                "base": hex(0x10000000 + index * 0x100000),
                "size": "0x10000",
            }]
            entry["interrupt_routes"] = [{
                "source": f"{name}.irq0",
                "target": f"gic@{100 + index}",
            }]
            test_record = self._file_record(
                f"tests/{name}.json", json.dumps({"subsystem": name, "pass": True}).encode()
            )
            test_record["name"] = "deterministic-smoke"
            entry["deterministic_tests"] = [test_record]

            if physical:
                records = {}
                for field in manifest["physical_evidence_contract"]["file_fields"]:
                    records[field] = self._file_record(
                        f"evidence/{name}-{field}.json",
                        json.dumps({"subsystem": name, "field": field}).encode(),
                    )
                entry["physical_evidence"] = {
                    "board_identity": {"board": "i.MX952 EVK", "serial": f"FIX-{index}"},
                    "silicon_identity": {"revision": "B0", "lot": f"FIX-{index}"},
                    **records,
                    "comparison_result": "PASS",
                    "timing_tolerances": {"interrupt_latency_us": 1.0},
                }
        return manifest

    def test_default_template_is_blocked(self):
        report = validate_manifest(self.template, self.root, "functional")
        self.assertEqual("BLOCKED", report["verdict"])
        self.assertTrue(all(item["verdict"] == "BLOCKED" for item in report["subsystems"].values()))

    def test_complete_synthetic_fixture_is_functionally_ready(self):
        report = validate_manifest(self._complete(), self.root, "functional")
        self.assertEqual("READY", report["verdict"])
        self.assertTrue(all(item["verdict"] == "READY" for item in report["subsystems"].values()))

    def test_synthetic_fixture_cannot_satisfy_full_physical(self):
        report = validate_manifest(
            self._complete(evidence_class="synthetic_fixture", physical=True),
            self.root,
            "full-physical",
        )
        self.assertEqual("BLOCKED", report["verdict"])
        self.assertTrue(any("synthetic evidence" in error for error in report["errors"]))

    def test_missing_capability_and_tampered_artifact_are_blocked(self):
        manifest = self._complete()
        entry = manifest["subsystems"]["netc"]
        entry["provided_capabilities"].pop()
        (self.root / entry["artifact"]["path"]).write_bytes(b"tampered")
        report = validate_manifest(manifest, self.root, "functional")
        self.assertEqual("BLOCKED", report["verdict"])
        self.assertTrue(any("mandatory capabilities missing" in error for error in report["errors"]))
        self.assertTrue(any("SHA-256 mismatch" in error for error in report["errors"]))

    def test_complete_production_schema_fixture_requires_and_hashes_all_evidence_files(self):
        manifest = self._complete(evidence_class="production", physical=True)
        report = validate_manifest(manifest, self.root, "full-physical")
        self.assertEqual("READY", report["verdict"])
        for item in report["subsystems"].values():
            self.assertEqual(5, len(item["physical_evidence_files"]))

        missing = self._complete(evidence_class="production", physical=True)
        file_record = missing["subsystems"]["usb"]["physical_evidence"]["comparison_report"]
        (self.root / file_record["path"]).unlink()
        blocked = validate_manifest(missing, self.root, "full-physical")
        self.assertEqual("BLOCKED", blocked["verdict"])
        self.assertTrue(any("comparison_report" in error for error in blocked["errors"]))


if __name__ == "__main__":
    unittest.main()
