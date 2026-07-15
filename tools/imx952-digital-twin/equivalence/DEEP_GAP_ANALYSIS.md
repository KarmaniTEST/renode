# i.MX952 Full-Equivalence Deep Gap Analysis

## Executive conclusion

The current i.MX952 Renode branch is a qualified deterministic **functional engineering twin** for its documented A55/M7, SCMI subset, ELE subset, storage and messaging scenarios. It is not yet a physical-equivalence twin.

The shortest credible path to full qualification is not to add more optimistic stubs. It is to:

1. freeze one exact physical target and software baseline;
2. collect identical evidence from silicon and the twin;
3. close gaps in production boot and System Manager/security contracts first;
4. bring up the production BSP and use its failures to drive peripheral implementation;
5. integrate execution-capable backends for blocks that cannot be represented faithfully by a register-only model;
6. calibrate timing claims against silicon and keep exact-cycle claims separate from correlated timing claims.

## Pinned qualification target

- SoC: i.MX952
- Silicon revision: B0
- Board: i.MX952 EVK
- Primary target-specific configuration sources:
  - `nxp-imx/linux-imx` exact `imx952.dtsi`
  - `nxp-imx/imx-sm` exact generated `configs/mx952evk/config_scmi.h`
- Production image source:
  - `nxp-imx/imx-mkimage` i.MX95 image recipe with B0 revision selection

The exact commit pins are recorded in `AUTHORITATIVE_BASELINE.json`.

## 1. CPU, cache, interrupt and architectural topology

### Source contract

The exact i.MX952 Linux DTS exposes:

- four Cortex-A55 cores with MPIDR affinities `0x0`, `0x100`, `0x200`, `0x300`;
- private L1 caches and per-core L2 cache declarations;
- a shared L3 cache declaration;
- PSCI over SMC;
- GICv3 plus an ITS MSI controller.

### Current model

Implemented:

- four Cortex-A55 cores with correct affinity-style IDs;
- GICv3 distributor and redistributors;
- generic timers;
- Cortex-M7 execution domain.

Missing for physical-equivalence claims:

- modeled cache hierarchy effects;
- GIC ITS/MSI behavior;
- CPU PMU behavior needed by production performance tooling;
- silicon-correlated idle/PSCI latency and power-state behavior;
- cache/interconnect timing and contention.

### Qualification consequence

CPU instruction execution can remain in Renode for functional testing, but cache/interconnect and latency claims require a separate timing model or co-simulation/correlation layer.

## 2. Production Boot ROM and boot chain

### Source contract

The pinned NXP image build defines a production flow containing revision-dependent AHAB container behavior, OEI images, DDR training firmware, ATF, U-Boot and optional auxiliary-core images. For the selected B0 baseline the image recipe uses container version 2 and defines ATF at `0x8A200000`, U-Boot at `0x90200000`, M7 TCM alias `0x303C0000`, plus explicit OEI and DDR-firmware inputs.

### Current model

The current regression suite loads deterministic HEX images directly and manually sets CPU entry state for most scenarios. The platform file itself explicitly states that Boot ROM and populated boot media are future work.

### Missing implementation

- reset-time architectural state matching silicon;
- boot-mode/fuse/strap selection;
- boot-media discovery;
- AHAB container parsing and validation flow;
- ELE-mediated authentication path;
- OEI execution/handoff behavior;
- DDR training firmware interaction and trained-memory readiness;
- ATF handoff;
- U-Boot handoff;
- recovery/error paths;
- exact boot artifact hashes in evidence.

### First implementation rule

WP1 must be driven by a real production boot artifact set. A full-equivalence configuration must not replace ROM stages with manual `LoadELF`, `LoadHEX` or direct PC assignment.

## 3. System Manager / SCMI

### Exact target contract

The exact i.MX952 DTS exposes these SCMI protocol nodes to Linux:

