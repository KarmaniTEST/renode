#!/usr/bin/env python3
"""Create an explicit synthetic B0 container fixture for CI execution-plan tests.

The output is never production evidence. It exists only to prove parser,
readiness, range loading and CPU-halt behavior deterministically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from parse_imx95_container_v2 import CONTAINER_HEADER, IMAGE_DESCRIPTOR, SIGNATURE_HEADER

ATF_PAYLOAD = b"ATF-FIXTURE-IMX952\0"
UBOOT_PAYLOAD = b"UBOOT-FIXTURE-IMX952\0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_container(container_offset: int) -> bytes:
    images = [
        (ATF_PAYLOAD, 0x8A200000, 0x8A200000, 0x400),
        (UBOOT_PAYLOAD, 0x90200000, 0x90200000, 0x500),
    ]
    num_images = len(images)
    sig_offset = 0x10 + num_images * 0x80
    length = sig_offset + 0x10
    total_size = container_offset + 0x600
    output = bytearray(total_size)
    output[container_offset:container_offset + 0x10] = CONTAINER_HEADER.pack(
        2, length, 0x87, 0, 1, 0, num_images, sig_offset, 0
    )

    for index, (payload, destination, entry, relative_offset) in enumerate(images):
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
        output[descriptor_offset:descriptor_offset + 0x80] = descriptor
        absolute_offset = container_offset + relative_offset
        output[absolute_offset:absolute_offset + len(payload)] = payload

    signature = SIGNATURE_HEADER.pack(0, 16, 0x90, 0, 0, 0, 0, 0)
    absolute_signature = container_offset + sig_offset
    output[absolute_signature:absolute_signature + 0x10] = signature
    return bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    args.root.mkdir(parents=True, exist_ok=True)
    files = {
        "flash.bin": build_container(0x400),
        "mx952b0-ahab-container.img": build_container(0),
        "u-boot-atf-container.img": build_container(0),
        "a55-oei-ddrfw.bin": b"A55-OEI-DDR-SYNTHETIC-FIXTURE\0",
        "u-boot-spl.bin": b"SPL-SYNTHETIC-FIXTURE\0",
        "bl31.bin": ATF_PAYLOAD,
        "u-boot.bin": UBOOT_PAYLOAD,
    }
    for name, content in files.items():
        (args.root / name).write_bytes(content)

    artifacts = [
        {
            "name": "final_boot_image", "path": "flash.bin", "required": True,
            "sha256": sha256(args.root / "flash.bin"),
            "container_validation": {"required_stages": ["ATF", "U_BOOT"]},
        },
        {
            "name": "ahab_container", "path": "mx952b0-ahab-container.img", "required": True,
            "sha256": sha256(args.root / "mx952b0-ahab-container.img"),
            "container_validation": {"offsets": ["0x0"], "required_stages": []},
        },
        {
            "name": "u_boot_atf_container", "path": "u-boot-atf-container.img", "required": True,
            "execution_source": True,
            "sha256": sha256(args.root / "u-boot-atf-container.img"),
            "container_validation": {"offsets": ["0x0"], "required_stages": ["ATF", "U_BOOT"]},
        },
        {
            "name": "a55_oei_ddr", "path": "a55-oei-ddrfw.bin", "required": True,
            "sha256": sha256(args.root / "a55-oei-ddrfw.bin"),
        },
        {
            "name": "u_boot_spl", "path": "u-boot-spl.bin", "required": True,
            "load_address": "0x20480000", "sha256": sha256(args.root / "u-boot-spl.bin"),
        },
        {
            "name": "arm_trusted_firmware", "path": "bl31.bin", "required": True,
            "load_address": "0x8A200000", "sha256": sha256(args.root / "bl31.bin"),
        },
        {
            "name": "u_boot", "path": "u-boot.bin", "required": True,
            "load_address": "0x90200000", "sha256": sha256(args.root / "u-boot.bin"),
        },
    ]
    manifest = {
        "schema_version": 2,
        "evidence_class": "synthetic_fixture",
        "target": {"soc": "i.MX952", "revision": "B0", "board": "i.MX952 EVK"},
        "container_version": 2,
        "source_baseline": {"imx_mkimage_commit": "1b577853ae1afe1f26cdef27548da52fb424af48"},
        "artifacts": artifacts,
        "fixture_expected_words": {
            "ATF": "0x2D465441",
            "U_BOOT": "0x4F4F4255"
        },
        "qualification_boundary": "Synthetic parser/loader fixture only; never production boot evidence."
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": "PASS", "manifest": str(args.manifest), "root": str(args.root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
