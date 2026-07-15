# Functional i.MX95-family MU2 + SCMI System Manager transport model.
# Address window: MU2 0x0000..0x0FFF, SCMI SRAM 0x1000..0x13FF.

MU_PAR = 0x004
MU_GCR = 0x114
MU_GSR = 0x118
MU_TSR = 0x124

SCMI_SRAM = 0x1000
SCMI_CHANNEL_SIZE = 0x80
SCMI_CHANNEL_COUNT = 2
SMT_CHANNEL_STATUS = 0x04
SMT_LENGTH = 0x14
SMT_MESSAGE_HEADER = 0x18
SMT_PAYLOAD = 0x1C
SMT_CHANNEL_FREE = 0x1

SCMI_SUCCESS = 0
SCMI_NOT_SUPPORTED = 0xFFFFFFFF
SCMI_NOT_FOUND = 0xFFFFFFFC
SCMI_PROTOCOL_BASE = 0x10
SCMI_PROTOCOL_POWER = 0x11
SCMI_PROTOCOL_CLOCK = 0x14
SCMI_PROTOCOL_PINCTRL = 0x19
SCMI_CLOCK_COUNT = 198
SCMI_CLOCK_VERSION = 0x00020000


def _read(offset, length):
    value = 0
    i = 0
    while i < length:
        if offset + i < len(memory):
            value |= (memory[offset + i] & 0xFF) << (8 * i)
        i += 1
    return value


def _write(offset, value, length):
    i = 0
    while i < length:
        if offset + i < len(memory):
            memory[offset + i] = (value >> (8 * i)) & 0xFF
        i += 1


def _read32(offset):
    return _read(offset, 4)


def _write32(offset, value):
    _write(offset, value & 0xFFFFFFFF, 4)


def _write_ascii(offset, text, size):
    i = 0
    while i < size:
        value = ord(text[i]) if i < len(text) else 0
        _write(offset + i, value, 1)
        i += 1


def _set_response(channel, status, words, text_payload=None):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    _write32(base + SMT_PAYLOAD, status)
    payload_length = 4
    index = 0
    for word in words:
        _write32(base + SMT_PAYLOAD + 4 + index * 4, word)
        payload_length += 4
        index += 1
    if text_payload is not None:
        _write_ascii(base + SMT_PAYLOAD + 4, text_payload, 16)
        payload_length = 20
    # SCMI SMT length includes the 4-byte SCMI message header.
    _write32(base + SMT_LENGTH, payload_length + 4)
    _write32(base + SMT_CHANNEL_STATUS, SMT_CHANNEL_FREE)


