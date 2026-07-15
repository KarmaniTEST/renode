import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "validate_boot_artifacts.py"
spec = importlib.util.spec_from_file_location("validate_boot_artifacts", MODULE_PATH)
validate_boot_artifacts = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validate_boot_artifacts)


class BootArtifactValidatorTests(unittest.TestCase):
    def test_required_artifacts_are_fingerprinted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "flash.bin").write_bytes(b"boot-image")
            manifest = {
                "target": {"soc": "i.MX952", "revision": "B0", "board": "i.MX952 EVK"},
                "container_version": 2,
                "artifacts": [
                    {"name": "final", "path": "flash.bin", "required": True}
                ],
            }
            report = validate_boot_artifacts.validate_manifest(manifest, root)
            self.assertEqual(report["verdict"], "PASS")
            self.assertEqual(len(report["artifacts"][0]["sha256"]), 64)

    def test_missing_required_artifact_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {
                "target": {"soc": "i.MX952", "revision": "B0", "board": "i.MX952 EVK"},
                "container_version": 2,
                "artifacts": [
                    {"name": "missing", "path": "missing.bin", "required": True}
                ],
            }
            report = validate_boot_artifacts.validate_manifest(manifest, Path(tmpdir))
            self.assertEqual(report["verdict"], "FAIL")

    def test_optional_artifact_may_be_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {
                "target": {"soc": "i.MX952", "revision": "B0", "board": "i.MX952 EVK"},
                "container_version": 2,
                "artifacts": [
                    {"name": "optional", "path": "optional.bin", "required": False}
                ],
            }
            report = validate_boot_artifacts.validate_manifest(manifest, Path(tmpdir))
            self.assertEqual(report["verdict"], "PASS")

    def test_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "flash.bin").write_bytes(b"actual")
            manifest = {
                "target": {"soc": "i.MX952", "revision": "B0", "board": "i.MX952 EVK"},
                "container_version": 2,
                "artifacts": [
                    {
                        "name": "final",
                        "path": "flash.bin",
                        "required": True,
                        "sha256": "0" * 64,
                    }
                ],
            }
            report = validate_boot_artifacts.validate_manifest(manifest, root)
            self.assertEqual(report["verdict"], "FAIL")
            self.assertTrue(any("SHA-256 mismatch" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
