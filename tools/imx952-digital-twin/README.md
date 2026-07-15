# NXP i.MX 952 Digital Twin

This directory provides the operator-facing entry point for the experimental NXP i.MX 952 EVK virtual platform in this branch.

The goal is a repeatable engineering digital twin for early software development, heterogeneous A55/M7 integration and firmware-service validation. It is not a cycle-accurate replacement for the physical EVK.

## Implemented platform scope

- 4x Cortex-A55 application cores
- Cortex-M7 real-time core with ITCM and DTCM
- GICv3 and generic timers
- 2 GiB DDR window and SoC SRAM
- LPUART1
- A55 MU2 / SCMI System Manager endpoint
- M7 MU5 / SCMI System Manager endpoint
- SCMI Base, Power, Clock and Pinctrl subsets
- NXP vendor SCMI CPU protocol for M7 lifecycle control
- NXP SiP auxiliary-core lifecycle service
- early-boot EdgeLock Enclave service subset
- LPI2C7 path with deterministic EVK Type-C controller behavior
- USDHC1/2/3 controller models
- dual-endpoint MU7 A55 <-> M7 messaging
- deterministic A55/M7 firmware and Robot Framework regression tests

## Quick start

From the repository root:

```bash
bash tools/imx952-digital-twin/run.sh demo
```

On Windows PowerShell:

```powershell
./tools/imx952-digital-twin/run.ps1 demo
```

The demo loads deterministic A55 and M7 firmware and prepares the heterogeneous lifecycle scenario. Use the Renode Monitor to run, inspect memory and debug both processing domains.

## Qualification

Run the complete i.MX 952 regression suite:

```bash
bash tools/imx952-digital-twin/qualify.sh
```

The script supports three execution modes:

```bash
bash tools/imx952-digital-twin/qualify.sh auto
bash tools/imx952-digital-twin/qualify.sh local
bash tools/imx952-digital-twin/qualify.sh docker
```

`auto` uses a locally installed `renode-test` when available and otherwise falls back to the official `antmicro/renode:nightly-dotnet` container.

The qualification target is:

```text
tests/platforms/NXP_IMX952.robot
```

The dedicated GitHub Actions workflow `.github/workflows/imx952-digital-twin.yml` runs the same suite for this branch and for changes touching the i.MX 952 model. Every CI attempt preserves `imx952-qualification.log` as a workflow artifact so failures can be diagnosed and reproduced.

## Supported engineering use cases

| Use case | Status |
|---|---|
| A55 bare-metal execution | Supported |
| M7 bare-metal execution | Supported |
| A55/M7 shared-memory interaction | Supported |
| A55-controlled M7 start/stop | Supported |
| A55 SCMI System Manager access | Supported subset |
| M7 SCMI System Manager access | Supported subset |
| ELE early-boot interactions | Supported subset |
| A55/M7 MU messaging | Supported |
| deterministic regression testing | Supported |
| interactive firmware debugging | Supported |
| full Boot ROM emulation | Not implemented |
| complete ELE/System Manager firmware surface | Not implemented |
| complete NETC/PCIe/USB/GPU/NPU multimedia model | Not implemented |
| cycle-accurate timing/performance | Out of scope |

## Main entry points

- Platform: `platforms/boards/nxp_imx952_evk.repl`
- Base script: `scripts/single-node/nxp_imx952_evk.resc`
- Heterogeneous demo: `scripts/single-node/nxp_imx952_evk_heterogeneous_demo.resc`
- Regression suite: `tests/platforms/NXP_IMX952.robot`

## Firmware integration

The current deterministic firmware is intentionally small and self-contained so that the digital twin can be qualified without external binary downloads.

For application integration:

1. Load the A55 ELF/HEX/BIN into the DDR or SRAM address expected by the software.
2. Set the A55 reset/entry address when the image format does not provide it automatically.
3. Load the M7 image into ITCM/DTCM or another modeled memory region.
4. Release the M7 through the modeled NXP SiP service or NXP SCMI CPU protocol when validating the production lifecycle flow.
5. Add the workload to `tests/platforms/NXP_IMX952.robot` or a dedicated Robot suite to keep the scenario reproducible.

A full NXP boot-container / Boot ROM chain is deliberately not claimed as supported until the missing boot services and devices are modeled and qualified end to end.

## Definition of ready-to-use for this branch

This branch is considered ready for engineering use when:

- the dedicated GitHub Actions qualification workflow is green;
- the complete `NXP_IMX952.robot` suite passes from a clean runtime;
- the demo starts with no manual repository edits;
- supported and unsupported hardware paths remain explicit in this document;
- any production firmware scenario added later has its own deterministic regression test.

Until the qualification workflow is green, treat the branch as a release candidate rather than a fully qualified digital twin.
