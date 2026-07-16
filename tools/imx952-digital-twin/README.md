# NXP i.MX 952 Digital Twin

This directory is the operator-facing entry point for the NXP i.MX952 EVK digital twin program.

The repository now carries two intentionally separate execution profiles:

1. **Qualified engineering twin** — stable, deterministic and ready for professional software development within its documented scope.
2. **Full-equivalence candidate** — stricter source-derived System Manager behavior and evidence-driven qualification infrastructure used to progress toward physical-hardware equivalence.

The second profile is not labeled physically equivalent until the hardware-correlated release gate passes.

## Implemented engineering platform scope

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

## Full-equivalence candidate additions

The candidate profile adds a source-derived System Manager implementation without destabilizing the qualified engineering platform:

- M7, AP-S and AP-NS agent identities
- independent AP-S and AP-NS SMT channels
- source-derived power-domain IDs and permissions
- source-derived performance-domain IDs and permissions
- SCMI Power version 3.1
- SCMI System Power version 2.1
- SCMI Performance version 4.0
- SCMI Clock version 3.0
- source-derived AP-S/AP-NS/M7 permission regression tests
- authoritative source baseline pinned to exact NXP revisions
- physical-board evidence collector
- digital-twin vs hardware comparator
- production boot-artifact SHA-256 manifest validator
- fail-closed full-physical release gate

## Quick start

### Qualified engineering demo

```bash
bash tools/imx952-digital-twin/run.sh demo
```

### Qualified engineering platform

```bash
bash tools/imx952-digital-twin/run.sh platform
```

### Full-equivalence development candidate

```bash
bash tools/imx952-digital-twin/run.sh full-platform
```

On Windows PowerShell the engineering launch path remains:

```powershell
./tools/imx952-digital-twin/run.ps1 demo
```

The full candidate can be opened directly with:

```powershell
renode --console scripts/single-node/nxp_imx952_evk_full.resc
```

## Qualification

### Stable engineering qualification

```bash
bash tools/imx952-digital-twin/qualify.sh docker
```

This runs:

```text
tests/platforms/NXP_IMX952.robot
```

### Complete professional qualification package

Linux:

```bash
bash tools/imx952-digital-twin/qualify-full.sh docker engineering
```

Windows PowerShell:

```powershell
./tools/imx952-digital-twin/qualify-full.ps1 -RuntimeMode docker -QualificationMode engineering
```

This validates:

- equivalence framework unit tests
- authoritative source and target baseline
- strict release-gate behavior
- stable engineering regression suite
- full-equivalence System Manager candidate regression suite
- operator entry points
- clean official Renode nightly runtime execution

The Renode qualification targets are:

```text
tests/platforms/NXP_IMX952.robot
tests/platforms/NXP_IMX952_FULL_EQUIVALENCE.robot
```

## Full physical-equivalence qualification

Full physical qualification requires evidence from the exact pinned i.MX952 EVK B0 reference and the corresponding digital-twin run.

Linux:

```bash
export IMX952_REFERENCE_EVIDENCE=/path/to/physical-board.json
export IMX952_CANDIDATE_EVIDENCE=/path/to/digital-twin.json
bash tools/imx952-digital-twin/qualify-full.sh docker full-physical
```

Windows PowerShell:

```powershell
./tools/imx952-digital-twin/qualify-full.ps1 `
    -RuntimeMode docker `
    -QualificationMode full-physical `
    -ReferenceEvidence C:\evidence\physical-board.json `
    -CandidateEvidence C:\evidence\digital-twin.json
```

The full-physical gate checks:

- exact SoC, board and silicon-revision identity
- pinned production firmware identity
- physical-board vs twin evidence comparison
- zero required comparison failures
- zero target mismatches
- every mandatory subsystem at `FULL_EQUIVALENCE`
- no unresolved subsystem gates

If any of these conditions is missing, the release verdict is `BLOCKED` by design.

## Production boot artifact identity

Create a project-specific copy of:

```text
tools/imx952-digital-twin/equivalence/plans/imx952_evk_b0_boot_artifacts.template.json
```

