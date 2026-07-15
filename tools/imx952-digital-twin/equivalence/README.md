# i.MX952 Evidence-Driven Equivalence Framework

This directory implements WP0 of the full physical-equivalence program: establish a fixed physical i.MX952 EVK as the comparison oracle and make every equivalence claim reproducible.

## Principle

The digital twin is not the reference. The selected physical board, silicon revision and production firmware baseline are the reference.

A subsystem can move toward `FULL_EQUIVALENCE` only when the same observation keys are collected from both targets and the comparison profile passes.

## Files

- `AUTHORITATIVE_BASELINE.json` — pinned NXP source revisions and target identity.
- `EQUIVALENCE_STATUS.json` — evidence-gated maturity ledger for each subsystem.
- `collect_evidence.py` — converts target-specific files, commands and hashes into normalized evidence JSON.
- `compare_evidence.py` — compares physical reference evidence with digital-twin evidence.
- `profiles/imx952_evk_b0_foundation.json` — first B0 comparison contract.
- `plans/imx952_evk_b0_physical_reference.template.json` — physical-board capture template.
- `tests/` — dependency-free unit tests executed by qualification CI.

## Evidence schema

Both physical and virtual targets produce the same structure:

```json
{
  "schema_version": 1,
  "target": {
    "kind": "physical_board",
    "soc": "i.MX952",
    "revision": "B0",
    "board": "i.MX952 EVK"
  },
  "observations": {
    "boot.stage_sequence": {
      "value": ["ROM", "OEI", "ATF", "UBOOT"]
    },
    "timing.m7_release_us": {
      "value": 123.4,
      "unit": "us"
    }
  }
}
```

The target identity is part of the verdict. Evidence from a different silicon revision must not silently pass against the B0 profile.

## Collect physical evidence

Copy the template and replace board-specific connection information and capture paths:

```bash
cp tools/imx952-digital-twin/equivalence/plans/imx952_evk_b0_physical_reference.template.json \
   /tmp/imx952-physical-plan.json

python3 tools/imx952-digital-twin/equivalence/collect_evidence.py \
  --plan /tmp/imx952-physical-plan.json \
  --output evidence/physical/imx952-evk-b0.json
```

The collector supports:

- `literal` — pinned configuration or independently verified metadata;
- `sha256` — boot/firmware artifact identity;
- `text_regex` and `text_regex_all` — UART, trace and tool log parsing;
- `command_regex` and `command_regex_all` — local, SSH or lab-control commands;
- `command_json` — structured output from target-side probes.

A command source is an argv array, so a physical target can use `ssh`, a serial-console wrapper, a JTAG CLI, a power controller or another lab tool without coupling the evidence format to one transport.

## Collect digital-twin evidence

Create a second capture plan with:

```json
"kind": "digital_twin"
```

and point its sources at Renode logs, Robot-generated evidence, monitor commands or dedicated probe scripts. Observation keys must be identical to the physical plan.

## Compare

```bash
python3 tools/imx952-digital-twin/equivalence/compare_evidence.py \
  --reference evidence/physical/imx952-evk-b0.json \
  --candidate evidence/twin/imx952-evk-b0.json \
  --profile tools/imx952-digital-twin/equivalence/profiles/imx952_evk_b0_foundation.json \
  --output evidence/reports/imx952-evk-b0-report.json
```

Exit codes:

- `0` — all required equivalence rules pass;
- `1` — one or more required rules fail;
- `2` — invalid profile/evidence or collection input.

## First production qualification contract

The foundation profile starts with:

- production boot-stage order;
- B0 container version;
- ATF and U-Boot load addresses;
- M7 TCM alias;
- System Manager SCMI protocol inventory;
- M7 lifecycle sequence;
- ELE firmware status;
- optional boot and M7-release timing measurements with explicit tolerances.

These are only the first gates. Passing this profile does not mean the whole SoC is physically equivalent.

## Source-derived boot baseline

The pinned NXP `imx-mkimage` i.MX95 build currently defines, for the selected B0 baseline:

- container version `2`;
- ATF load address `0x8A200000`;
- U-Boot load address `0x90200000`;
- M7 TCM alias `0x303C0000`;
- OEI images and DDR firmware as explicit production image inputs.

The pinned NXP System Manager EVK configuration defines a much broader surface than the current Renode model, including logical machines, SCMI agents, clocks, resources, memory permissions, power domains and fault reactions. The exact configuration is therefore a qualification input, not background documentation.

## Immediate next implementation milestones

1. Add a digital-twin capture plan that emits the foundation observation keys automatically from Renode/Robot execution.
2. Add physical EVK capture adapters for UART, production SCMI inventory and ELE status.
3. Hash and record every production boot artifact used by both targets.
4. Execute the first hardware-vs-twin comparison and freeze the resulting reference evidence.
5. Begin WP1 Boot ROM work from the first failing boot-chain differential rather than adding unverified stubs.

## Claim policy

`EQUIVALENCE_STATUS.json` is the source of truth for claim maturity. A green Renode-only regression may demonstrate a stable functional model, but it cannot promote a subsystem to `FULL_EQUIVALENCE` without the required physical-reference and timing evidence.
