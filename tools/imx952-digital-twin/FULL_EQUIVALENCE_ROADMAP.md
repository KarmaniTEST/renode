# i.MX952 Full Physical-Equivalence Digital Twin Program

## Objective

Evolve the current qualified i.MX952 engineering digital twin into a layered digital twin that can reproduce the observable behavior of the target physical hardware across boot, security, system management, networking, high-speed I/O, accelerators and timing.

The target is not merely to boot the same software. The target is measurable equivalence against a physical i.MX952 reference board for the supported configuration.

## Definition of physical-hardware equivalence

A subsystem is considered equivalent only when all applicable gates pass:

1. **Architectural equivalence**: documented address map, registers, reset values, access permissions, interrupts, clocks, resets, DMA and memory visibility match the reference hardware.
2. **Firmware/API equivalence**: the same production firmware, commands, status codes, error paths and lifecycle transitions execute without simulation-only patches.
3. **Protocol equivalence**: externally visible transactions and ordering match physical hardware within an explicitly defined tolerance.
4. **Boot-trace equivalence**: production boot artifacts execute through the same boot stages and expose equivalent externally observable state transitions.
5. **Timing equivalence**: latency, throughput, arbitration and timeout behavior match silicon within a documented tolerance and workload envelope.
6. **Regression equivalence**: the same automated test stimulus runs against both the digital twin and the physical board and produces equivalent verdicts and comparable traces.

No subsystem may be marked `FULL_EQUIVALENCE` solely because software boots or a happy-path test passes.

## Target architecture

The final solution is a **hybrid digital twin**, not a Renode-only model.

### Layer A — Renode orchestration and deterministic functional platform

Use Renode for:

- Cortex-A55 and Cortex-M7 software execution
- memory map and interrupt topology
- deterministic peripheral behavior where register-level models are sufficient
- Robot Framework regression orchestration
- fault injection, snapshots, observability and test automation

### Layer B — high-fidelity firmware and security services

Use the real production binaries when legally and technically available, or validated protocol-accurate models where direct execution is impossible:

- Boot ROM / ROM API surface
- EdgeLock Enclave services
- System Manager firmware and SCMI services
- secure boot, lifecycle, fuse, key and authentication flows
- reset, clock, power and domain transitions

### Layer C — detailed peripheral models

Develop or integrate detailed models for:

- NETC Ethernet switch/controller complex
- PCIe
- USB controller and PHY-visible behavior
- storage and DMA paths
- IOMMU/SMMU interactions
- clock/reset/power domains that affect software-visible behavior

### Layer D — accelerator execution models

GPU and NPU equivalence require accelerator-specific execution models or vendor-backed execution paths.

Possible implementations, selected per available IP access:

- vendor SystemC/TLM model
- RTL or Verilator co-simulation
- FPGA/emulation-backed model
- remote execution proxy to a physical accelerator with deterministic transaction capture
- validated functional model plus a separately calibrated timing model

A stubbed register model is not sufficient for `FULL_EQUIVALENCE`.

### Layer E — timing and performance model

Cycle-accurate or cycle-correlated behavior requires a timing backend beyond ordinary instruction-accurate functional emulation.

The timing architecture must support:

- CPU/interconnect latency model
- cache and memory hierarchy effects
- DDR latency/bandwidth model
- bus arbitration and contention
- DMA concurrency
- peripheral service latency
- interrupt latency
- NETC packet-path timing
- USB/PCIe transfer timing
- GPU/NPU execution timing
- clock and power-state dependent performance

Where exact cycle accuracy is unavailable, the model must declare the achieved tolerance and the validated workload envelope instead of claiming exact equivalence.

## Work packages

### WP0 — Golden physical reference and observability

**Goal:** establish the physical board as the comparison oracle.

Deliverables:

- fixed board revision and SoC revision
- fixed boot media and firmware baseline
- fixed BSP/U-Boot/Linux/RTOS versions
- JTAG and trace access where available
- UART, network and external bus capture
- power/reset/clock observation strategy
- register snapshot tooling
- timestamped event trace format
- automated hardware runner

Exit criteria:

- the same test definition can target `digital_twin` and `physical_board`
- every future equivalence claim has a reproducible hardware reference result

### WP1 — Boot ROM equivalence

