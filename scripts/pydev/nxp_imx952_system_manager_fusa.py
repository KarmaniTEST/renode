# i.MX952 source-derived SCMI FuSa priority-notification layer.
#
# Layering:
#   core -> SMT/P2A -> BBM -> MISC -> Clock -> Pinctrl -> FuSa priority
#
# The mx952evk configuration grants FuSa access only to the M7 S-EENV agent and
# assigns local M7 channel 2 (global SMT channel 2 / MU doorbell 2) to priority
# notifications. This layer implements a bounded functional FuSa first slice and
# priority queue. Physical fault generation and IRQ latency remain outside scope.

_FUSA_PROTOCOL = 0x83
_FUSA_VERSION = 0x00010000
_FUSA_FAULT_COUNT = 89
_FUSA_SEENV_ID_COUNT = 1
_FUSA_SEENV_LM_COUNT = 1

_FUSA_FEENV_STATE_INIT = 0
_FUSA_FEENV_STATE_PRE_SAFETY = 1
_FUSA_FEENV_STATE_SAFETY_RUNTIME = 2
_FUSA_FEENV_STATE_SOC_TERMINATING = 3

_FUSA_SEENV_STATE_DISABLED = 0
_FUSA_SEENV_STATE_INIT = 1
_FUSA_SEENV_STATE_SAFETY_READY = 2
_FUSA_SEENV_STATE_SAFETY_RUNTIME = 3
_FUSA_SEENV_STATE_TERMINAL = 4

_FUSA_ID_DISCOVER = 0xFFFFFFFF
_FUSA_NOTIFY_FEENV_STATE_EVENT = 0
_FUSA_PRIORITY_CHANNEL = 2
_FUSA_PRIORITY_QUEUE_LIMIT = 8

# Deterministic test/evidence input. Bits[7:0] F-EENV state, Bits[15:8] MSEL.
# This is not a production hardware register and is kept outside the public SCMI
# protocol surface.
_INTERNAL_FUSA_FEENV_TRIGGER = 0x1E4

_FUSA_ORIGINAL_VALUE = request.Value if request.IsWrite else 0
_FUSA_IS_AP = size >= 0x1400
_FUSA_REQUEST_CHANNEL = None
_FUSA_PRE_HEADER = 0
_FUSA_PRE_WORDS = [0] * 12
_FUSA_INTERCEPT = False

if request.IsWrite and request.Offset == 0x114:
    if _FUSA_IS_AP and (_FUSA_ORIGINAL_VALUE & (1 << 2)):
        _FUSA_REQUEST_CHANNEL = 2
    elif _FUSA_ORIGINAL_VALUE & 0x1:
        _FUSA_REQUEST_CHANNEL = 0

    if _FUSA_REQUEST_CHANNEL is not None:
        _fusa_base = 0x1000 + _FUSA_REQUEST_CHANNEL * 0x80
        _FUSA_PRE_HEADER = _read32(_fusa_base + 0x18)
        _fusa_index = 0
        while _fusa_index < len(_FUSA_PRE_WORDS):
            _FUSA_PRE_WORDS[_fusa_index] = _read32(
                _fusa_base + 0x1C + _fusa_index * 4)
            _fusa_index += 1

        _fusa_protocol = (_FUSA_PRE_HEADER >> 10) & 0xFF
        _fusa_message = _FUSA_PRE_HEADER & 0xFF
        _FUSA_INTERCEPT = (
            _fusa_protocol == _FUSA_PROTOCOL or
            (not _FUSA_IS_AP and _fusa_protocol == 0x10 and
             _fusa_message in set([0x01, 0x06]))
        )
        if _FUSA_INTERCEPT:
            _write32(
                _fusa_base + 0x18,
                (0xFF << 10) | (_FUSA_PRE_HEADER & 0x3FF),
            )

execfile("scripts/pydev/nxp_imx952_system_manager_pinctrl.py")


def _fusa_agent_for_request():
    if _FUSA_REQUEST_CHANNEL is None:
        return None
    if not _FUSA_IS_AP:
        return 0
    if _FUSA_REQUEST_CHANNEL == 0:
        return 1
    return 2


