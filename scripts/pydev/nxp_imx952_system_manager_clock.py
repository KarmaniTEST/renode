# i.MX952 source-derived SCMI Clock permission layer.
#
# Layering:
#   core protocol engine -> exact SMT/P2A transport -> BBM -> MISC -> Clock policy
#
# NXP's Clock protocol exposes the global SM_NUM_CLOCK inventory (198 clocks) and
# uses per-agent clkPerms to restrict mutating operations. This layer preserves
# global clock IDs while enforcing the exact generated mx952evk permission map.

_CLOCK_PROTOCOL = 0x14
_CLOCK_COUNT = 198
_CLOCK_PERMISSION_ALL_BITS = 0xE0000000  # state | parent | rate
_CLOCK_ATTR_RESTRICTED = 1 << 1

# Use source-defined numeric agent IDs here because the lower protocol engine is
# loaded later during the first PythonPeripheral IsInit execution.
_CLOCK_ALLOWED = {
    0: set([44, 51, 96, 141, 142]),
    1: set([24, 25, 26, 27, 28, 29, 30, 31, 32]),
    2: set([
        0, 14, 15, 16, 17, 18, 19, 35, 36, 37, 38, 39, 40, 46, 48, 49,
        50, 52, 57, 58, 60, 66, 67, 69, 77, 79, 80, 88, 102, 103, 105,
        110, 111, 112, 113, 120, 121, 124, 125, 126, 128, 129, 130, 131,
        132, 133, 134, 135, 136, 137, 138, 139, 140, 143, 144, 145, 146,
        147, 148, 149, 150, 153, 154, 155, 158, 159, 160, 163, 164, 165,
        166, 167, 168, 169, 170, 171, 179, 181, 182, 183, 184, 185, 186,
        187, 188, 189, 190, 193, 194, 195, 196, 197
    ]),
}

_CLOCK_SOURCE_NAMES = {
    44: "CAN1", 51: "LPTMR1", 96: "M7SYSTICK", 141: "LPTMR2",
    142: "LPUART3",
    24: "ARMPLL_VCO", 25: "ARMPLL_PFD0_UNGATED", 26: "ARMPLL_PFD0",
    27: "ARMPLL_PFD1_UNGATED", 28: "ARMPLL_PFD1",
    29: "ARMPLL_PFD2_UNGATED", 30: "ARMPLL_PFD2",
    31: "ARMPLL_PFD3_UNGATED", 32: "ARMPLL_PFD3",
    0: "EXT", 14: "AUDIOPLL1_VCO", 15: "AUDIOPLL1",
    16: "AUDIOPLL2_VCO", 17: "AUDIOPLL2", 18: "VIDEOPLL1_VCO",
    19: "VIDEOPLL1", 35: "HSIOPLL_VCO", 36: "HSIOPLL",
    37: "LDBPLL_VCO", 38: "LDBPLL", 39: "EXT1", 40: "EXT2",
    46: "I3C1SLOW", 48: "LPI2C2", 49: "LPSPI1", 50: "LPSPI2",
    52: "LPUART1", 57: "PDM", 58: "SAI1", 60: "TPM2",
    66: "CAMPHYCFG", 67: "MIPIPHYPLLBYPASS", 69: "MIPITESTBYTE",
    77: "DISPLPSPI", 79: "DISPPHYCFG", 80: "DISP1PIX",
    88: "HSIOPCIEAUX", 102: "ENETREF", 103: "ENETTIMER1",
    105: "SAI2", 110: "CCMCKO1", 111: "CCMCKO2", 112: "CCMCKO3",
    113: "CCMCKO4", 120: "CAN2", 121: "CAN3", 124: "FLEXIO1",
    125: "FLEXIO2", 126: "XSPI1", 128: "I3C2SLOW", 129: "LPI2C3",
    130: "LPI2C4", 131: "LPI2C5", 132: "LPI2C6", 133: "LPI2C7",
    134: "LPI2C8", 135: "LPSPI3", 136: "LPSPI4", 137: "LPSPI5",
    138: "LPSPI6", 139: "LPSPI7", 140: "LPSPI8", 143: "LPUART4",
    144: "LPUART5", 145: "LPUART6", 146: "LPUART7", 147: "LPUART8",
    148: "SAI3", 149: "SAI4", 150: "SAI5", 153: "TPM4", 154: "TPM5",
    155: "TPM6", 158: "USDHC1", 159: "USDHC2", 160: "USDHC3",
    163: "XSPISLVROOT", 164: "AUDMIX1", 165: "ASRC1", 166: "ASRC2",
    167: "GPT2", 168: "GPT3", 169: "GPT4", 170: "GPT5",
    171: "EXT_GPR_SEL", 179: "NPU_CGC", 181: "CAMISI_CGC",
    182: "CAMISP_CGC", 183: "CAMCSI0_CGC", 184: "CAMCSI1_CGC",
    185: "CAMOCRAM_CGC", 186: "HSIOUSB_CGC", 187: "HSIOPCIE_CGC",
    188: "DISPOCRAM_CGC", 189: "DISPSEERIS_CGC", 190: "DISPDSI_CGC",
    193: "NETC_CGC", 194: "VPUENC_CGC", 195: "VPUJPEGENC_CGC",
    196: "VPUJPEGDEC_CGC", 197: "VPUDEC_CGC",
}

_CLOCK_ORIGINAL_GCR = request.Value if request.IsWrite else 0
_CLOCK_IS_AP = size >= 0x1400
_CLOCK_REQUEST_CHANNEL = None
_CLOCK_PRE_HEADER = 0
_CLOCK_PRE_WORDS = [0] * 8