**Goal:** execute the production boot flow without simulation-only shortcuts.

Scope:

- reset vector and initial CPU state
- boot source selection
- ROM-visible memory map
- boot container parsing
- authentication and image loading interactions
- ROM API calls used by production software
- handoff to the next boot stage
- boot failure paths and recovery behavior

Preferred implementation order:

1. execute an authorized ROM image/model if available
2. otherwise implement ROM-observable behavior from authoritative specifications and hardware traces
3. validate every modeled path against physical board traces

Exit criteria:

- production boot image boots without digital-twin-specific binary patching
- boot-stage sequence and externally visible state match hardware
- negative boot tests produce equivalent failure classifications

### WP2 — Complete ELE coverage

**Goal:** cover the complete ELE command surface required by the target product configuration.

Scope:

- command transport and response semantics
- lifecycle and state transitions
- identity and device information
- fuse access behavior
- secure boot/authentication requests
- key-management-visible behavior
- firmware status and versioning
- error codes, permissions and invalid-state behavior
- reset and persistence behavior

Exit criteria:

- command matrix coverage is 100% for the agreed target configuration
- positive, negative and lifecycle-transition tests match physical hardware

### WP3 — Complete System Manager coverage

**Goal:** reproduce the production System Manager interface and domain behavior.

Scope:

- complete SCMI protocol set used by the platform
- NXP vendor protocols
- clocks
- resets
- power domains
- pin control
- CPU lifecycle
- resource ownership and permissions
- domain dependencies
- asynchronous notifications
- timeout/error behavior

Exit criteria:

- production firmware executes without service stubs for the agreed configuration
- full request/response and state-transition matrix is hardware-correlated

### WP4 — NETC

**Goal:** model the complete software-visible NETC path required by the BSP and target use cases.

Scope:

- PCIe/ECAM-facing enumeration where applicable
- register blocks and reset values
- descriptor rings
- DMA
- interrupts/MSI/MSI-X where applicable
- buffer management
- MAC/PHY-facing behavior
- switch/bridge behavior required by the target
- VLAN, filtering and timestamping features required by the target
- TSN features required by the target
- error and congestion behavior

Implementation strategy:

- native Renode model for control plane where practical
- packet/datapath co-simulation when detailed timing is required
- hardware trace correlation for descriptor and packet ordering

Exit criteria:

- production driver initializes unmodified
- required traffic suites pass identically on twin and hardware
- latency/throughput tolerance is documented and met

### WP5 — USB

**Goal:** reproduce controller, device/host mode and timing-sensitive behavior needed by production software.

Scope:

- controller register model
- DMA and descriptor behavior
- interrupts
- role switching if required
- enumeration
- endpoint behavior
- reset/suspend/resume
- error injection
- PHY-visible timing where required

Exit criteria:

- production USB stack and required devices enumerate without simulation patches
- protocol traces match hardware at the selected abstraction level

### WP6 — GPU

**Goal:** run the production GPU software stack through a real execution-capable backend.

Minimum acceptable approaches:

- vendor GPU virtual model
- RTL/SystemC model
- hardware-backed remote execution proxy

Required coverage:

- driver initialization
- MMU/IOMMU interaction
- command submission
- interrupts/fences
- memory sharing
- representative rendering/compute workloads
- fault and reset behavior

Exit criteria:

- production driver and user-space stack execute unmodified for the target configuration
- output correctness is bit-exact where deterministic, otherwise tolerance-defined
- timing is correlated against hardware for selected workloads

### WP7 — NPU

**Goal:** execute the production NPU runtime and representative neural workloads through a real execution-capable backend.

Required coverage:

- firmware/runtime initialization
- memory mapping and DMA
- command submission
- synchronization and interrupts
- supported operator execution
- fault/reset behavior
- model output validation

Exit criteria:

- production runtime executes unmodified for the target configuration
- selected model outputs match hardware according to numerical tolerance
- inference latency and throughput are hardware-correlated

### WP8 — Cycle-accurate / cycle-correlated timing

**Goal:** add a timing model that is validated against silicon rather than assuming functional-emulator time equals hardware time.

Approach:

1. define timing observables and tolerances per subsystem
2. capture golden silicon measurements
3. build detailed timing models for CPU, interconnect, memory and high-impact peripherals
4. co-simulate RTL/SystemC/FPGA models for blocks requiring cycle detail
5. calibrate and continuously regress against the physical board