def _fusa_restore_request(channel):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    _write32(base + SMT_MESSAGE_HEADER, _FUSA_PRE_HEADER)
    index = 0
    while index < len(_FUSA_PRE_WORDS):
        _write32(base + SMT_PAYLOAD + index * 4, _FUSA_PRE_WORDS[index])
        index += 1


def _fusa_protocols_for_agent(agent_id):
    # Preserve all lower-layer source-derived protocols (including BBM and MISC)
    # before adding the M7-only FuSa surface.
    protocols = list(_misc_protocols_for_agent(agent_id))
    if agent_id == AGENT_M7 and _FUSA_PROTOCOL not in protocols:
        protocols.append(_FUSA_PROTOCOL)
    return protocols


def _fusa_process_base(channel, message_id, agent_id, words):
    protocols = _fusa_protocols_for_agent(agent_id)
    if message_id == 0x01:
        _set_response(channel, SCMI_SUCCESS, [(3 << 8) | len(protocols)])
        return

    if message_id == 0x06:
        skip = words[0]
        if skip >= len(protocols):
            _set_response(channel, SCMI_INVALID_PARAMETERS, [0])
            return
        remaining = protocols[skip:]
        packed_words = []
        index = 0
        while index < len(remaining):
            packed = 0
            shift = 0
            while shift < 32 and index < len(remaining):
                packed |= (remaining[index] & 0xFF) << shift
                shift += 8
                index += 1
            packed_words.append(packed)
        _set_response(channel, SCMI_SUCCESS, [len(remaining)] + packed_words)
        return

    _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _fusa_process(channel, message_id, agent_id, words):
    global fusa_seenv_state, fusa_last_ping_cookie
    if agent_id != AGENT_M7:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])
        return

    supported = set([0x00, 0x01, 0x02, 0x03, 0x05, 0x06, 0x07, 0x10])
    if message_id == 0x00:
        _set_response(channel, SCMI_SUCCESS, [_FUSA_VERSION])
    elif message_id == 0x01:
        attributes1 = (
            (_FUSA_FAULT_COUNT << 16) |
            (_FUSA_SEENV_ID_COUNT << 8) |
            _FUSA_SEENV_LM_COUNT
        )
        _set_response(channel, SCMI_SUCCESS, [attributes1, 0])
    elif message_id == 0x02:
        _message_attributes(channel, words[0], supported)
    elif message_id == 0x03:
        _set_response(
            channel,
            SCMI_SUCCESS,
            [fusa_feenv_state, fusa_msel_mode],
        )
    elif message_id == 0x05:
        fusa_feenv_notify[agent_id] = (words[0] & 0x1) != 0
        _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x06:
        requested = words[0]
        if requested not in set([0, _FUSA_ID_DISCOVER]):
            _set_response(channel, SCMI_NOT_FOUND, [])
        else:
            _set_response(
                channel,
                SCMI_SUCCESS,
                [0, LM_M7, fusa_seenv_state],
            )
    elif message_id == 0x07:
        requested_state = words[0]
        if requested_state > _FUSA_SEENV_STATE_TERMINAL:
            _set_response(channel, SCMI_INVALID_PARAMETERS, [])
        else:
            fusa_seenv_state = requested_state
            fusa_last_ping_cookie = words[1]
            _set_response(channel, SCMI_SUCCESS, [])
    elif message_id == 0x10:
        if words[0] <= _FUSA_VERSION:
            _set_response(channel, SCMI_SUCCESS, [])
        else:
            _set_response(channel, SCMI_NOT_SUPPORTED, [])
    else:
        _set_response(channel, SCMI_NOT_SUPPORTED, [])


def _fusa_priority_base():
    return SCMI_SRAM + _FUSA_PRIORITY_CHANNEL * SCMI_CHANNEL_SIZE


def _fusa_priority_channel_free():
    return (_read32(_fusa_priority_base() + SMT_CHANNEL_STATUS) &
            SMT_CHANNEL_FREE) != 0