Then validate and fingerprint the exact artifacts:

```bash
python3 tools/imx952-digital-twin/equivalence/validate_boot_artifacts.py \
    --manifest /path/to/boot-artifacts.json \
    --root /path/to/artifact-directory \
    --output /path/to/boot-artifact-report.json
```

The manifest covers the production-image baseline including AHAB, OEI/DDR, SPL, ATF, U-Boot and optional M7 firmware inputs. The resulting hashes are qualification evidence and must be identical between the physical-board and digital-twin campaign.

## Evidence collection and comparison

The common collector can consume files, UART/log captures, commands, SSH/lab-control wrappers and artifact hashes while emitting one normalized evidence format for both targets.

Core tools:

```text
tools/imx952-digital-twin/equivalence/collect_evidence.py
tools/imx952-digital-twin/equivalence/compare_evidence.py
tools/imx952-digital-twin/equivalence/qualification_gate.py
```

Pinned target and maturity state:

```text
tools/imx952-digital-twin/equivalence/AUTHORITATIVE_BASELINE.json
tools/imx952-digital-twin/equivalence/EQUIVALENCE_STATUS.json
```

## Supported use cases and qualification state

| Use case | Engineering twin | Full-equivalence candidate |
|---|---|---|
| A55 bare-metal execution | Qualified | Included |
| M7 bare-metal execution | Qualified | Included |
| A55/M7 shared-memory interaction | Qualified | Included |
| A55-controlled M7 start/stop | Qualified | Included |
| A55 SCMI access | Qualified subset | Source-derived AP-S/AP-NS candidate |
| M7 SCMI access | Qualified subset | Source-derived M7 candidate |
| SCMI System Power | Not in stable profile | Candidate implemented/tested |
| SCMI Performance | Not in stable profile | Candidate implemented/tested |
| ELE early-boot interactions | Qualified subset | Physical differential pending |
| deterministic regression testing | Qualified | Qualified infrastructure |
| production Boot ROM / AHAB / OEI / DDR chain | Not qualified | Evidence and artifact gates prepared |
| GIC ITS/MSI | Not modeled | Pending |
| NETC | Not modeled | Pending |
| USB | Not modeled | Pending |
| PCIe/HSIO | Not modeled | Pending |
| GPU execution backend | Not modeled | Pending vendor/co-simulation backend |
| NPU execution backend | Not modeled | Pending vendor/co-simulation backend |
| cycle/timing equivalence | Not claimed | Hardware correlation required |

## Main entry points

Engineering profile:

```text
platforms/boards/nxp_imx952_evk.repl
scripts/single-node/nxp_imx952_evk.resc
scripts/single-node/nxp_imx952_evk_heterogeneous_demo.resc
tests/platforms/NXP_IMX952.robot
```

Full-equivalence candidate:

```text
platforms/boards/nxp_imx952_evk_full.repl
scripts/single-node/nxp_imx952_evk_full.resc
scripts/pydev/nxp_imx952_system_manager_full.py
tests/platforms/NXP_IMX952_FULL_EQUIVALENCE.robot
```

## Qualified status

### Engineering twin

**Qualified for the documented engineering scope on 2026-07-15.**

The complete stable regression suite passed from a clean official Renode nightly runtime with 8/8 deterministic tests successful. The qualification covers A55/M7 execution and shared memory, the real A55 SiP SMC lifecycle path, A55 and M7 SCMI roles, NXP SCMI CPU control, ELE early-boot services, LPI2C7 and bidirectional MU7 messaging.

### Full-equivalence candidate

The source-derived System Manager candidate and its AP-S/AP-NS/M7 permission regression tests pass in the same clean-runtime CI gate together with the stable suite.

This is a **qualified development candidate**, not yet a `FULL_PHYSICAL_EQUIVALENCE` release. The remaining physical-equivalence claims are deliberately blocked until production boot-chain execution, complete ELE/System Manager coverage, GIC ITS/MSI, NETC, USB/PCIe, execution-capable GPU/NPU backends and silicon-correlated timing evidence are present.
