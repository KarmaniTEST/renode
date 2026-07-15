# i.MX952 NXP MISC SCMI extension layer.
#
# Layering:
#   core protocol engine -> exact SMT/P2A transport -> BBM -> MISC
#
# The first qualified MISC slice is AP-NS only. It exposes the source-assigned
# COMBO_PHY control plus safe target/config/board metadata. Physical fuse-derived
# numeric silicon fields remain zero until physical-EVK evidence is captured.

_MISC_PROTOCOL = 0x84
_MISC_VERSION = 0x00010001
_MISC_COMBO_PHY = 9
_MISC_DEVICE_CONTROL_COUNT = 10
_MISC_BOARD_CONTROL_COUNT = 8
_MISC_REASON_COUNT = 32
_MISC_ALLOWED_AGENT = 2  # AP-NS

_MISC_REASON_NAMES = {
    0: "CM33_LOCKUP", 1: "CM33_SWREQ", 2: "CM7_LOCKUP", 3: "CM7_SWREQ",
    4: "FCCU", 5: "JTAG_SW", 6: "ELE", 7: "TEMPSENSE",
    8: "WDOG1", 9: "WDOG2", 10: "WDOG3", 11: "WDOG4", 12: "WDOG5",
    13: "JTAG", 14: "CM33_EXC", 15: "BBM", 16: "SW", 17: "SM_ERR",
    18: "FUSA_SRECO", 19: "PMIC", 31: "POR",
}

_MISC_ORIGINAL_GCR = request.Value if request.IsWrite else 0
_MISC_IS_AP = size >= 0x1400
_MISC_REQUEST_CHANNEL = None
_MISC_PRE_HEADER = 0
_MISC_PRE_WORDS = [0] * 20

if request.IsWrite and request.Offset == 0x114:
    if _MISC_IS_AP and (_MISC_ORIGINAL_GCR & (1 << 2)):
        _MISC_REQUEST_CHANNEL = 2
    elif (not _MISC_IS_AP) and (_MISC_ORIGINAL_GCR & 0x1):
        _MISC_REQUEST_CHANNEL = 0

    if _MISC_REQUEST_CHANNEL is not None:
        _misc_base = 0x1000 + _MISC_REQUEST_CHANNEL * 0x80
        _MISC_PRE_HEADER = _read32(_misc_base + 0x18)
        _misc_index = 0
        while _misc_index < len(_MISC_PRE_WORDS):
            _MISC_PRE_WORDS[_misc_index] = _read32(
                _misc_base + 0x1C + _misc_index * 4)
            _misc_index += 1

execfile("scripts/pydev/nxp_imx952_system_manager_bbm.py")


def _misc_agent_for_request():
    if _MISC_REQUEST_CHANNEL is None:
        return None
    if not _MISC_IS_AP:
        return AGENT_M7
    if _MISC_REQUEST_CHANNEL == 0:
        return AGENT_AP_S
    return AGENT_AP_NS


def _misc_base(channel):
    return SCMI_SRAM + channel * SCMI_CHANNEL_SIZE


def _misc_finish(channel, payload_length):
    base = _misc_base(channel)
    _write32(base + SMT_LENGTH, payload_length + 4)
    _write32(base + SMT_CHANNEL_STATUS, SMT_CHANNEL_FREE)


def _misc_status(channel, status):
    base = _misc_base(channel)
    _write32(base + SMT_PAYLOAD, status)
    _misc_finish(channel, 4)


def _misc_words(channel, status, words):
    base = _misc_base(channel)
    _write32(base + SMT_PAYLOAD, status)
    index = 0
    for word in words:
        _write32(base + SMT_PAYLOAD + 4 + index * 4, word)
        index += 1
    _misc_finish(channel, 4 + 4 * len(words))


def _misc_text_response(channel, status, words, text, text_offset, text_size=16):
    base = _misc_base(channel)
    _write32(base + SMT_PAYLOAD, status)
    index = 0
    for word in words:
        _write32(base + SMT_PAYLOAD + 4 + index * 4, word)
        index += 1
    _write_ascii(base + SMT_PAYLOAD + text_offset, text, text_size)
    _misc_finish(channel, max(4 + 4 * len(words), text_offset + text_size))