def _fusa_priority_header(message_id):
    global fusa_priority_token
    header = (
        ((_FUSA_PROTOCOL & 0xFF) << 10) |
        (3 << 8) |
        (message_id & 0xFF) |
        ((fusa_priority_token & 0x3FF) << 18)
    )
    fusa_priority_token = (fusa_priority_token + 1) & 0x3FF
    return header


def _fusa_try_dispatch_priority():
    if _FUSA_IS_AP or not fusa_priority_queue:
        return False
    if not _fusa_priority_channel_free():
        return False

    state, msel = fusa_priority_queue.pop(0)
    base = _fusa_priority_base()
    _write32(base + SMT_CHANNEL_STATUS, 0)
    _write32(
        base + SMT_MESSAGE_HEADER,
        _fusa_priority_header(_FUSA_NOTIFY_FEENV_STATE_EVENT),
    )
    _write32(base + SMT_PAYLOAD, state)
    _write32(base + SMT_PAYLOAD + 4, msel)
    _write32(base + SMT_LENGTH, 12)
    _write32(MU_GSR, _read32(MU_GSR) | (1 << _FUSA_PRIORITY_CHANNEL))
    _update_m7_scmi_irq()
    return True


def _fusa_queue_feenv_event(state, msel):
    global fusa_priority_overflow
    if not fusa_feenv_notify.get(AGENT_M7, False):
        return False
    if len(fusa_priority_queue) >= _FUSA_PRIORITY_QUEUE_LIMIT:
        fusa_priority_overflow += 1
        return False
    fusa_priority_queue.append((state, msel))
    _fusa_try_dispatch_priority()
    return True


if request.IsInit:
    fusa_feenv_state = _FUSA_FEENV_STATE_PRE_SAFETY
    fusa_msel_mode = 0
    fusa_seenv_state = _FUSA_SEENV_STATE_INIT
    fusa_last_ping_cookie = 0
    fusa_feenv_notify = {AGENT_M7: False}
    fusa_priority_queue = []
    fusa_priority_token = 0
    fusa_priority_overflow = 0
    _write32(_INTERNAL_FUSA_FEENV_TRIGGER, 0)

elif (request.IsWrite and request.Offset == 0x114 and
      _FUSA_REQUEST_CHANNEL is not None and _FUSA_INTERCEPT):
    _fusa_restore_request(_FUSA_REQUEST_CHANNEL)
    protocol_id = (_FUSA_PRE_HEADER >> 10) & 0xFF
    message_id = _FUSA_PRE_HEADER & 0xFF
    if protocol_id == _FUSA_PROTOCOL:
        _fusa_process(
            _FUSA_REQUEST_CHANNEL,
            message_id,
            _fusa_agent_for_request(),
            _FUSA_PRE_WORDS,
        )
    else:
        _fusa_process_base(
            _FUSA_REQUEST_CHANNEL,
            message_id,
            _fusa_agent_for_request(),
            _FUSA_PRE_WORDS,
        )

elif (request.IsWrite and not _FUSA_IS_AP and
      request.Offset == _INTERNAL_FUSA_FEENV_TRIGGER and request.Length == 4):
    requested_state = _FUSA_ORIGINAL_VALUE & 0xFF
    requested_msel = (_FUSA_ORIGINAL_VALUE >> 8) & 0xFF
    if requested_state <= _FUSA_FEENV_STATE_SOC_TERMINATING:
        fusa_feenv_state = requested_state
        fusa_msel_mode = requested_msel
        _fusa_queue_feenv_event(requested_state, requested_msel)
    _write32(_INTERNAL_FUSA_FEENV_TRIGGER, 0)

elif (request.IsWrite and not _FUSA_IS_AP and
      request.Offset == (_fusa_priority_base() + SMT_CHANNEL_STATUS) and
      request.Length == 4 and (_FUSA_ORIGINAL_VALUE & SMT_CHANNEL_FREE)):
    _fusa_try_dispatch_priority()
