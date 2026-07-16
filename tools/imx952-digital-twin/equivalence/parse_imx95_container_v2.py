#!/usr/bin/env python3
"""Parse and verify pinned i.MX95 B0 AHAB container-v2 images.

The binary layouts and constants are derived from the pinned NXP imx-mkimage
sources. This tool verifies container structure, image ranges and descriptor
hashes. It does not authenticate signatures, execute Boot ROM, train DDR or
claim ATF/U-Boot handoff success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import BinaryIO, Dict, Iterable, List, Sequence, Tuple

CONTAINER_HEADER = struct.Struct("<BHBIHBBHH")
IMAGE_DESCRIPTOR = struct.Struct("<IIQQII64s32s")
SIGNATURE_HEADER = struct.Struct("<BHBHHHHI")

CONTAINER_TAG = 0x87
CONTAINER_VERSION = 0x02
CONTAINER_HEADER_SIZE = 0x10
IMAGE_DESCRIPTOR_SIZE = 0x80
SIGNATURE_HEADER_SIZE = 0x10
MAX_IMAGES = 16
SCAN_ALIGNMENT = 0x400

HASH_ALGORITHMS = {
    0x000: ("sha256", 32),
    0x100: ("sha384", 48),
    0x200: ("sha512", 64),
    0x300: ("sm3", 32),
}
HASH_FLAG_MASK = 0x300

PINNED_STAGES = {
    "ATF": 0x8A200000,
    "U_BOOT": 0x90200000,
    "TEE": 0x8C000000,
    "M7_A55_ALIAS": 0x303C0000,
    "M33_OEI": 0x1FFC0000,
}


def _read_exact(handle: BinaryIO, offset: int, size: int) -> bytes:
    handle.seek(offset)
    data = handle.read(size)
    if len(data) != size:
        raise ValueError(f"short read at 0x{offset:X}: wanted {size}, got {len(data)}")
    return data


def _digest_region(handle: BinaryIO, offset: int, size: int, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise ValueError(f"hash algorithm {algorithm} is unavailable") from exc
    handle.seek(offset)
    remaining = size
    while remaining:
        block = handle.read(min(1024 * 1024, remaining))
        if not block:
            raise ValueError(f"short image data at 0x{offset:X}")
        digest.update(block)
        remaining -= len(block)
    return digest.hexdigest()


def _candidate_offsets(handle: BinaryIO, file_size: int) -> List[int]:
    offsets: List[int] = []
    for offset in range(0, max(file_size - CONTAINER_HEADER_SIZE + 1, 0), SCAN_ALIGNMENT):
        header = _read_exact(handle, offset, CONTAINER_HEADER_SIZE)
        version, length, tag, _flags, _sw, _fuse, num_images, sig_offset, _reserved = \
            CONTAINER_HEADER.unpack(header)
        expected = CONTAINER_HEADER_SIZE + num_images * IMAGE_DESCRIPTOR_SIZE + SIGNATURE_HEADER_SIZE
        if (
            version == CONTAINER_VERSION
            and tag == CONTAINER_TAG
            and 0 < num_images <= MAX_IMAGES
            and length == expected
            and sig_offset == CONTAINER_HEADER_SIZE + num_images * IMAGE_DESCRIPTOR_SIZE
            and offset + length <= file_size
        ):
            offsets.append(offset)
    return offsets


def _stage_names(destination: int) -> List[str]:
    return [name for name, address in PINNED_STAGES.items() if destination == address]


def parse_container(handle: BinaryIO, file_size: int, offset: int) -> Dict[str, object]:
    errors: List[str] = []
    header_data = _read_exact(handle, offset, CONTAINER_HEADER_SIZE)
    version, length, tag, flags, sw_version, fuse_version, num_images, sig_offset, reserved = \
        CONTAINER_HEADER.unpack(header_data)

    expected_length = CONTAINER_HEADER_SIZE + num_images * IMAGE_DESCRIPTOR_SIZE + SIGNATURE_HEADER_SIZE
    if version != CONTAINER_VERSION:
        errors.append(f"container version is {version}, expected 2")
    if tag != CONTAINER_TAG:
        errors.append(f"container tag is 0x{tag:02X}, expected 0x87")
    if not 0 < num_images <= MAX_IMAGES:
        errors.append(f"num_images {num_images} is outside 1..{MAX_IMAGES}")
    if length != expected_length:
        errors.append(f"header length 0x{length:X} differs from exact 0x{expected_length:X}")
    expected_sig_offset = CONTAINER_HEADER_SIZE + num_images * IMAGE_DESCRIPTOR_SIZE
    if sig_offset != expected_sig_offset:
        errors.append(
            f"signature block offset 0x{sig_offset:X} differs from exact 0x{expected_sig_offset:X}"
        )
    if offset + max(length, expected_length) > file_size:
        errors.append("container header extends beyond the file")

    images: List[Dict[str, object]] = []
    ranges: List[Tuple[int, int, int]] = []
    safe_image_count = min(num_images, MAX_IMAGES)
    for index in range(safe_image_count):
        descriptor_offset = offset + CONTAINER_HEADER_SIZE + index * IMAGE_DESCRIPTOR_SIZE
        descriptor_data = _read_exact(handle, descriptor_offset, IMAGE_DESCRIPTOR_SIZE)
        image_offset, size, destination, entry, hab_flags, meta, stored_hash, iv = \
            IMAGE_DESCRIPTOR.unpack(descriptor_data)
        absolute_offset = offset + image_offset
        image_errors: List[str] = []

        if size == 0:
            image_errors.append("image size is zero")
        if absolute_offset < 0 or absolute_offset > file_size:
            image_errors.append("image offset is outside the file")
        if size > file_size or absolute_offset + size > file_size:
            image_errors.append("image range extends beyond the file")

        hash_selector = hab_flags & HASH_FLAG_MASK
        algorithm_info = HASH_ALGORITHMS.get(hash_selector)
        algorithm = None
        digest_length = 0
        digest = None
        expected_digest = None
        hash_match = False
        if algorithm_info is None:
            image_errors.append(f"unsupported hash selector 0x{hash_selector:X}")
        else:
            algorithm, digest_length = algorithm_info
            expected_digest = stored_hash[:digest_length].hex()
            if any(stored_hash[digest_length:]):
                image_errors.append("unused descriptor hash bytes are non-zero")
            if not image_errors or (
                absolute_offset <= file_size and size <= file_size and absolute_offset + size <= file_size
            ):
                try:
                    digest = _digest_region(handle, absolute_offset, size, algorithm)
                    hash_match = digest == expected_digest
                    if not hash_match:
                        image_errors.append(f"{algorithm} descriptor hash mismatch")
                except ValueError as exc:
                    image_errors.append(str(exc))

        if size and absolute_offset + size <= file_size:
            ranges.append((absolute_offset, absolute_offset + size, index))

        images.append({
            "index": index,
            "descriptor_offset": f"0x{descriptor_offset:X}",
            "relative_data_offset": f"0x{image_offset:X}",
            "absolute_data_offset": f"0x{absolute_offset:X}",
            "size_bytes": size,
            "destination": f"0x{destination:016X}",
            "entry": f"0x{entry:016X}",
            "stages": _stage_names(destination),
            "hab_flags": f"0x{hab_flags:08X}",
            "image_type": hab_flags & 0xF,
            "core_id": (hab_flags >> 4) & 0xF,
            "hash_selector": f"0x{hash_selector:03X}",
            "hash_algorithm": algorithm,
            "expected_hash": expected_digest,
            "calculated_hash": digest,
            "hash_match": hash_match,
            "meta": f"0x{meta:08X}",
            "iv": iv.hex(),
            "errors": image_errors,
        })
        errors.extend(f"image {index}: {message}" for message in image_errors)

    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if current[0] < previous[1]:
            errors.append(f"image ranges overlap: {previous[2]} and {current[2]}")

    signature = None
    signature_absolute = offset + sig_offset
    if signature_absolute + SIGNATURE_HEADER_SIZE <= file_size:
        signature_data = _read_exact(handle, signature_absolute, SIGNATURE_HEADER_SIZE)
        sig_version, sig_length, sig_tag, srk_offset, cert_offset, blob_offset, signature_offset, sig_reserved = \
            SIGNATURE_HEADER.unpack(signature_data)
        signature = {
            "offset": f"0x{signature_absolute:X}",
            "version": sig_version,
            "length": sig_length,
            "tag": f"0x{sig_tag:02X}",
            "srk_table_offset": f"0x{srk_offset:X}",
            "cert_offset": f"0x{cert_offset:X}",
            "blob_offset": f"0x{blob_offset:X}",
            "signature_offset": f"0x{signature_offset:X}",
            "reserved": f"0x{sig_reserved:08X}",
        }
    else:
        errors.append("signature block header extends beyond the file")

    return {
        "verdict": "PASS" if not errors else "FAIL",
        "offset": f"0x{offset:X}",
        "header": {
            "version": version,
            "length": length,
            "tag": f"0x{tag:02X}",
            "flags": f"0x{flags:08X}",
            "software_version": sw_version,
            "fuse_version": fuse_version,
            "num_images": num_images,
            "signature_block_offset": f"0x{sig_offset:X}",
            "reserved": f"0x{reserved:04X}",
        },
        "images": images,
        "signature_block_header": signature,
        "errors": errors,
    }


def inspect_file(path: Path, offsets: Sequence[int] | None = None,
                 required_stages: Iterable[str] = ()) -> Dict[str, object]:
    file_size = path.stat().st_size
    with path.open("rb") as handle:
        selected_offsets = list(offsets) if offsets is not None else _candidate_offsets(handle, file_size)
        containers = [parse_container(handle, file_size, offset) for offset in selected_offsets]

    errors: List[str] = []
    if not containers:
        errors.append("no structurally valid B0 container-v2 header found on 0x400 boundaries")
    for index, container in enumerate(containers):
        errors.extend(f"container {index}: {message}" for message in container["errors"])

    discovered = {
        stage
        for container in containers
        for image in container["images"]
        for stage in image["stages"]
    }
    required = set(required_stages)
    unknown = sorted(required - set(PINNED_STAGES))
    if unknown:
        errors.append(f"unknown required stages: {unknown}")
    missing = sorted(required - discovered)
    if missing:
        errors.append(f"required pinned stages missing: {missing}")

    return {
        "verdict": "PASS" if not errors else "FAIL",
        "classification": "STRUCTURAL_AND_HASH_VALIDATION_ONLY",
        "input": str(path.resolve()),
        "size_bytes": file_size,
        "source_contract": {
            "repository": "nxp-imx/imx-mkimage",
            "commit": "1b577853ae1afe1f26cdef27548da52fb424af48",
            "container_tag": "0x87",
            "container_version": 2,
            "image_descriptor_size": 128,
        },
        "required_stages": sorted(required),
        "discovered_stages": sorted(discovered),
        "execution_readiness": "READY_FOR_EXECUTION" if not errors and required else "NOT_ASSERTED",
        "containers": containers,
        "errors": errors,
        "qualification_boundary": [
            "Signature-block fields are parsed but cryptographic signatures are not authenticated.",
            "No Boot ROM, ELE, OEI, DDR training, ATF or U-Boot code is executed by this validator.",
            "A PASS proves pinned binary layout, ranges, hashes and requested destination-stage presence only.",
        ],
    }


def _parse_offset(value: str) -> int:
    return int(value, 0)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--offset", action="append", type=_parse_offset,
        help="Exact container offset; repeat for multiple containers. Default scans 0x400 boundaries.",
    )
    parser.add_argument(
        "--require-stage", action="append", choices=sorted(PINNED_STAGES), default=[],
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = inspect_file(args.input, args.offset, args.require_stage)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