def _process_base(channel, message_id):
    if message_id == 0x00:  # PROTOCOL_VERSION
        _set_response(channel, SCMI_SUCCESS, [0x00020000])
    elif message_id == 0x01:  # PROTOCOL_ATTRIBUTES
        # One platform agent and three implemented protocols: Power, Clock, Pinctrl.
        _set_response(channel, SCMI_SUCCESS, [0x00000103])
    elif message_id == 0x02:  # PROTOCOL_MESSAGE_ATTRIBUTES
        _set_response(channel, SCMI_SUCCESS, [0])
    elif message_id == 0x03:  # DISCOVER_VENDOR
        _set_response(channel, SCMI_SUCCESS, [], "NXP-Renode")
    elif message_id == 0x04:  # DISCOVER_SUB_VENDOR
        _set_response(channel, SCMI_SUCCESS, [], "i.MX952-SM")
    elif message_id == 0x05:  # DISCOVER_IMPLEMENTATION_VERSION
        _set_response(channel, SCMI_SUCCESS, [1])
    elif message_id == 0x06:  # DISCOVER_LIST_PROTOCOLS
        packed = SCMI_PROTOCOL_POWER | (SCMI_PROTOCOL_CLOCK << 8) | (SCMI_PROTOCOL_PINCTRL << 16)
        _set_response(channel, SCMI_SUCCESS, [3, packed])
    elif message_id == 0x07:  # DISCOVER_AGENT
        _set_response(channel, SCMI_SUCCESS, [1])
        base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
        _write_ascii(base + SMT_PAYLOAD + 8, "A55-Agent", 16)
        _write32(base + SMT_LENGTH, 28)
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _process_power(channel, message_id):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    if message_id == 0x00:  # PROTOCOL_VERSION
        _set_response(channel, SCMI_SUCCESS, [0x00030000])
    elif message_id == 0x01:  # PROTOCOL_ATTRIBUTES
        # i.MX 952 domain IDs are sparse. Expose a superset covering current IDs.
        _set_response(channel, SCMI_SUCCESS, [64, 0, 0, 0])
    elif message_id == 0x02:  # PROTOCOL_MESSAGE_ATTRIBUTES
        _set_response(channel, SCMI_SUCCESS, [0])
    elif message_id == 0x03:  # POWER_DOMAIN_ATTRIBUTES
        domain_id = _read32(base + SMT_PAYLOAD)
        _write32(base + SMT_PAYLOAD, SCMI_SUCCESS)
        _write32(base + SMT_PAYLOAD + 4, 0)
        _write_ascii(base + SMT_PAYLOAD + 8, "imx952-pd-%d" % domain_id, 16)
        _write32(base + SMT_LENGTH, 32)
        _write32(base + SMT_CHANNEL_STATUS, SMT_CHANNEL_FREE)
    elif message_id == 0x04:  # POWER_STATE_SET
        domain_id = _read32(base + SMT_PAYLOAD + 4)
        pstate = _read32(base + SMT_PAYLOAD + 8)
        power_domain_states[domain_id] = pstate
        _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x05:  # POWER_STATE_GET
        domain_id = _read32(base + SMT_PAYLOAD)
        _set_response(channel, SCMI_SUCCESS, [power_domain_states.get(domain_id, 0)])
    elif message_id == 0x06:  # POWER_DOMAIN_NAME_GET
        domain_id = _read32(base + SMT_PAYLOAD)
        _write32(base + SMT_PAYLOAD, SCMI_SUCCESS)
        _write_ascii(base + SMT_PAYLOAD + 4, "imx952-pd-%d" % domain_id, 64)
        _write32(base + SMT_LENGTH, 72)
        _write32(base + SMT_CHANNEL_STATUS, SMT_CHANNEL_FREE)
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _clock_default_rate(clock_id):
    if clock_id == 70:   # A55
        return 1700000000
    if clock_id == 95:   # M7
        return 800000000
    if clock_id == 96:   # M7 SysTick
        return 800000000
    if clock_id == 52:   # LPUART1
        return 24000000
    if clock_id == 43 or clock_id == 119:  # BUSAON / BUSWAKEUP
        return 133000000
    if clock_id == 158 or clock_id == 159 or clock_id == 160:  # USDHC1/2/3
        return 400000000
    return 24000000