def _misc_supported_messages():
    return set([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x10,
                0x20, 0x21, 0x22])


def _misc_protocols_for_agent(agent_id):
    protocols = list(_bbm_protocols_for_agent(agent_id))
    if agent_id == _MISC_ALLOWED_AGENT:
        protocols.append(_MISC_PROTOCOL)
    return protocols


def _override_misc_base(channel, agent_id, message_id, words):
    protocols = _misc_protocols_for_agent(agent_id)
    if message_id == 0x01:
        _misc_words(channel, SCMI_SUCCESS, [(3 << 8) | len(protocols)])
    elif message_id == 0x06:
        skip = words[0]
        remaining = protocols[skip:]
        packed_words = []
        index = 0
        while index < len(remaining):
            packed = 0
            shift = 0
            while shift < 32 and index < len(remaining):
                packed |= (remaining[index] & 0xFF) << shift
                index += 1
                shift += 8
            packed_words.append(packed)
        _misc_words(channel, SCMI_SUCCESS, [len(remaining)] + packed_words)


def _misc_control_allowed(agent_id, ctrl_id):
    return agent_id == _MISC_ALLOWED_AGENT and ctrl_id == _MISC_COMBO_PHY


def _process_misc(channel, agent_id, message_id, words):
    if agent_id != _MISC_ALLOWED_AGENT:
        _misc_status(channel, SCMI_DENIED)
        return

    if message_id == 0x00:  # PROTOCOL_VERSION
        _misc_words(channel, SCMI_SUCCESS, [_MISC_VERSION])

    elif message_id == 0x01:  # PROTOCOL_ATTRIBUTES
        attributes = ((_MISC_BOARD_CONTROL_COUNT & 0xFF) << 24) | \
                     ((_MISC_REASON_COUNT & 0xFF) << 16) | \
                     (_MISC_DEVICE_CONTROL_COUNT & 0xFFFF)
        _misc_words(channel, SCMI_SUCCESS, [attributes])

    elif message_id == 0x02:  # PROTOCOL_MESSAGE_ATTRIBUTES
        if words[0] in _misc_supported_messages():
            _misc_words(channel, SCMI_SUCCESS, [0])
        else:
            _misc_status(channel, SCMI_NOT_FOUND)

    elif message_id == 0x03:  # MISC_CONTROL_SET
        ctrl_id = words[0]
        num_val = words[1]
        if not _misc_control_allowed(agent_id, ctrl_id):
            _misc_status(channel, SCMI_DENIED)
        elif num_val > 8:
            _misc_status(channel, SCMI_INVALID_PARAMETERS)
        else:
            misc_controls[ctrl_id] = list(words[2:2 + num_val])
            _misc_status(channel, SCMI_SUCCESS)

    elif message_id == 0x04:  # MISC_CONTROL_GET
        ctrl_id = words[0]
        if not _misc_control_allowed(agent_id, ctrl_id):
            _misc_status(channel, SCMI_DENIED)
        else:
            values = misc_controls.get(ctrl_id, [0])
            _misc_words(channel, SCMI_SUCCESS, [len(values)] + values)

    elif message_id == 0x05:  # MISC_CONTROL_ACTION
        ctrl_id = words[0]
        if not _misc_control_allowed(agent_id, ctrl_id):
            _misc_status(channel, SCMI_DENIED)
        else:
            # Action semantics are control-specific and not yet source-qualified
            # for COMBO_PHY. The message exists but the action is unavailable.
            _misc_status(channel, SCMI_NOT_SUPPORTED)

    elif message_id == 0x06:  # MISC_DISCOVER_BUILD_INFO
        base = _misc_base(channel)
        _write32(base + SMT_PAYLOAD, SCMI_SUCCESS)
        _write32(base + SMT_PAYLOAD + 4, 0)  # not an NXP production build number
        _write32(base + SMT_PAYLOAD + 8, 0x44F76DCB)  # pinned source commit prefix
        _write_ascii(base + SMT_PAYLOAD + 12, "pinned-source", 16)
        _write_ascii(base + SMT_PAYLOAD + 28, "model", 16)
        _misc_finish(channel, 44)

    elif message_id == 0x07:  # MISC_ROM_PASSOVER_GET
        _misc_status(channel, SCMI_NOT_SUPPORTED)

    elif message_id == 0x08:  # MISC_CONTROL_NOTIFY
        ctrl_id = words[0]
        if not _misc_control_allowed(agent_id, ctrl_id):
            _misc_status(channel, SCMI_DENIED)
        else:
            misc_control_notify[(agent_id, ctrl_id)] = words[1]
            _misc_status(channel, SCMI_SUCCESS)

    elif message_id == 0x09:  # MISC_REASON_ATTRIBUTES
        reason_id = words[0]
        if reason_id < 0 or reason_id >= _MISC_REASON_COUNT:
            _misc_status(channel, SCMI_NOT_FOUND)
        else:
            _misc_text_response(channel, SCMI_SUCCESS, [0],
                                _MISC_REASON_NAMES.get(reason_id,
                                                       "REASON-%d" % reason_id),
                                8, 16)

    elif message_id == 0x0A:  # MISC_RESET_REASON
        # Deterministic POR baseline: valid bit + reason 31. No extended info.
        _misc_words(channel, SCMI_SUCCESS, [0x8000001F, 0x8000001F])

    elif message_id == 0x0B:  # MISC_SI_INFO
        # Numeric fields are physical/fuse-derived and intentionally remain zero
        # until captured from the selected EVK B0 reference.
        _misc_text_response(channel, SCMI_SUCCESS, [0, 0, 0],
                            "i.MX952 B0", 16, 16)

    elif message_id == 0x0C:  # MISC_CFG_INFO
        _misc_text_response(channel, SCMI_SUCCESS, [0],
                            "mx952evk", 8, 16)

    elif message_id == 0x0D:  # MISC_SYSLOG
        # No modeled device log words yet; valid empty functional log.
        _misc_words(channel, SCMI_SUCCESS, [0])

    elif message_id == 0x0E:  # MISC_BOARD_INFO
        _misc_text_response(channel, SCMI_SUCCESS, [0],
                            "i.MX952 EVK", 8, 16)

    elif message_id == 0x10:  # NEGOTIATE_PROTOCOL_VERSION
        if words[0] <= _MISC_VERSION:
            _misc_status(channel, SCMI_SUCCESS)
        else:
            _misc_status(channel, SCMI_NOT_SUPPORTED)

    elif message_id == 0x20 or message_id == 0x21:
        # Extended COMBO_PHY access is not qualified in this first slice.
        _misc_status(channel, SCMI_NOT_SUPPORTED)

    elif message_id == 0x22:  # MISC_DDR_INFO_GET
        region_id = words[0]
        if region_id != 0:
            _misc_status(channel, SCMI_NOT_FOUND)
        else:
            # Current full candidate models one 2 GiB DDR region at
            # 0x80000000..0xFFFFFFFF. Type/speed are left unclaimed.
            attributes = (1 << 16) | (2 << 8)
            _misc_words(channel, SCMI_SUCCESS,
                        [attributes, 0, 0x80000000, 0, 0xFFFFFFFF, 0])

    else:
        _misc_status(channel, SCMI_NOT_SUPPORTED)


if request.IsInit:
    misc_controls = {_MISC_COMBO_PHY: [0]}
    misc_control_notify = {}

elif (request.IsWrite and request.Offset == 0x114 and
      _MISC_REQUEST_CHANNEL is not None):
    agent_id = _misc_agent_for_request()
    message_id = _MISC_PRE_HEADER & 0xFF
    protocol_id = (_MISC_PRE_HEADER >> 10) & 0xFF

    if protocol_id == _MISC_PROTOCOL:
        _process_misc(_MISC_REQUEST_CHANNEL, agent_id, message_id,
                      _MISC_PRE_WORDS)

    elif protocol_id == SCMI_PROTOCOL_BASE and message_id in set([0x01, 0x06]):
        _override_misc_base(_MISC_REQUEST_CHANNEL, agent_id, message_id,
                            _MISC_PRE_WORDS)
