# NXP i.MX 952 Engineering Digital Twin

This directory is the operator-facing entry point for the NXP i.MX 952 EVK virtual platform provided by this branch.

The platform is qualified for repeatable early software development, heterogeneous Cortex-A55/Cortex-M7 integration, firmware-service validation and interactive debugging. It is not a cycle-accurate replacement for the physical EVK and does not claim complete physical-hardware equivalence.

## Implemented platform scope

- 4x Cortex-A55 application cores
- Cortex-M7 real-time core with 256 KiB ITCM and 256 KiB DTCM
- GICv3 and per-core generic timers
- 2 GiB DDR window and SoC SRAM
- LPUART1
- A55 MU2 / SCMI System Manager endpoint
- M7 MU5 / SCMI System Manager endpoint
- SCMI Base, Power, Clock and Pinctrl subsets
- NXP vendor SCMI CPU protocol for M7 lifecycle control
- NXP SiP auxiliary-core lifecycle service at `0xC2000005`
- early-boot EdgeLock Enclave service subset
- LPI2C7 path with deterministic EVK Type-C controller behavior
- native USDHC1/2/3 controller models
- dual-endpoint MU7 A55 <-> M7 messaging
- deterministic A55/M7 firmware and Robot Framework regression tests

## Quick start

From the repository root, launch the heterogeneous lifecycle and shared-memory demo:

```bash
bash tools/imx952-digital-twin/run.sh demo
```

Launch the firmware-level MU7 request/response demo:

```bash
bash tools/imx952-digital-twin/run.sh mu7
```

On Windows PowerShell:

```powershell
./tools/imx952-digital-twin/run.ps1 demo
./tools/imx952-digital-twin/run.ps1 mu7
```

The scripts use `$ORIGIN`-relative paths, so they do not depend on the caller's working directory.

For the MU7 demo, enter `start` in the Renode Monitor. The expected evidence is:

```text
sysbus ReadDoubleWord 0x88020030  -> 0x600D7007
sysbus ReadDoubleWord 0x88020034  -> 0x4D3755AA
```

These values prove that real A55 and M7 instructions exchanged a request and response through the modeled MU7 peripheral.

## Qualification

Run the complete i.MX 952 regression suite:

```bash
bash tools/imx952-digital-twin/qualify.sh
```

Execution modes:

```bash
bash tools/imx952-digital-twin/qualify.sh auto
bash tools/imx952-digital-twin/qualify.sh local
bash tools/imx952-digital-twin/qualify.sh docker
```

`auto` uses a built Renode runtime from this repository when available and otherwise uses the official `antmicro/renode:nightly-dotnet` container. Set `RENODE_IMAGE` to pin a different approved image. The qualification log records the resolved Docker image ID for reproducibility.

Qualification targets:

```text
tests/platforms/NXP_IMX952.robot
tests/platforms/NXP_IMX952_MU7_Firmware.robot
```

The GitHub Actions workflow `.github/workflows/imx952-digital-twin.yml` validates all Intel HEX fixtures, runs both Robot suites in a clean official Renode runtime, verifies the operator entry points and preserves `imx952-qualification.log` as an artifact.

## Supported engineering use cases

| Use case | Status |
|---|---|
| A55 bare-metal execution | Supported |
| M7 bare-metal execution | Supported |
| A55/M7 shared-memory interaction | Supported |
| A55-controlled M7 prepare/start/stop through NXP SiP | Supported |
| A55-controlled M7 lifecycle through NXP SCMI CPU | Supported |
| A55 SCMI System Manager access | Supported subset |
| M7 SCMI System Manager access and response signaling | Supported subset |
| ELE early-boot interactions | Supported subset |
| A55/M7 MU register-level messaging | Supported |
| A55/M7 firmware-level MU request/response | Supported |
| deterministic regression testing | Supported |
| interactive firmware debugging | Supported |
| full Boot ROM and signed-container boot chain | Not implemented |
| complete ELE/System Manager firmware surface | Not implemented |
| complete NETC/PCIe/USB/GPU/NPU multimedia model | Not implemented |
| physical timing/performance equivalence | Out of scope for this release |

## Main entry points

- Platform: `platforms/boards/nxp_imx952_evk.repl`
- Base script and NXP SiP service: `scripts/single-node/nxp_imx952_evk.resc`
- Heterogeneous lifecycle demo: `scripts/single-node/nxp_imx952_evk_heterogeneous_demo.resc`
- Firmware-level MU7 demo: `scripts/single-node/nxp_imx952_evk_mu7_firmware_demo.resc`
- Core regression suite: `tests/platforms/NXP_IMX952.robot`
- Firmware-level MU7 suite: `tests/platforms/NXP_IMX952_MU7_Firmware.robot`

## Application and firmware integration

1. Load the A55 ELF, HEX or binary into the DDR or SRAM address expected by the software.
2. Set the A55 reset/entry address when the image format does not provide it automatically.
3. Load the M7 image into ITCM/DTCM or another modeled memory region.
4. Release the M7 through the modeled NXP SiP service or NXP SCMI CPU protocol when validating the production lifecycle flow.
5. Use MU7 or shared memory for heterogeneous communication.
6. Add every repeatable workload to a Robot suite and preserve the exact firmware identity and Renode runtime image ID.

A full NXP Boot ROM, signed boot-container, DDR-training and production secure-boot chain is deliberately not claimed until the required firmware artifacts, security backend and hardware-correlated evidence are available.

## Qualified status

**Qualified for the documented professional engineering scope on July 16, 2026.**

The clean-runtime GitHub Actions qualification passed with **9/9 deterministic tests**:

1. 4x Cortex-A55 plus Cortex-M7 shared-memory execution
2. real A55 `SMC 0xC2000005` NXP SiP M7 lifecycle and firmware execution
3. A55 MU2/SCMI Base, Clock and Power behavior
4. M7 MU5/SCMI Base, Clock and response signaling
5. NXP SCMI CPU reset-vector/start/state/stop control of the modeled M7
6. ELE identity, fuse and firmware-status early-boot subset
7. LPI2C7 EVK Type-C identity and unknown-device NACK behavior
8. bidirectional MU7 register and interrupt signaling
9. real A55 and M7 firmware request/response through MU7

The qualification also validated Intel HEX checksums, Linux and Windows launchers, the qualification launcher, operator documentation and both interactive demo entry points.

This qualification applies only to the support matrix above. It does not imply complete SoC peripheral coverage, production secure-boot equivalence, physical timing correlation or cycle accuracy.
