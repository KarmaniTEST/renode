import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "collect_evidence.py"
spec = importlib.util.spec_from_file_location("collect_evidence", MODULE_PATH)
collect_evidence = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = collect_evidence
spec.loader.exec_module(collect_evidence)


class CollectorTests(unittest.TestCase):
    def test_collects_literals_regexes_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / "uart.log"
            log.write_text("STAGE: ROM\nSTAGE: OEI\nVALUE=0x2\n", encoding="utf-8")
            binary = root / "firmware.bin"
            binary.write_bytes(b"abc")
            plan_path = root / "plan.json"
            plan = {
                "schema_version": 1,
                "name": "unit-plan",
                "target": {
                    "kind": "physical_board",
                    "soc": "i.MX952",
                    "revision": "B0",
                    "board": "i.MX952 EVK"
                },
                "observations": [
                    {
                        "key": "literal",
                        "source": {"type": "literal", "value": 7}
                    },
                    {
                        "key": "stages",
                        "source": {
                            "type": "text_regex_all",
                            "path": "uart.log",
                            "pattern": "^STAGE: (.+)$"
                        }
                    },
                    {
                        "key": "value",
                        "source": {
                            "type": "text_regex",
                            "path": "uart.log",
                            "pattern": "VALUE=(0x[0-9a-fA-F]+)",
                            "convert": "int"
                        }
                    },
                    {
                        "key": "hash",
                        "source": {"type": "sha256", "path": "firmware.bin"}
                    }
                ]
            }
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            result = collect_evidence.collect(plan, plan_path)
            self.assertEqual(result["observations"]["literal"]["value"], 7)
            self.assertEqual(result["observations"]["stages"]["value"], ["ROM", "OEI"])
            self.assertEqual(result["observations"]["value"]["value"], 2)
            self.assertEqual(
                result["observations"]["hash"]["value"],
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
            )

    def test_optional_collection_failure_is_recorded(self):
        plan = {
            "schema_version": 1,
            "target": {"kind": "digital_twin"},
            "observations": [
                {
                    "key": "optional",
                    "required": False,
                    "source": {
                        "type": "text_regex",
                        "path": "missing.log",
                        "pattern": "x=(.+)"
                    }
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = collect_evidence.collect(plan, Path(tmpdir) / "plan.json")
            self.assertIsNone(result["observations"]["optional"]["value"])
            self.assertIn("collection_error", result["observations"]["optional"])


if __name__ == "__main__":
    unittest.main()
