import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "qualification_gate.py"
spec = importlib.util.spec_from_file_location("qualification_gate", MODULE_PATH)
qualification_gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(qualification_gate)


class QualificationGateTests(unittest.TestCase):
    def test_baseline_requires_target_and_sources(self):
        errors = qualification_gate.validate_baseline({"target": {}})
        self.assertTrue(errors)

    def test_full_status_rejects_incomplete_subsystems(self):
        status = {
            "subsystems": [
                {"id": name, "status": "FULL_EQUIVALENCE"}
                for name in qualification_gate.MANDATORY_FULL_EQUIVALENCE[:-1]
            ]
        }
        errors = qualification_gate.validate_full_status(status)
        self.assertTrue(any("timing" in error for error in errors))

    def test_full_status_accepts_all_mandatory_subsystems(self):
        status = {
            "subsystems": [
                {"id": name, "status": "FULL_EQUIVALENCE"}
                for name in qualification_gate.MANDATORY_FULL_EQUIVALENCE
            ]
        }
        self.assertEqual(qualification_gate.validate_full_status(status), [])

    def test_report_requires_clean_pass(self):
        report = {
            "verdict": "PASS",
            "target_mismatches": [],
            "summary": {"required_failed": 0},
        }
        self.assertEqual(qualification_gate.validate_report(report), [])

    def test_report_rejects_required_failure(self):
        report = {
            "verdict": "FAIL",
            "target_mismatches": ["revision"],
            "summary": {"required_failed": 1},
        }
        self.assertGreaterEqual(len(qualification_gate.validate_report(report)), 3)


if __name__ == "__main__":
    unittest.main()