if request.IsWrite and request.Offset == 0x114:
    if _CLOCK_IS_AP and (_CLOCK_ORIGINAL_GCR & (1 << 2)):
        _CLOCK_REQUEST_CHANNEL = 2
    elif _CLOCK_ORIGINAL_GCR & 0x1:
        _CLOCK_REQUEST_CHANNEL = 0

    if _CLOCK_REQUEST_CHANNEL is not None:
        _clock_base = 0x1000 + _CLOCK_REQUEST_CHANNEL * 0x80
        _CLOCK_PRE_HEADER = _read32(_clock_base + 0x18)
        _clock_index = 0
        while _clock_index < len(_CLOCK_PRE_WORDS):
            _CLOCK_PRE_WORDS[_clock_index] = _read32(
                _clock_base + 0x1C + _clock_index * 4)
            _clock_index += 1

        # Prevent lower layers from processing Clock requests. The original
        # header and payload are restored after the layered model has processed
        # lower protocols, then this layer emits the authoritative response.
        if ((_CLOCK_PRE_HEADER >> 10) & 0xFF) == _CLOCK_PROTOCOL:
            _write32(_clock_base + 0x18, (0xFF << 10) | (_CLOCK_PRE_HEADER & 0x3FF))

execfile("scripts/pydev/nxp_imx952_system_manager_misc.py")


def _clock_agent_for_request():
    if _CLOCK_REQUEST_CHANNEL is None:
        return None
    if not _CLOCK_IS_AP:
        return 0
    if _CLOCK_REQUEST_CHANNEL == 0:
        return 1
    return 2


def _clock_allowed(agent_id, clock_id):
    return clock_id in _CLOCK_ALLOWED.get(agent_id, set())


def _clock_restore_header(channel):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    _write32(base + SMT_MESSAGE_HEADER, _CLOCK_PRE_HEADER)


def _clock_restore_payload(channel, words):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    index = 0
    while index < len(words):
        _write32(base + SMT_PAYLOAD + index * 4, words[index])
        index += 1


def _clock_set_name(channel, clock_id):
    if clock_id not in _CLOCK_SOURCE_NAMES:
        return
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    _write_ascii(base + SMT_PAYLOAD + 8, _CLOCK_SOURCE_NAMES[clock_id], 16)


def _clock_delegate(channel, agent_id, message_id, words):
    # The lower masked-protocol response overwrites SMT payload word 0. Restore
    # the complete captured request before reusing the core Clock handlers.
    _clock_restore_payload(channel, words)
    _process_clock(channel, message_id, agent_id)


def _clock_process_filtered(channel, agent_id, message_id, words):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE

    if message_id == 0x02:
        requested = words[0]
        supported = set([0, 1, 2, 3, 4, 5, 6, 7, 0xB, 0xC, 0xD,
                         0xE, 0xF, 0x10])
        _message_attributes(channel, requested, supported)
        return

    if message_id == 0x03:
        clock_id = words[0]
        if clock_id >= _CLOCK_COUNT:
            _set_response(channel, SCMI_NOT_FOUND, [])
            return
        _clock_delegate(channel, agent_id, message_id, words)
        attributes = _read32(base + SMT_PAYLOAD + 4)
        if not _clock_allowed(agent_id, clock_id):
            attributes |= _CLOCK_ATTR_RESTRICTED
        else:
            attributes &= (~_CLOCK_ATTR_RESTRICTED & 0xFFFFFFFF)
        _write32(base + SMT_PAYLOAD + 4, attributes)
        _clock_set_name(channel, clock_id)
        return

    if message_id == 0x0F:
        clock_id = words[0]
        if clock_id >= _CLOCK_COUNT:
            _set_response(channel, SCMI_NOT_FOUND, [])
        else:
            permissions = (_CLOCK_PERMISSION_ALL_BITS
                           if _clock_allowed(agent_id, clock_id) else 0)
            _set_response(channel, SCMI_SUCCESS, [permissions])
        return

    # NXP requires explicit clock permission for all mutating operations.
    if message_id == 0x05:  # RATE_SET: flags, clockId, rate low/high
        clock_id = words[1]
        if clock_id >= _CLOCK_COUNT:
            _set_response(channel, SCMI_NOT_FOUND, [])
        elif not _clock_allowed(agent_id, clock_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            _clock_delegate(channel, agent_id, message_id, words)
        return

    if message_id == 0x07 or message_id == 0x0D:  # CONFIG_SET / PARENT_SET
        clock_id = words[0]
        if clock_id >= _CLOCK_COUNT:
            _set_response(channel, SCMI_NOT_FOUND, [])
        elif not _clock_allowed(agent_id, clock_id):
            _set_response(channel, SCMI_DENIED, [])
        else:
            _clock_delegate(channel, agent_id, message_id, words)
        return

    # Read-only operations preserve the core model's global-ID behavior.
    _clock_delegate(channel, agent_id, message_id, words)


if (request.IsWrite and request.Offset == 0x114 and
        _CLOCK_REQUEST_CHANNEL is not None and
        ((_CLOCK_PRE_HEADER >> 10) & 0xFF) == _CLOCK_PROTOCOL):
    _clock_restore_header(_CLOCK_REQUEST_CHANNEL)
    _clock_process_filtered(
        _CLOCK_REQUEST_CHANNEL,
        _clock_agent_for_request(),
        _CLOCK_PRE_HEADER & 0xFF,
        _CLOCK_PRE_WORDS)
