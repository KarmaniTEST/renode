# Source-derived i.MX952 MU v2 + SCMI System Manager candidate.
#
# This model is intentionally separate from nxp_imx952_system_manager.py so the
# stable engineering twin can remain regression-compatible while the stricter
# physical-equivalence contract is developed and qualified.
#
# Implemented protocol surface in this candidate:
# - Base          0x10
# - Power         0x11, NXP SM version 3.1
# - System Power  0x12, NXP SM version 2.1
# - Performance   0x13, NXP SM version 4.0
# - Clock         0x14, NXP SM version 3.0
# - Pinctrl       0x19
# - NXP CPU       0x82 (M7 agent compatibility path)
#
# Agent mapping for the two A55-side SMT channels follows the generated
# mx952evk System Manager configuration:
#   local channel 0 -> AP-S  (global A2P channel 3, agent 1)
#   local channel 1 -> AP-NS (global A2P channel 5, agent 2)
# The one-channel M7 endpoint maps to agent 0.

from Antmicro.Renode.Core import EmulationManager
from Antmicro.Renode.Peripherals.CPU import RegisterValue

MU_PAR = 0x004
MU_GIER = 0x110
MU_GCR = 0x114
MU_GSR = 0x118
MU_TSR = 0x124

SCMI_SRAM = 0x1000
SCMI_CHANNEL_SIZE = 0x80
SMT_CHANNEL_STATUS = 0x04
SMT_LENGTH = 0x14
SMT_MESSAGE_HEADER = 0x18
SMT_PAYLOAD = 0x1C
SMT_CHANNEL_FREE = 0x1

SCMI_SUCCESS = 0
SCMI_NOT_SUPPORTED = 0xFFFFFFFF
SCMI_INVALID_PARAMETERS = 0xFFFFFFFE
SCMI_DENIED = 0xFFFFFFFD
SCMI_NOT_FOUND = 0xFFFFFFFC

SCMI_PROTOCOL_BASE = 0x10
SCMI_PROTOCOL_POWER = 0x11
SCMI_PROTOCOL_SYSTEM = 0x12
SCMI_PROTOCOL_PERF = 0x13
SCMI_PROTOCOL_CLOCK = 0x14
SCMI_PROTOCOL_PINCTRL = 0x19
SCMI_PROTOCOL_NXP_CPU = 0x82

SCMI_BASE_VERSION = 0x00020000
SCMI_POWER_VERSION = 0x00030001
SCMI_SYSTEM_VERSION = 0x00020001
SCMI_PERF_VERSION = 0x00040000
SCMI_CLOCK_VERSION = 0x00030000
SCMI_PINCTRL_VERSION = 0x00010000
SCMI_NXP_CPU_VERSION = 0x00010000

AGENT_M7 = 0
AGENT_AP_S = 1
AGENT_AP_NS = 2

AGENT_NAMES = {
    AGENT_M7: "M7",
    AGENT_AP_S: "AP-S",
    AGENT_AP_NS: "AP-NS",
}

# i.MX952 power domain IDs from devices/MIMX952/sm/dev_sm_power.h.
PD_CAMERA = 3
PD_A55P = 9
PD_DDR = 10
PD_DISPLAY = 11
PD_GPU = 12
PD_HSIO_TOP = 13
PD_M7 = 15
PD_NETC = 16
PD_NOC = 17
PD_NPU = 18
PD_VPU = 19

POWER_DOMAIN_NAMES = {
    0: "ANA",
    1: "AON",
    2: "BBSM",
    3: "CAMERA",
    4: "CCMSRCGPC",
    5: "A55C0",
    6: "A55C1",
    7: "A55C2",
    8: "A55C3",
    9: "A55P",
    10: "DDR",
    11: "DISPLAY",
    12: "GPU",
    13: "HSIO_TOP",
    14: "HSIO_WAON",
    15: "M7",
    16: "NETC",
    17: "NOC",
    18: "NPU",
    19: "VPU",
    20: "WAKEUP",
}

POWER_PERMISSIONS = {
    AGENT_M7: set([PD_M7]),
    AGENT_AP_S: set([PD_A55P]),
    AGENT_AP_NS: set([PD_CAMERA, PD_DISPLAY, PD_GPU, PD_HSIO_TOP, PD_NETC, PD_NPU, PD_VPU]),
}

