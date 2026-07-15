# i.MX952 NXP BBM SCMI extension layer.
#
# Layering:
#   protocol engine -> exact SMT/P2A transport -> BBM vendor extension
#
# The underlying transport and core SCMI implementation are loaded first. This
# file then overrides only BBM protocol 0x81 and Base discovery for agents that
# have BBM permissions in the pinned mx952evk generated configuration.

_BBM_PROTOCOL = 0x81
_BBM_VERSION = 0x00010000
_BBM_RTC_BBNSM = 0
_BBM_RTC_PCA2131 = 1
_BBM_BUTTON_0 = 0

_BBM_ALLOWED_AGENTS = set([0, 2])  # M7, AP-NS
_BBM_GPR_WRITE = {
    0: set(),
    2: set([4, 5, 6, 7]),
}
_BBM_RTC_ACCESS = {
    0: set([_BBM_RTC_BBNSM, _BBM_RTC_PCA2131]),
    2: set([_BBM_RTC_BBNSM, _BBM_RTC_PCA2131]),
}
_BBM_BUTTON_ACCESS = {
    0: set([_BBM_BUTTON_0]),
    2: set([_BBM_BUTTON_0]),
}
_BBM_RTC_NAMES = {
    _BBM_RTC_BBNSM: "BBNSM",
    _BBM_RTC_PCA2131: "PCA2131",
}

_BBM_ORIGINAL_GCR = request.Value if request.IsWrite else 0
_BBM_IS_AP = size >= 0x1400
_BBM_REQUEST_CHANNEL = None
_BBM_PRE_HEADER = 0
_BBM_PRE_WORDS = [0, 0, 0, 0, 0]

# Capture the request before the lower layers replace it with a response.
if request.IsWrite and request.Offset == 0x114:
    if _BBM_IS_AP and (_BBM_ORIGINAL_GCR & (1 << 2)):
        _BBM_REQUEST_CHANNEL = 2
    elif _BBM_ORIGINAL_GCR & 0x1:
        _BBM_REQUEST_CHANNEL = 0

    if _BBM_REQUEST_CHANNEL is not None:
        _bbm_base = 0x1000 + _BBM_REQUEST_CHANNEL * 0x80
        _BBM_PRE_HEADER = _read32(_bbm_base + 0x18)
        _bbm_index = 0
        while _bbm_index < len(_BBM_PRE_WORDS):
            _BBM_PRE_WORDS[_bbm_index] = _read32(
                _bbm_base + 0x1C + _bbm_index * 4)
            _bbm_index += 1

execfile("scripts/pydev/nxp_imx952_system_manager_transport.py")


def _bbm_agent_for_request():
    if _BBM_REQUEST_CHANNEL is None:
        return None
    if not _BBM_IS_AP:
        return AGENT_M7
    if _BBM_REQUEST_CHANNEL == 0:
        return AGENT_AP_S
    return AGENT_AP_NS


def _bbm_response(channel, status, words, text=None, text_offset=4):
    _set_response(channel, status, words, text, text_offset, 16)


def _bbm_message_attributes(channel, requested):
    supported = set([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
                     0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x10])
    if requested in supported:
        _bbm_response(channel, SCMI_SUCCESS, [0])
    else:
        _bbm_response(channel, SCMI_NOT_FOUND, [])


def _bbm_has_rtc(agent_id, rtc_id):
    return rtc_id in _BBM_RTC_ACCESS.get(agent_id, set())


def _bbm_has_button(agent_id, button_id):
    return button_id in _BBM_BUTTON_ACCESS.get(agent_id, set())


