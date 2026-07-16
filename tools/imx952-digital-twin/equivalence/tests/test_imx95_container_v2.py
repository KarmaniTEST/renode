from __future__ import annotations

import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parse_imx95_container_v2 import (  # noqa: E402
    CONTAINER_HEADER,
    IMAGE_DESCRIPTOR,
    SIGNATURE_HEADER,
    inspect_file,
    parse_container,
)


class Imx95ContainerV2Tests(unittest.TestCase):
    def _build_container(self, *, tamper=False, malformed_length=False):
        container_offset = 0x400
        image_payloads = [b"ATF-PAYLOAD-0001", b"UBOOT-PAYLOAD-02"]
        destinations = [0x8A200000, 0x90200000]
        entries = destinations
        data_offsets = [0x400, 0x500]
        num_images = len(image_payloads)
        sig_offset = 0x10 + num_images * 0x80
        length = sig_offset + 0x10
        if malformed_length:
            length += 1

        file_data = bytearray(0xA00)
        header = CONTAINER_HEADER.pack(
            2,
            length,
            0x87,
            0,
            1,
            0,
            num_images,
            sig_offset,
            0,
        )
        file_data[container_offset:container_offset + len(header)] = header

        for index, (payload, destination, entry, relative_offset) in enumerate(
            zip(image_payloads, destinations, entries, data_offsets)
        ):
            digest = hashlib.sha384(payload).digest()
            stored_hash = digest + b"\0" * (64 - len(digest))
            descriptor = IMAGE_DESCRIPTOR.pack(
                relative_offset,
                len(payload),
                destination,
                entry,
                0x103,
                0,
                stored_hash,
                b"\0" * 32,
            )
            descriptor_offset = container_offset + 0x10 + index * 0x80
            file_data[descriptor_offset:descriptor_offset + len(descriptor)] = descriptor
            absolute_offset = container_offset + relative_offset
            file_data[absolute_offset:absolute_offset + len(payload)] = payload

        signature = SIGNATURE_HEADER.pack(0, 16, 0x90, 0, 0, 0, 0, 0)
        signature_absolute = container_offset + sig_offset
        file_data[signature_absolute:signature_absolute + len(signature)] = signature

        if tamper:
            file_data[container_offset + data_offsets[1]] ^= 0xFF
        return bytes(file_data), container_offset

    def _write_temp(self, content):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "container.img"
        path.write_bytes(content)
        return directory, path

    def test_exact_container_and_required_stages_pass(self):
        content, offset = self._build_container()
        directory, path = self._write_temp(content)
        self.addCleanup(directory.cleanup)
        report = inspect_file(path, [offset], ["ATF", "U_BOOT"])
        self.assertEqual("PASS", report["verdict"])
        self.assertEqual("READY_FOR_EXECUTION", report["execution_readiness"])
        self.assertEqual(["ATF", "U_BOOT"], report["discovered_stages"])
        self.assertTrue(all(image["hash_match"] for image in report["containers"][0]["images"]))

    def test_auto_scan_finds_aligned_container(self):
        content, _offset = self._build_container()
        directory, path = self._write_temp(content)
        self.addCleanup(directory.cleanup)
        report = inspect_file(path, None, ["ATF"])
        self.assertEqual("PASS", report["verdict"])
        self.assertEqual("0x400", report["containers"][0]["offset"])

    def test_tampered_image_fails_hash_gate(self):
        content, offset = self._build_container(tamper=True)
        directory, path = self._write_temp(content)
        self.addCleanup(directory.cleanup)
        report = inspect_file(path, [offset], ["ATF", "U_BOOT"])
        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("hash mismatch" in error for error in report["errors"]))

    def test_missing_required_stage_fails_readiness(self):
        content, offset = self._build_container()
        directory, path = self._write_temp(content)
        self.addCleanup(directory.cleanup)
        report = inspect_file(path, [offset], ["TEE"])
        self.assertEqual("FAIL", report["verdict"])
        self.assertIn("required pinned stages missing: ['TEE']", report["errors"])

    def test_malformed_exact_header_length_fails(self):
        content, offset = self._build_container(malformed_length=True)
        directory, path = self._write_temp(content)
        self.addCleanup(directory.cleanup)
        with path.open("rb") as handle:
            report = parse_container(handle, path.stat().st_size, offset)
        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(any("header length" in error for error in report["errors"]))

    def test_no_container_fails_closed(self):
        directory, path = self._write_temp(b"\0" * 0x1000)
        self.addCleanup(directory.cleanup)
        report = inspect_file(path)
        self.assertEqual("FAIL", report["verdict"])
        self.assertIn(
            "no structurally valid B0 container-v2 header found on 0x400 boundaries",
            report["errors"],
        )


if __name__ == "__main__":
    unittest.main()