# i.MX952 performance domains from devices/MIMX952/sm/dev_sm_perf.h.
PERF_M33 = 0
PERF_WAKEUP = 1
PERF_M7 = 2
PERF_DRAM = 3
PERF_HSIO = 4
PERF_NPU = 5
PERF_NOC = 6
PERF_A55 = 7
PERF_GPU = 8
PERF_VPU = 9
PERF_CAM = 10
PERF_DISP = 11

PERF_DOMAIN_NAMES = {
    PERF_M33: "M33",
    PERF_WAKEUP: "WAKEUP",
    PERF_M7: "M7",
    PERF_DRAM: "DRAM",
    PERF_HSIO: "HSIO",
    PERF_NPU: "NPU",
    PERF_NOC: "NOC",
    PERF_A55: "A55",
    PERF_GPU: "GPU",
    PERF_VPU: "VPU",
    PERF_CAM: "CAM",
    PERF_DISP: "DISP",
}

PERF_PERMISSIONS = {
    AGENT_M7: set([PERF_M7]),
    AGENT_AP_S: set([PERF_A55, PERF_DRAM]),
    AGENT_AP_NS: set([PERF_A55, PERF_DRAM, PERF_GPU, PERF_NPU, PERF_VPU, PERF_CAM, PERF_DISP]),
}

# PRK, LOW, NOM, ODV. Exact frequency values are model calibration inputs;
# these defaults preserve the already-qualified A55/M7 operating points while
# exposing the source-derived four-level state machine.
PERF_LEVELS = {
    PERF_A55: [400000000, 800000000, 1200000000, 1700000000],
    PERF_M7: [200000000, 400000000, 600000000, 800000000],
    PERF_DRAM: [400000000, 800000000, 1600000000, 2400000000],
    PERF_GPU: [200000000, 400000000, 800000000, 1000000000],
    PERF_NPU: [200000000, 400000000, 800000000, 1000000000],
    PERF_VPU: [200000000, 400000000, 600000000, 800000000],
    PERF_CAM: [200000000, 400000000, 600000000, 800000000],
    PERF_DISP: [200000000, 400000000, 600000000, 800000000],
}

IMX952_M7_CPUID = 1
M7_SCMI_IRQ = 205
CPU_RUN_MODE_START = 0
CPU_RUN_MODE_HOLD = 1
CPU_RUN_MODE_STOP = 2
CPU_RUN_MODE_SLEEP = 3
CPU_VEC_FLAGS_START = 1 << 30

SYS_STATE_SHUTDOWN = 0x00000000
SYS_STATE_COLD_RESET = 0x00000001
SYS_STATE_WARM_RESET = 0x00000002
SYS_STATE_POWER_UP = 0x00000003
SYS_STATE_SUSPEND = 0x00000004


def _read(offset, length):
    value = 0
    i = 0
    while i < length:
        if 0 <= offset + i < len(memory):
            value |= (memory[offset + i] & 0xFF) << (8 * i)
        i += 1
    return value


def _write(offset, value, length):
    i = 0
    while i < length:
        if 0 <= offset + i < len(memory):
            memory[offset + i] = (value >> (8 * i)) & 0xFF
        i += 1


def _read32(offset):
    return _read(offset, 4)


def _write32(offset, value):
    _write(offset, value & 0xFFFFFFFF, 4)


def _write_ascii(offset, text, field_size):
    i = 0
    while i < field_size:
        value = ord(text[i]) if i < len(text) else 0
        _write(offset + i, value, 1)
        i += 1


def _find_element(name):
    emulation = EmulationManager.Instance.CurrentEmulation
    for candidate in emulation.Machines:
        try:
            result = emulation.TryGetEmulationElementByName(name, candidate)
            if result[0]:
                return candidate, result[1]
        except:
            pass
    return None, None


def _get_machine():
    machine, unused = _find_element("m7")
    return machine


def _get_m7():
    unused, m7 = _find_element("m7")
    return m7


def _agent_for_channel(channel):
    if scmi_channel_count == 1:
        return AGENT_M7
    if channel == 0:
        return AGENT_AP_S
    return AGENT_AP_NS


