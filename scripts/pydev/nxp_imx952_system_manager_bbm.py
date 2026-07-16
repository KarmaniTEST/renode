# i.MX952 NXP BBM SCMI extension layer.
#
# Layering:
#   protocol engine -> exact SMT/P2A transport -> BBM vendor extension
#
# The underlying transport and core SCMI implementation are loaded first. This
# file then overrides only BBM protocol 0x81 and Base discovery for agents that
# have BBM permissions in the pinned mx952evk generated configuration.
#
# BBM notification delivery follows NXP's normal P2A queue semantics:
#   M7   local channel 1 -> global SMT channel 1 / MU doorbell 1
#   AP-NS local channel 3 -> global SMT channel 6 / MU doorbell 1
# Functional queueing and doorbell state are modeled. Physical RTC/button event
# generation and interrupt latency remain hardware-correlation gates.

_BBM_PROTOCOL = 0x81
_BBM_VERSION = 0x00010000
_BBM_RTC_BBNSM = 0
_BBM_RTC_PCA2131 = 1
_BBM_BUTTON_0 = 0

_BBM_NOTIFY_RTC_ALARM = 1 << 0
_BBM_NOTIFY_RTC_ROLLOVER = 1 << 1
_BBM_NOTIFY_RTC_UPDATED = 1 << 2
_BBM_NOTIFY_BUTTON_DETECT = 1 << 0

_BBM_RTC_EVENT_MESSAGE_ID = 0
_BBM_BUTTON_EVENT_MESSAGE_ID = 1
_BBM_MESSAGE_TYPE_NOTIFICATION = 3
_BBM_M7_NOTIFY_CHANNEL = 1
_BBM_APNS_NOTIFY_CHANNEL = 3
_BBM_NOTIFY_QUEUE_LIMIT = 8

# Deterministic functional evidence inputs. These are not physical registers.
# RTC trigger: bits[7:0] RTC ID; bits[9:8] event (0 alarm, 1 rollover, 2 update).
# Button trigger: bit[0] resulting asserted state; every write is a detect event.
_INTERNAL_BBM_RTC_TRIGGER = 0x1E8
_INTERNAL_BBM_BUTTON_TRIGGER = 0x1EC

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

_BBM_ORIGINAL_VALUE = request.Value if request.IsWrite else 0
_BBM_ORIGINAL_GCR = _BBM_ORIGINAL_VALUE
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


def _bbm_endpoint_agent():
    return AGENT_AP_NS if _BBM_IS_AP else AGENT_M7


def _bbm_notify_channel():
    return _BBM_APNS_NOTIFY_CHANNEL if _BBM_IS_AP else _BBM_M7_NOTIFY_CHANNEL


def _bbm_notify_base():
    return SCMI_SRAM + _bbm_notify_channel() * SCMI_CHANNEL_SIZE


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


def _bbm_notification_header(message_id):
    global bbm_notify_token
    header = (((_BBM_PROTOCOL & 0xFF) << 10) |
              ((_BBM_MESSAGE_TYPE_NOTIFICATION & 0x3) << 8) |
              (message_id & 0xFF) |
              ((bbm_notify_token & 0x3FF) << 18))
    bbm_notify_token = (bbm_notify_token + 1) & 0x3FF
    return header


def _bbm_notify_channel_free():
    return (_read32(_bbm_notify_base() + SMT_CHANNEL_STATUS) &
            SMT_CHANNEL_FREE) != 0


def _bbm_try_dispatch_notification():
    if not bbm_notify_queue or not _bbm_notify_channel_free():
        return False

    message_id, flags = bbm_notify_queue.pop(0)
    base = _bbm_notify_base()
    channel = _bbm_notify_channel()
    _write32(base + SMT_CHANNEL_STATUS, 0)
    _write32(base + SMT_MESSAGE_HEADER, _bbm_notification_header(message_id))
    _write32(base + SMT_PAYLOAD, flags)
    _write32(base + SMT_LENGTH, 8)
    _write32(MU_GSR, _read32(MU_GSR) | (1 << channel))
    _update_m7_scmi_irq()
    return True


def _bbm_queue_notification(message_id, flags):
    global bbm_notify_overflow
    if len(bbm_notify_queue) >= _BBM_NOTIFY_QUEUE_LIMIT:
        bbm_notify_overflow += 1
        return False
    bbm_notify_queue.append((message_id, flags & 0xFFFFFFFF))
    _bbm_try_dispatch_notification()
    return True


def _bbm_emit_rtc_event(rtc_id, event):
    agent_id = _bbm_endpoint_agent()
    if not _bbm_has_rtc(agent_id, rtc_id):
        return False

    subscriptions = bbm_rtc_notify.get((agent_id, rtc_id), 0) & 0x7
    if event == 0:
        event_flag = _BBM_NOTIFY_RTC_ALARM
    elif event == 1:
        event_flag = _BBM_NOTIFY_RTC_ROLLOVER
    elif event == 2:
        event_flag = _BBM_NOTIFY_RTC_UPDATED
    else:
        return False

    if (subscriptions & event_flag) == 0:
        return False
    flags = ((rtc_id & 0xFF) << 24) | event_flag
    return _bbm_queue_notification(_BBM_RTC_EVENT_MESSAGE_ID, flags)


def _bbm_emit_button_event(asserted):
    global bbm_button_state
    agent_id = _bbm_endpoint_agent()
    bbm_button_state = 1 if asserted else 0
    if not _bbm_has_button(agent_id, _BBM_BUTTON_0):
        return False
    if (bbm_button_notify.get(agent_id, 0) & _BBM_NOTIFY_BUTTON_DETECT) == 0:
        return False
    return _bbm_queue_notification(
        _BBM_BUTTON_EVENT_MESSAGE_ID,
        _BBM_NOTIFY_BUTTON_DETECT,
    )


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
            bbm_rtc_notify[(agent_id, rtc_id)] = words[1] & 0x7
            _bbm_response(channel, SCMI_SUCCESS, [])

    elif message_id == 0x0B:  # BBM_BUTTON_NOTIFY
        if not _bbm_has_button(agent_id, _BBM_BUTTON_0):
            _bbm_response(channel, SCMI_DENIED, [])
        else:
            bbm_button_notify[agent_id] = words[0] & 0x1
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
    bbm_notify_queue = []
    bbm_notify_token = 0
    bbm_notify_overflow = 0
    _write32(_INTERNAL_BBM_RTC_TRIGGER, 0)
    _write32(_INTERNAL_BBM_BUTTON_TRIGGER, 0)

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

elif (request.IsWrite and request.Offset == _INTERNAL_BBM_RTC_TRIGGER and
      request.Length == 4):
    rtc_id = _BBM_ORIGINAL_VALUE & 0xFF
    event = (_BBM_ORIGINAL_VALUE >> 8) & 0x3
    _bbm_emit_rtc_event(rtc_id, event)
    _write32(_INTERNAL_BBM_RTC_TRIGGER, 0)

elif (request.IsWrite and request.Offset == _INTERNAL_BBM_BUTTON_TRIGGER and
      request.Length == 4):
    _bbm_emit_button_event((_BBM_ORIGINAL_VALUE & 0x1) != 0)
    _write32(_INTERNAL_BBM_BUTTON_TRIGGER, 0)

elif (request.IsWrite and
      request.Offset == (_bbm_notify_base() + SMT_CHANNEL_STATUS) and
      request.Length == 4 and (_BBM_ORIGINAL_VALUE & SMT_CHANNEL_FREE)):
    _bbm_try_dispatch_notification()