def _process_clock(channel, message_id):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    if message_id == 0x00:  # PROTOCOL_VERSION
        _set_response(channel, SCMI_SUCCESS, [SCMI_CLOCK_VERSION])
    elif message_id == 0x01:  # PROTOCOL_ATTRIBUTES
        _set_response(channel, SCMI_SUCCESS, [SCMI_CLOCK_COUNT])
    elif message_id == 0x02:  # PROTOCOL_MESSAGE_ATTRIBUTES
        _set_response(channel, SCMI_SUCCESS, [0])
    elif message_id == 0x03:  # CLOCK_ATTRIBUTES
        clock_id = _read32(base + SMT_PAYLOAD)
        if clock_id >= SCMI_CLOCK_COUNT:
            _set_response(channel, SCMI_NOT_FOUND, [])
        else:
            _write32(base + SMT_PAYLOAD, SCMI_SUCCESS)
            _write32(base + SMT_PAYLOAD + 4, 0)
            _write_ascii(base + SMT_PAYLOAD + 8, "imx952-clk-%d" % clock_id, 16)
            _write32(base + SMT_PAYLOAD + 24, 0)
            _write32(base + SMT_LENGTH, 32)
            _write32(base + SMT_CHANNEL_STATUS, SMT_CHANNEL_FREE)
    elif message_id == 0x05:  # CLOCK_RATE_SET
        clock_id = _read32(base + SMT_PAYLOAD + 4)
        rate_lsb = _read32(base + SMT_PAYLOAD + 8)
        rate_msb = _read32(base + SMT_PAYLOAD + 12)
        clock_rates[clock_id] = rate_lsb | (rate_msb << 32)
        _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x06:  # CLOCK_RATE_GET
        clock_id = _read32(base + SMT_PAYLOAD)
        rate = clock_rates.get(clock_id, _clock_default_rate(clock_id))
        _set_response(channel, SCMI_SUCCESS, [rate & 0xFFFFFFFF, (rate >> 32) & 0xFFFFFFFF])
    elif message_id == 0x07:  # CLOCK_CONFIG_SET
        clock_id = _read32(base + SMT_PAYLOAD)
        attributes = _read32(base + SMT_PAYLOAD + 4)
        clock_enabled[clock_id] = (attributes & 1) != 0
        _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x0D:  # CLOCK_PARENT_SET
        clock_id = _read32(base + SMT_PAYLOAD)
        parent_id = _read32(base + SMT_PAYLOAD + 4)
        clock_parents[clock_id] = parent_id
        _set_response(channel, SCMI_SUCCESS, [])
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _process_pinctrl(channel, message_id):
    if message_id == 0x00:  # PROTOCOL_VERSION
        _set_response(channel, SCMI_SUCCESS, [0x00010000])
    elif message_id == 0x01:  # PROTOCOL_ATTRIBUTES
        _set_response(channel, SCMI_SUCCESS, [0])
    elif message_id == 0x02:  # PROTOCOL_MESSAGE_ATTRIBUTES
        _set_response(channel, SCMI_SUCCESS, [0])
    elif message_id == 0x06:  # PINCTRL_CONFIG_SET
        _set_response(channel, SCMI_SUCCESS, [])
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _process_scmi(channel):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    header = _read32(base + SMT_MESSAGE_HEADER)
    message_id = header & 0xFF
    protocol_id = (header >> 10) & 0xFF
    if protocol_id == SCMI_PROTOCOL_BASE:
        _process_base(channel, message_id)
    elif protocol_id == SCMI_PROTOCOL_POWER:
        _process_power(channel, message_id)
    elif protocol_id == SCMI_PROTOCOL_CLOCK:
        _process_clock(channel, message_id)
    elif protocol_id == SCMI_PROTOCOL_PINCTRL:
        _process_pinctrl(channel, message_id)
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])
    _write32(MU_GSR, _read32(MU_GSR) | (1 << channel))
    self.NoisyLog("i.MX952 SCMI response: channel=%d protocol=0x%X message=0x%X" % (channel, protocol_id, message_id))


if request.IsInit:
    memory = [0] * 0x1400
    clock_rates = {}
    clock_enabled = {}
    clock_parents = {}
    power_domain_states = {}
    # i.MX95 MU V2: four transmit and four receive registers.
    _write32(MU_PAR, 0x00000404)
    _write32(MU_TSR, 0x0000000F)
    _write32(SCMI_SRAM + SMT_CHANNEL_STATUS, SMT_CHANNEL_FREE)
    _write32(SCMI_SRAM + SCMI_CHANNEL_SIZE + SMT_CHANNEL_STATUS, SMT_CHANNEL_FREE)
elif request.IsRead:
    request.Value = _read(request.Offset, request.Length)
elif request.IsWrite:
    offset = request.Offset
    value = request.Value
    length = request.Length

    if offset == MU_GSR and length == 4:
        # GSR is write-one-to-clear for pending general interrupt bits.
        _write32(MU_GSR, _read32(MU_GSR) & (~value & 0xFFFFFFFF))
    elif offset == MU_GCR and length == 4:
        # Process each requested SMT channel synchronously.
        _write32(MU_GCR, value)
        channel = 0
        while channel < SCMI_CHANNEL_COUNT:
            if value & (1 << channel):
                _process_scmi(channel)
            channel += 1
        _write32(MU_GCR, 0)
    else:
        _write(offset, value, length)