def _protocols_for_agent(agent_id):
    if agent_id == AGENT_M7:
        return [SCMI_PROTOCOL_POWER, SCMI_PROTOCOL_SYSTEM, SCMI_PROTOCOL_PERF,
                SCMI_PROTOCOL_CLOCK, SCMI_PROTOCOL_PINCTRL, SCMI_PROTOCOL_NXP_CPU]
    return [SCMI_PROTOCOL_POWER, SCMI_PROTOCOL_SYSTEM, SCMI_PROTOCOL_PERF,
            SCMI_PROTOCOL_CLOCK, SCMI_PROTOCOL_PINCTRL]


def _update_m7_scmi_irq():
    if scmi_channel_count != 1:
        return
    unused, nvic = _find_element("m7Nvic")
    if nvic is None:
        return
    try:
        pending = (_read32(MU_GSR) & _read32(MU_GIER) & 0xF) != 0
        nvic.OnGPIO(M7_SCMI_IRQ, pending)
    except:
        pass


def _apply_m7_reset_vector(vector):
    m7 = _get_m7()
    machine = _get_machine()
    if m7 is None or machine is None:
        return False
    sp = machine.SystemBus.ReadDoubleWord(vector)
    pc = machine.SystemBus.ReadDoubleWord(vector + 4)
    if sp != 0 and pc != 0 and (sp & 0xF0000000) == 0x20000000:
        m7.SP = RegisterValue.Create(sp, 32)
        m7.PC = RegisterValue.Create(pc & 0xFFFFFFFE, 32)
    else:
        m7.PC = RegisterValue.Create(vector & 0xFFFFFFFE, 32)
    return True


def _set_response(channel, status, words, text_payload=None, text_offset=4, text_size=16):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    _write32(base + SMT_PAYLOAD, status)
    payload_length = 4
    index = 0
    for word in words:
        _write32(base + SMT_PAYLOAD + 4 + index * 4, word)
        payload_length += 4
        index += 1
    if text_payload is not None:
        _write_ascii(base + SMT_PAYLOAD + text_offset, text_payload, text_size)
        payload_length = max(payload_length, text_offset + text_size)
    _write32(base + SMT_LENGTH, payload_length + 4)
    _write32(base + SMT_CHANNEL_STATUS, SMT_CHANNEL_FREE)


def _message_attributes(channel, message_id, supported):
    if message_id in supported:
        _set_response(channel, SCMI_SUCCESS, [0])
    else:
        _set_response(channel, SCMI_NOT_FOUND, [])


def _process_base(channel, message_id, agent_id):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    protocols = _protocols_for_agent(agent_id)
    if message_id == 0x00:
        _set_response(channel, SCMI_SUCCESS, [SCMI_BASE_VERSION])
    elif message_id == 0x01:
        # Number of agents in bits[15:8], number of protocols in bits[7:0].
        _set_response(channel, SCMI_SUCCESS, [(3 << 8) | len(protocols)])
    elif message_id == 0x02:
        requested = _read32(base + SMT_PAYLOAD)
        _message_attributes(channel, requested, set([0, 1, 2, 3, 4, 5, 6, 7]))
    elif message_id == 0x03:
        _set_response(channel, SCMI_SUCCESS, [], "NXP", 4, 16)
    elif message_id == 0x04:
        _set_response(channel, SCMI_SUCCESS, [], "i.MX952-SM", 4, 16)
    elif message_id == 0x05:
        _set_response(channel, SCMI_SUCCESS, [1])
    elif message_id == 0x06:
        skip = _read32(base + SMT_PAYLOAD)
        remaining = protocols[skip:]
        words = []
        index = 0
        while index < len(remaining):
            packed = 0
            shift = 0
            while shift < 32 and index < len(remaining):
                packed |= (remaining[index] & 0xFF) << shift
                shift += 8
                index += 1
            words.append(packed)
        _set_response(channel, SCMI_SUCCESS, [len(remaining)] + words)
    elif message_id == 0x07:
        requested_agent = _read32(base + SMT_PAYLOAD)
        if requested_agent not in AGENT_NAMES:
            _set_response(channel, SCMI_NOT_FOUND, [])
        else:
            _set_response(channel, SCMI_SUCCESS, [requested_agent], AGENT_NAMES[requested_agent], 8, 16)
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _power_allowed(agent_id, domain_id):
    return domain_id in POWER_PERMISSIONS.get(agent_id, set())