Required metrics:

- boot-stage duration
- interrupt latency distribution
- memory-access latency and bandwidth
- DMA latency and concurrency
- packet latency and throughput
- storage and USB transfer timing
- GPU workload duration
- NPU inference latency
- clock/power-state transition timing

Exit criteria:

- each claimed timing domain has a numerical tolerance and golden measurement set
- regression fails when correlation moves outside tolerance

## Equivalence matrix

Each subsystem must carry one explicit status:

- `NOT_MODELED`
- `FUNCTIONAL_MODEL`
- `PROTOCOL_EQUIVALENT`
- `FIRMWARE_EQUIVALENT`
- `TIMING_CORRELATED`
- `CYCLE_ACCURATE`
- `FULL_EQUIVALENCE`

The repository must maintain a machine-readable matrix containing:

- subsystem
- model backend
- required proprietary dependency, if any
- test count
- hardware-correlated test count
- functional coverage
- protocol coverage
- timing tolerance
- current status
- known deviations

## Test architecture

Every equivalence test should support two backends:

```text
same stimulus
    |
    +--> digital twin --> normalized trace/result
    |
    +--> physical board --> normalized trace/result

normalized comparison --> pass/fail + deviation report
```

Required artifacts per run:

- software versions
- firmware hashes
- board/SoC revision
- digital-twin commit
- test stimulus
- UART/log output
- register snapshots
- transaction traces where applicable
- timing measurements
- normalized comparison report

## Program gates

### Gate 1 — Full boot-chain fidelity

- production boot artifacts run without twin-specific patches
- Boot ROM observable flow correlated
- ELE and System Manager services required for boot covered

### Gate 2 — Full BSP peripheral bring-up

- production BSP boots
- all required production drivers initialize
- no required device is represented by a placeholder register stub

### Gate 3 — Accelerator-capable twin

- GPU production stack executes representative workloads
- NPU production runtime executes representative models

### Gate 4 — Hardware correlation

- automated twin-vs-board differential regression in CI/lab pipeline
- protocol and state equivalence for all claimed blocks

### Gate 5 — Timing equivalence

- agreed timing domains meet numerical correlation targets
- cycle-accurate claims restricted to blocks with a cycle-accurate backend

### Gate 6 — Full-equivalence release

A release may be labeled `FULL_PHYSICAL_EQUIVALENCE` only when:

- all target subsystems are at the required equivalence level
- no production-path dependency is silently stubbed
- all agreed hardware differential tests pass
- all timing claims have measured tolerances
- external proprietary model/firmware dependencies are reproducibly versioned and available to authorized users

## Immediate next implementation sequence

1. Build the machine-readable equivalence matrix and mark the current qualified model honestly.
2. Build the physical-board differential test harness.
3. Capture golden boot traces and define the exact production boot artifact set.
4. Close Boot ROM, ELE and System Manager gaps required by the production boot flow.
5. Implement NETC control/data path required by the production BSP.
6. Add USB and remaining BSP-critical peripherals.
7. Integrate an execution-capable GPU backend.
8. Integrate an execution-capable NPU backend.
9. Add SystemC/RTL/FPGA timing backends for timing-critical blocks.
10. Calibrate against silicon and enforce correlation thresholds in regression.

## Non-negotiable external dependencies

True physical equivalence may require artifacts that cannot be reconstructed reliably from a public functional specification alone, including some combination of:

- exact SoC revision documentation
- authorized Boot ROM image or executable reference model
- complete ELE/System Manager protocol definitions or production firmware access
- GPU/NPU vendor models or hardware-backed execution access
- detailed interconnect/memory timing information
- physical reference boards and trace access

If an exact proprietary implementation is unavailable, the repository must state the resulting limitation explicitly rather than relabeling a functional approximation as full equivalence.

## Current program baseline

The starting point is the qualified `imx952-a55-m7-support` branch. Its existing A55/M7, SCMI subset, NXP M7 lifecycle, ELE subset, LPI2C7, USDHC and MU7 regression coverage becomes the functional baseline for this program.

The next milestone is **Gate 1: production boot-chain fidelity plus a hardware differential harness**.