- `0x11` Power
- `0x12` System Power
- `0x13` Performance
- `0x14` Clock
- `0x15` Sensor
- `0x19` Pinctrl
- `0x80` NXP LMM
- `0x81` NXP BBM
- `0x82` NXP CPU
- `0x84` NXP Misc

The NXP System Manager protocol source defines the broader family protocol namespace, including Reset, Voltage and FuSa, and states that supported protocols implement required messages while vendor protocols generally make their messages mandatory.

The exact generated i.MX952 EVK configuration defines separate agents rather than one flat server:

- M7 agent
- AP secure agent
- AP non-secure agent

Those agents have different permissions. The AP non-secure agent, for example, has explicit permissions to power domains and performance domains including GPU, NPU, VPU, camera, display, A55 and DRAM.

### Current model

The current Python System Manager implements only:

- Base `0x10`
- Power `0x11`
- Clock `0x14`
- Pinctrl `0x19`
- NXP CPU `0x82`

Base discovery currently advertises only four non-base protocols. The implementation selects a generic A55 or M7 agent name based mainly on window/channel count and does not implement the exact M7/AP-S/AP-NS permission model.

### Highest-priority fidelity gaps

1. Explicit agent identity and channel topology.
2. Permission enforcement derived from the exact generated target configuration.
3. System Power `0x12` complete mandatory contract.
4. Performance `0x13` complete mandatory contract with exact i.MX952 domains.
5. Sensor `0x15` contract.
6. NXP LMM `0x80`.
7. NXP BBM `0x81`.
8. NXP Misc `0x84`.
9. Correct notifications and P2A channels.
10. Exact names/attributes/IDs instead of synthetic `imx952-pd-N` and `imx952-clk-N` responses where the production contract defines them.

### Exact performance-domain baseline

The pinned i.MX952 System Manager source defines 12 device performance domains:

- 0 M33
- 1 WAKEUP
- 2 M7
- 3 DRAM
- 4 HSIO
- 5 NPU
- 6 NOC
- 7 A55
- 8 GPU
- 9 VPU
- 10 CAM
- 11 DISP

and four performance levels: PRK, LOW, NOM and ODV.

### Implementation rule

Do not advertise a protocol through Base discovery before its mandatory message contract and agent permissions are implemented. A broader but dishonest discovery response is worse than an explicitly incomplete model.

## 4. EdgeLock Enclave

### Current model

Current deterministic tests cover a subset including SoC information, a fuse read path and firmware status.

### Missing for full qualification

- complete command inventory for the selected production firmware baseline;
- exact request/response framing and status/error behavior;
- lifecycle states;
- boot authentication flows;
- key/fuse policy and denied paths;
- reset/recovery behavior;
- timing and concurrency where software-visible;
- physical-board differential traces.

### Architecture decision

Prefer execution of legally available production ELE firmware or an authorized executable model. Where that is impossible, protocol-accurate modeling must be derived from the production caller behavior and hardware traces and must remain labeled below full firmware equivalence until proven.

## 5. NETC

### Current model

No complete NETC model is present in the platform.

### Required layers

- MMIO/register contract;
- descriptor rings and DMA;
- interrupt/MSI path;
- MDIO/PHY behavior;
- Ethernet endpoint and switch datapath;
- queueing and timestamp behavior;
- TSN features required by the selected BSP/use cases;
- RPMsg/partitioned operation where used by the selected target configuration;
- production Linux driver bring-up;
- packet-by-packet differential evidence;
- latency/throughput correlation.

### Dependencies

GIC ITS/MSI, DMA coherency, memory ordering, clocks, power domains and System Manager permissions must be sufficiently correct before NETC can be called equivalent.

## 6. USB and PCIe / HSIO

### Current model

No full production USB or PCIe stack is modeled.

### Required layers

USB:

- controller registers;
- DMA and interrupts;
- host/device paths required by the target;
- Type-C role interaction;
- production driver behavior;
- protocol differential testing;
- timing correlation.

PCIe:

- root-complex configuration space and link state;
- MSI/MSI-X through ITS;
- DMA/IOMMU behavior as required;
- enumeration and error paths;
- production endpoint workloads;
- timing correlation where claimed.

## 7. GPU and NPU

### Current model

No execution-capable GPU or NPU backend is present.

### Full-equivalence requirement

A register stub is insufficient. At least one execution-capable backend is needed per accelerator:

- vendor executable virtual model;
- SystemC/TLM model;
- RTL/Verilator co-simulation;
- FPGA/emulation backend;
- hardware-backed accelerator proxy.

Qualification requires the production driver/runtime stack, memory and interrupt semantics, workload output comparison and timing correlation.

The selected i.MX952 System Manager source already shows that GPU and NPU are first-class power/performance-managed domains. Their System Manager behavior must therefore be implemented before accelerator qualification can be complete.

## 8. Timing and cycle accuracy

### Current state

The existing twin uses deterministic virtual execution and is suitable for functional regression. It is not a cycle-accurate full-SoC model.

### Required decomposition

Do not use one global “cycle accurate” label. Qualify timing by domain:

- CPU execution timing;
- cache hierarchy;
- interconnect/NOC;
- DDR;
- DMA;
- interrupt latency;
- NETC packet path;
- USB/PCIe;
- GPU;
- NPU.

Each domain must state:

- backend type;
- clock model;
- measured workloads;
- physical-board sample method;
- absolute/relative tolerance;
- validated operating envelope.

A block may be `TIMING_CORRELATED` without being `CYCLE_ACCURATE`. Only a backend that actually models the required cycles should receive the latter label.

## 9. Critical path and implementation order

### WP0 — Golden reference and differential harness — STARTED

Implemented on this branch:

- pinned authoritative baseline;
- exact target identity and source revisions;
- evidence collector for files, commands, UART/log parsing and artifact hashes;
- machine-readable hardware-vs-twin comparator;
- explicit numeric tolerances;
- B0 foundation comparison profile;
- physical EVK capture-plan template;
- source-derived System Manager contract;
- claim-status ledger;
- unit tests and CI integration.

Remaining WP0 blocker:

- capture the first real i.MX952 EVK B0 evidence set with exact board serial and production firmware hashes.

### WP1 — Production boot chain

Start from the first differential between the physical boot trace and the twin. Implement ROM/boot services in dependency order until the same production image reaches the same handoff points.

### WP2 — System Manager and ELE contract completion

Refactor System Manager around exact agents, permissions and mandatory protocol contracts. Expand ELE from the current subset using production boot and OS callers plus physical evidence.

### WP3 — Production BSP bring-up

Boot the selected production BSP without simulation-only patches. Turn every missing/incorrect device probe into a traceable model gap.

### WP4 — NETC, USB and PCIe

Implement in dependency order, including ITS/MSI, DMA and System Manager prerequisites.

### WP5 — GPU/NPU execution backends

Integrate execution-capable accelerator models or hardware proxies and qualify production workloads.

### WP6 — Timing/cycle qualification

Correlate each timing domain against silicon, then replace correlated models with cycle-accurate backends only where required and technically available.

## 10. Full qualification release gate

The program may produce a `FULL_PHYSICAL_EQUIVALENCE` release only when:

- the exact target baseline is frozen and reproducible;
- production boot artifacts execute through the required boot chain;
- all claimed System Manager and ELE contracts pass physical differential tests;
- all claimed production drivers operate without hidden simulation patches;
- NETC/USB/PCIe and accelerator claims have workload-level differential evidence;
- timing claims include explicit measured tolerances;
- every subsystem status in `EQUIVALENCE_STATUS.json` has the evidence required for its claimed maturity;
- CI can reproduce the digital-twin side and the lab pipeline can reproduce the physical-reference side.

Until then, the honest status is: **full-equivalence program in progress, with WP0 implementation active and the existing functional twin preserved as the stable engineering baseline.**