def _process_power(channel, message_id, agent_id):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    allowed = POWER_PERMISSIONS.get(agent_id, set())
    if message_id == 0x00:
        _set_response(channel, SCMI_SUCCESS, [SCMI_POWER_VERSION])
    elif message_id == 0x01:
        _set_response(channel, SCMI_SUCCESS, [len(allowed), 0, 0, 0])
    elif message_id == 0x02:
        requested = _read32(base + SMT_PAYLOAD)
        _message_attributes(channel, requested, set([0, 1, 2, 3, 4, 5, 0x10]))
    elif message_id == 0x03:
        domain_id = _read32(base + SMT_PAYLOAD)
        if not _power_allowed(agent_id, domain_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            name = POWER_DOMAIN_NAMES.get(domain_id, "PD-%d" % domain_id)
            _set_response(channel, SCMI_SUCCESS, [0], name, 8, 16)
    elif message_id == 0x04:
        domain_id = _read32(base + SMT_PAYLOAD + 4)
        pstate = _read32(base + SMT_PAYLOAD + 8)
        if not _power_allowed(agent_id, domain_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            power_domain_states[domain_id] = pstate
            _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x05:
        domain_id = _read32(base + SMT_PAYLOAD)
        if not _power_allowed(agent_id, domain_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            _set_response(channel, SCMI_SUCCESS, [power_domain_states.get(domain_id, 0)])
    elif message_id == 0x10:
        requested_version = _read32(base + SMT_PAYLOAD)
        if requested_version <= SCMI_POWER_VERSION:
            _set_response(channel, SCMI_SUCCESS, [])
        else:
            _set_response(channel, SCMI_NOT_SUPPORTED, [])
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _process_system(channel, message_id, agent_id):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    if message_id == 0x00:
        _set_response(channel, SCMI_SUCCESS, [SCMI_SYSTEM_VERSION])
    elif message_id == 0x01:
        _set_response(channel, SCMI_SUCCESS, [0])
    elif message_id == 0x02:
        requested = _read32(base + SMT_PAYLOAD)
        _message_attributes(channel, requested, set([0, 1, 2, 3, 5, 0x10]))
    elif message_id == 0x03:
        flags = _read32(base + SMT_PAYLOAD)
        state = _read32(base + SMT_PAYLOAD + 4)
        if state not in set([SYS_STATE_SHUTDOWN, SYS_STATE_COLD_RESET, SYS_STATE_WARM_RESET,
                             SYS_STATE_POWER_UP, SYS_STATE_SUSPEND]):
            _set_response(channel, SCMI_INVALID_PARAMETERS, [])
        else:
            system_power_state[agent_id] = state
            system_power_flags[agent_id] = flags
            _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x05:
        enable = _read32(base + SMT_PAYLOAD) & 1
        system_notifications[agent_id] = enable != 0
        _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x10:
        requested_version = _read32(base + SMT_PAYLOAD)
        if requested_version <= SCMI_SYSTEM_VERSION:
            _set_response(channel, SCMI_SUCCESS, [])
        else:
            _set_response(channel, SCMI_NOT_SUPPORTED, [])
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _perf_allowed(agent_id, domain_id):
    return domain_id in PERF_PERMISSIONS.get(agent_id, set())


def _perf_levels(domain_id):
    return PERF_LEVELS.get(domain_id, [0, 1, 2, 3])


def _process_perf(channel, message_id, agent_id):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    allowed = PERF_PERMISSIONS.get(agent_id, set())
    if message_id == 0x00:
        _set_response(channel, SCMI_SUCCESS, [SCMI_PERF_VERSION])
    elif message_id == 0x01:
        _set_response(channel, SCMI_SUCCESS, [len(allowed), 0, 0, 0])
    elif message_id == 0x02:
        requested = _read32(base + SMT_PAYLOAD)
        _message_attributes(channel, requested, set([0, 1, 2, 3, 4, 5, 6, 7, 8, 0x10]))
    elif message_id == 0x03:
        domain_id = _read32(base + SMT_PAYLOAD)
        if not _perf_allowed(agent_id, domain_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            levels = _perf_levels(domain_id)
            sustained = levels[2] if len(levels) > 2 else levels[-1]
            name = PERF_DOMAIN_NAMES.get(domain_id, "PERF-%d" % domain_id)
            _set_response(channel, SCMI_SUCCESS, [0, 0, sustained, 2], name, 20, 16)
    elif message_id == 0x04:
        domain_id = _read32(base + SMT_PAYLOAD)
        skip_index = _read32(base + SMT_PAYLOAD + 4)
        if not _perf_allowed(agent_id, domain_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            levels = _perf_levels(domain_id)[skip_index:]
            words = [len(levels)]
            for index in range(len(levels)):
                words.extend([levels[index], 0, 0, levels[index], skip_index + index])
            _set_response(channel, SCMI_SUCCESS, words)
    elif message_id == 0x05:
        domain_id = _read32(base + SMT_PAYLOAD)
        range_max = _read32(base + SMT_PAYLOAD + 4)
        range_min = _read32(base + SMT_PAYLOAD + 8)
        if not _perf_allowed(agent_id, domain_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            perf_limits[domain_id] = (range_min, range_max)
            _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x06:
        domain_id = _read32(base + SMT_PAYLOAD)
        if not _perf_allowed(agent_id, domain_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            levels = _perf_levels(domain_id)
            default_limits = (0, len(levels) - 1)
            minimum, maximum = perf_limits.get(domain_id, default_limits)
            _set_response(channel, SCMI_SUCCESS, [maximum, minimum])
    elif message_id == 0x07:
        domain_id = _read32(base + SMT_PAYLOAD)
        level = _read32(base + SMT_PAYLOAD + 4)
        if not _perf_allowed(agent_id, domain_id):
            _set_response(channel, SCMI_DENIED, [])
        elif level > 3:
            _set_response(channel, SCMI_INVALID_PARAMETERS, [])
        else:
            perf_current_levels[domain_id] = level
            _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x08:
        domain_id = _read32(base + SMT_PAYLOAD)
        if not _perf_allowed(agent_id, domain_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            _set_response(channel, SCMI_SUCCESS, [perf_current_levels.get(domain_id, 2)])
    elif message_id == 0x10:
        requested_version = _read32(base + SMT_PAYLOAD)
        if requested_version <= SCMI_PERF_VERSION:
            _set_response(channel, SCMI_SUCCESS, [])
        else:
            _set_response(channel, SCMI_NOT_SUPPORTED, [])
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _clock_default_rate(clock_id):
    if clock_id == 70:
        return 1700000000
    if clock_id == 95 or clock_id == 96:
        return 800000000
    if clock_id == 52:
        return 24000000
    if clock_id == 43 or clock_id == 119:
        return 133000000
    if clock_id == 158 or clock_id == 159 or clock_id == 160:
        return 400000000
    return 24000000


def _process_clock(channel, message_id, agent_id):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    if message_id == 0x00:
        _set_response(channel, SCMI_SUCCESS, [SCMI_CLOCK_VERSION])
    elif message_id == 0x01:
        _set_response(channel, SCMI_SUCCESS, [198])
    elif message_id == 0x02:
        requested = _read32(base + SMT_PAYLOAD)
        _message_attributes(channel, requested, set([0, 1, 2, 3, 4, 5, 6, 7, 0xB, 0xC, 0xD, 0xE, 0x10]))
    elif message_id == 0x03:
        clock_id = _read32(base + SMT_PAYLOAD)
        if clock_id >= 198:
            _set_response(channel, SCMI_NOT_FOUND, [])
        else:
            _set_response(channel, SCMI_SUCCESS, [0], "imx952-clk-%d" % clock_id, 8, 16)
    elif message_id == 0x04:
        clock_id = _read32(base + SMT_PAYLOAD)
        rate = clock_rates.get(clock_id, _clock_default_rate(clock_id))
        _set_response(channel, SCMI_SUCCESS, [1, rate & 0xFFFFFFFF, (rate >> 32) & 0xFFFFFFFF, 0, 0])
    elif message_id == 0x05:
        clock_id = _read32(base + SMT_PAYLOAD + 4)
        rate_lsb = _read32(base + SMT_PAYLOAD + 8)
        rate_msb = _read32(base + SMT_PAYLOAD + 12)
        clock_rates[clock_id] = rate_lsb | (rate_msb << 32)
        _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x06:
        clock_id = _read32(base + SMT_PAYLOAD)
        rate = clock_rates.get(clock_id, _clock_default_rate(clock_id))
        _set_response(channel, SCMI_SUCCESS, [rate & 0xFFFFFFFF, (rate >> 32) & 0xFFFFFFFF])
    elif message_id == 0x07:
        clock_id = _read32(base + SMT_PAYLOAD)
        attributes = _read32(base + SMT_PAYLOAD + 4)
        clock_enabled[clock_id] = (attributes & 1) != 0
        _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x0B:
        clock_id = _read32(base + SMT_PAYLOAD)
        _set_response(channel, SCMI_SUCCESS, [1 if clock_enabled.get(clock_id, True) else 0])
    elif message_id == 0x0C:
        _set_response(channel, SCMI_SUCCESS, [0])
    elif message_id == 0x0D:
        clock_id = _read32(base + SMT_PAYLOAD)
        parent_id = _read32(base + SMT_PAYLOAD + 4)
        clock_parents[clock_id] = parent_id
        _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x0E:
        clock_id = _read32(base + SMT_PAYLOAD)
        _set_response(channel, SCMI_SUCCESS, [clock_parents.get(clock_id, 0)])
    elif message_id == 0x10:
        requested_version = _read32(base + SMT_PAYLOAD)
        if requested_version <= SCMI_CLOCK_VERSION:
            _set_response(channel, SCMI_SUCCESS, [])
        else:
            _set_response(channel, SCMI_NOT_SUPPORTED, [])
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _process_pinctrl(channel, message_id, agent_id):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    if message_id == 0x00:
        _set_response(channel, SCMI_SUCCESS, [SCMI_PINCTRL_VERSION])
    elif message_id == 0x01:
        _set_response(channel, SCMI_SUCCESS, [0])
    elif message_id == 0x02:
        requested = _read32(base + SMT_PAYLOAD)
        _message_attributes(channel, requested, set([0, 1, 2, 6]))
    elif message_id == 0x06:
        _set_response(channel, SCMI_SUCCESS, [])
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _process_nxp_cpu(channel, message_id, agent_id):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    m7 = _get_m7()
    if agent_id != AGENT_M7:
        _set_response(channel, SCMI_DENIED, [])
        return
    if message_id == 0x00:
        _set_response(channel, SCMI_SUCCESS, [SCMI_NXP_CPU_VERSION])
    elif message_id == 0x01:
        _set_response(channel, SCMI_SUCCESS, [2])
    elif message_id == 0x02:
        requested = _read32(base + SMT_PAYLOAD)
        _message_attributes(channel, requested, set([0, 1, 2, 3, 4, 5, 6, 0x0C]))
    elif message_id == 0x03:
        cpuid = _read32(base + SMT_PAYLOAD)
        if cpuid != IMX952_M7_CPUID:
            _set_response(channel, SCMI_NOT_FOUND, [])
        else:
            _set_response(channel, SCMI_SUCCESS, [0], "Cortex-M7", 8, 16)
    elif message_id == 0x04:
        cpuid = _read32(base + SMT_PAYLOAD)
        if cpuid != IMX952_M7_CPUID or m7 is None:
            _set_response(channel, SCMI_INVALID_PARAMETERS, [])
        else:
            vector = cpu_reset_vectors.get(cpuid, 0)
            if _apply_m7_reset_vector(vector):
                m7.IsHalted = False
                _set_response(channel, SCMI_SUCCESS, [])
            else:
                _set_response(channel, SCMI_NOT_FOUND, [])
    elif message_id == 0x05:
        cpuid = _read32(base + SMT_PAYLOAD)
        if cpuid != IMX952_M7_CPUID or m7 is None:
            _set_response(channel, SCMI_INVALID_PARAMETERS, [])
        else:
            m7.IsHalted = True
            _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x06:
        cpuid = _read32(base + SMT_PAYLOAD)
        flags = _read32(base + SMT_PAYLOAD + 4)
        vector_low = _read32(base + SMT_PAYLOAD + 8)
        vector_high = _read32(base + SMT_PAYLOAD + 12)
        vector = vector_low | (vector_high << 32)
        if cpuid != IMX952_M7_CPUID or m7 is None:
            _set_response(channel, SCMI_INVALID_PARAMETERS, [])
        else:
            cpu_reset_vectors[cpuid] = vector
            _apply_m7_reset_vector(vector)
            if flags & CPU_VEC_FLAGS_START:
                m7.IsHalted = False
            _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x0C:
        cpuid = _read32(base + SMT_PAYLOAD)
        if cpuid != IMX952_M7_CPUID or m7 is None:
            _set_response(channel, SCMI_INVALID_PARAMETERS, [])
        else:
            vector = cpu_reset_vectors.get(cpuid, 0)
            run_mode = CPU_RUN_MODE_STOP if m7.IsHalted else CPU_RUN_MODE_START
            _set_response(channel, SCMI_SUCCESS,
                          [run_mode, 0, vector & 0xFFFFFFFF, (vector >> 32) & 0xFFFFFFFF])
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _process_scmi(channel):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    header = _read32(base + SMT_MESSAGE_HEADER)
    message_id = header & 0xFF
    protocol_id = (header >> 10) & 0xFF
    agent_id = _agent_for_channel(channel)
    if protocol_id == SCMI_PROTOCOL_BASE:
        _process_base(channel, message_id, agent_id)
    elif protocol_id == SCMI_PROTOCOL_POWER:
        _process_power(channel, message_id, agent_id)
    elif protocol_id == SCMI_PROTOCOL_SYSTEM:
        _process_system(channel, message_id, agent_id)
    elif protocol_id == SCMI_PROTOCOL_PERF:
        _process_perf(channel, message_id, agent_id)
    elif protocol_id == SCMI_PROTOCOL_CLOCK:
        _process_clock(channel, message_id, agent_id)
    elif protocol_id == SCMI_PROTOCOL_PINCTRL:
        _process_pinctrl(channel, message_id, agent_id)
    elif protocol_id == SCMI_PROTOCOL_NXP_CPU:
        _process_nxp_cpu(channel, message_id, agent_id)
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])
    _write32(MU_GSR, _read32(MU_GSR) | (1 << channel))
    _update_m7_scmi_irq()
    self.NoisyLog("i.MX952 full SCMI response: agent=%d channel=%d protocol=0x%X message=0x%X" %
                  (agent_id, channel, protocol_id, message_id))


if request.IsInit:
    memory = [0] * int(size)
    clock_rates = {}
    clock_enabled = {}
    clock_parents = {}
    power_domain_states = {}
    perf_current_levels = {}
    perf_limits = {}
    system_power_state = {}
    system_power_flags = {}
    system_notifications = {}
    cpu_reset_vectors = {IMX952_M7_CPUID: 0}

    scmi_channel_count = 2 if size >= 0x1400 else 1
    _write32(MU_PAR, 0x00000404)
    _write32(MU_TSR, 0x0000000F)
    channel = 0
    while channel < scmi_channel_count:
        _write32(SCMI_SRAM + channel * SCMI_CHANNEL_SIZE + SMT_CHANNEL_STATUS,
                 SMT_CHANNEL_FREE)
        channel += 1
elif request.IsRead:
    request.Value = _read(request.Offset, request.Length)
elif request.IsWrite:
    offset = request.Offset
    value = request.Value
    length = request.Length

    if offset == MU_GIER and length == 4:
        _write32(MU_GIER, value)
        _update_m7_scmi_irq()
    elif offset == MU_GSR and length == 4:
        _write32(MU_GSR, _read32(MU_GSR) & (~value & 0xFFFFFFFF))
        _update_m7_scmi_irq()
    elif offset == MU_GCR and length == 4:
        _write32(MU_GCR, value)
        channel = 0
        while channel < scmi_channel_count:
            if value & (1 << channel):
                _process_scmi(channel)
            channel += 1
        _write32(MU_GCR, 0)
    else:
        _write(offset, value, length)
