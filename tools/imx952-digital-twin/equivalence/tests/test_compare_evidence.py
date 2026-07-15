import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "compare_evidence.py"
spec = importlib.util.spec_from_file_location("compare_evidence", MODULE_PATH)
compare_evidence = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(compare_evidence)


def evidence(kind, observations, revision="B0"):
    return {
        "schema_version": 1,
        "target": {
            "kind": kind,
            "soc": "i.MX952",
            "revision": revision,
            "board": "i.MX952 EVK"
        },
        "observations": {
            key: value if isinstance(value, dict) and "value" in value else {"value": value}
            for key, value in observations.items()
        }
    }


class ComparatorTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "schema_version": 1,
            "name": "unit",
            "required_target": {
                "soc": "i.MX952",
                "revision": "B0",
                "board": "i.MX952 EVK"
            },
            "rules": [
                {"key": "exact", "kind": "exact"},
                {"key": "numeric", "kind": "numeric", "unit": "us", "abs_tolerance": 5},
                {"key": "set", "kind": "set"},
                {"key": "sequence", "kind": "sequence"},
                {"key": "optional", "kind": "exact", "required": False}
            ]
        }

    def test_passes_equivalent_observations(self):
        reference = evidence("physical_board", {
            "exact": 3,
            "numeric": {"value": 100, "unit": "us"},
            "set": ["base", "clock", "power"],
            "sequence": ["rom", "oei", "atf", "uboot"]
        })
        candidate = evidence("digital_twin", {
            "exact": 3,
            "numeric": {"value": 104, "unit": "us"},
            "set": ["power", "base", "clock"],
            "sequence": ["rom", "oei", "atf", "uboot"]
        })
        report = compare_evidence.compare_documents(reference, candidate, self.profile)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["summary"]["required_failed"], 0)

    def test_fails_required_mismatch(self):
        reference = evidence("physical_board", {
            "exact": 3,
            "numeric": {"value": 100, "unit": "us"},
            "set": ["base"],
            "sequence": ["rom", "uboot"]
        })
        candidate = evidence("digital_twin", {
            "exact": 4,
            "numeric": {"value": 100, "unit": "us"},
            "set": ["base"],
            "sequence": ["rom", "uboot"]
        })
        report = compare_evidence.compare_documents(reference, candidate, self.profile)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertGreater(report["summary"]["required_failed"], 0)

    def test_fails_target_revision_mismatch(self):
        reference = evidence("physical_board", {
            "exact": 3,
            "numeric": {"value": 100, "unit": "us"},
            "set": [],
            "sequence": []
        })
        candidate = evidence("digital_twin", {
            "exact": 3,
            "numeric": {"value": 100, "unit": "us"},
            "set": [],
            "sequence": []
        }, revision="A1")
        report = compare_evidence.compare_documents(reference, candidate, self.profile)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(report["target_mismatches"])

    def test_cli_writes_machine_readable_report(self):
        reference = evidence("physical_board", {
            "exact": 3,
            "numeric": {"value": 100, "unit": "us"},
            "set": [],
            "sequence": []
        })
        candidate = evidence("digital_twin", {
            "exact": 3,
            "numeric": {"value": 102, "unit": "us"},
            "set": [],
            "sequence": []
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ref_path = root / "reference.json"
            cand_path = root / "candidate.json"
            profile_path = root / "profile.json"
            report_path = root / "report.json"
            ref_path.write_text(json.dumps(reference), encoding="utf-8")
            cand_path.write_text(json.dumps(candidate), encoding="utf-8")
            profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
            rc = compare_evidence.main([
                "--reference", str(ref_path),
                "--candidate", str(cand_path),
                "--profile", str(profile_path),
                "--output", str(report_path),
                "--quiet"
            ])
            self.assertEqual(rc, 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