def _process_bbm(channel, agent_id, message_id, words):
    if agent_id not in _BBM_ALLOWED_AGENTS:
        _bbm_response(channel, SCMI_DENIED, [])
        return

    if message_id == 0x00:  # PROTOCOL_VERSION
        _bbm_response(channel, SCMI_SUCCESS, [_BBM_VERSION])

    elif message_id == 0x01:  # PROTOCOL_ATTRIBUTES
        # 2 RTCs in bits 23:16, 8 device GPRs in bits 15:0.
        _bbm_response(channel, SCMI_SUCCESS, [(2 << 16) | 8])

    elif message_id == 0x02:  # PROTOCOL_MESSAGE_ATTRIBUTES
        _bbm_message_attributes(channel, words[0])

    elif message_id == 0x03:  # BBM_GPR_SET
        index = words[0]
        if index not in _BBM_GPR_WRITE.get(agent_id, set()):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            bbm_gprs[index] = words[1] & 0xFFFFFFFF
            _bbm_response(channel, SCMI_SUCCESS, [])

    elif message_id == 0x04:  # BBM_GPR_GET
        index = words[0]
        if index not in _BBM_GPR_WRITE.get(agent_id, set()):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            _bbm_response(channel, SCMI_SUCCESS, [bbm_gprs.get(index, 0)])

    elif message_id == 0x05:  # BBM_RTC_ATTRIBUTES
        rtc_id = words[0]
        if not _bbm_has_rtc(agent_id, rtc_id):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            # Functional timing description: 32-bit seconds, no sub-second
            # tick field, one logical tick per second. Physical correlation is
            # a later qualification gate.
            attributes = (32 << 24) | 1
            _bbm_response(channel, SCMI_SUCCESS, [attributes],
                          _BBM_RTC_NAMES[rtc_id], 8)

    elif message_id == 0x06:  # BBM_RTC_TIME_SET
        rtc_id = words[0]
        if not _bbm_has_rtc(agent_id, rtc_id):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            value = (words[3] << 32) | words[2]
            bbm_rtc_times[rtc_id] = value
            _bbm_response(channel, SCMI_SUCCESS, [])

    elif message_id == 0x07:  # BBM_RTC_TIME_GET
        rtc_id = words[0]
        if not _bbm_has_rtc(agent_id, rtc_id):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            value = bbm_rtc_times.get(rtc_id, 0)
            _bbm_response(channel, SCMI_SUCCESS,
                          [value & 0xFFFFFFFF, (value >> 32) & 0xFFFFFFFF])

    elif message_id == 0x08:  # BBM_RTC_ALARM_SET
        rtc_id = words[0]
        if not _bbm_has_rtc(agent_id, rtc_id):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            enabled = (words[1] & 1) != 0
            value = (words[3] << 32) | words[2]
            bbm_rtc_alarms[rtc_id] = (enabled, value)
            _bbm_response(channel, SCMI_SUCCESS, [])

    elif message_id == 0x09:  # BBM_BUTTON_GET
        if not _bbm_has_button(agent_id, _BBM_BUTTON_0):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            _bbm_response(channel, SCMI_SUCCESS, [bbm_button_state])

    elif message_id == 0x0A:  # BBM_RTC_NOTIFY
        rtc_id = words[0]
        if not _bbm_has_rtc(agent_id, rtc_id):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            bbm_rtc_notify[(agent_id, rtc_id)] = words[1]
            _bbm_response(channel, SCMI_SUCCESS, [])

    elif message_id == 0x0B:  # BBM_BUTTON_NOTIFY
        if not _bbm_has_button(agent_id, _BBM_BUTTON_0):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            bbm_button_notify[agent_id] = words[0]
            _bbm_response(channel, SCMI_SUCCESS, [])

    elif message_id == 0x0C:  # BBM_RTC_STATE
        rtc_id = words[0]
        if not _bbm_has_rtc(agent_id, rtc_id):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            _bbm_response(channel, SCMI_SUCCESS, [bbm_rtc_states.get(rtc_id, 0)])

    elif message_id == 0x10:  # NEGOTIATE_PROTOCOL_VERSION
        if words[0] <= _BBM_VERSION:
            _bbm_response(channel, SCMI_SUCCESS, [])
        else:
            _bbm_response(channel, SCMI_NOT_SUPPORTED, [])

    else:
        _bbm_response(channel, SCMI_NOT_SUPPORTED, [])


def _bbm_protocols_for_agent(agent_id):
    protocols = list(_protocols_for_agent(agent_id))
    if agent_id in _BBM_ALLOWED_AGENTS:
        protocols.append(_BBM_PROTOCOL)
    return protocols


def _override_base_discovery(channel, agent_id, message_id, words):
    protocols = _bbm_protocols_for_agent(agent_id)
    if message_id == 0x01:
        _bbm_response(channel, SCMI_SUCCESS, [(3 << 8) | len(protocols)])
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
        _bbm_response(channel, SCMI_SUCCESS,
                      [len(remaining)] + packed_words)


if request.IsInit:
    bbm_gprs = {}
    bbm_rtc_times = {_BBM_RTC_BBNSM: 0, _BBM_RTC_PCA2131: 0}
    bbm_rtc_alarms = {}
    bbm_rtc_notify = {}
    bbm_button_notify = {}
    bbm_rtc_states = {_BBM_RTC_BBNSM: 0, _BBM_RTC_PCA2131: 0}
    bbm_button_state = 0

elif (request.IsWrite and request.Offset == 0x114 and
      _BBM_REQUEST_CHANNEL is not None):
    agent_id = _bbm_agent_for_request()
    message_id = _BBM_PRE_HEADER & 0xFF
    protocol_id = (_BBM_PRE_HEADER >> 10) & 0xFF

    if protocol_id == _BBM_PROTOCOL:
        _process_bbm(_BBM_REQUEST_CHANNEL, agent_id, message_id, _BBM_PRE_WORDS)

    elif protocol_id == SCMI_PROTOCOL_BASE and message_id in set([0x01, 0x06]):
        _override_base_discovery(
            _BBM_REQUEST_CHANNEL, agent_id, message_id, _BBM_PRE_WORDS)
