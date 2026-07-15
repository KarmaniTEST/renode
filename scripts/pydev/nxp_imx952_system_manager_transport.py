# i.MX952 System Manager transport/topology wrapper.
#
# The source-derived protocol implementation remains in
# nxp_imx952_system_manager_full.py. This wrapper aligns the exposed SMT channel
# layout with NXP's generated mx952evk config_smt.h and adds a functional P2A
# notification path without changing the frozen engineering model.
#
# Source-derived local channel layout:
#
# M7 endpoint (global channels 0/1/2):
#   local 0 -> M7 A2P request
#   local 1 -> M7 P2A notification
#   local 2 -> M7 P2A priority notification
#
# AP endpoint (global channels 3/4/5/6):
#   local 0 -> AP-S  A2P request
#   local 1 -> AP-S  P2A notification
#   local 2 -> AP-NS A2P request
#   local 3 -> AP-NS P2A notification
#
# P2A delivery remains FUNCTIONAL_MODEL evidence: the notification buffer and
# mailbox-doorbell pending state are modeled, but silicon interrupt latency is
# not claimed until physical-EVK correlation exists.

# Private implementation offsets used only to communicate a remote P2A event
# between the two PythonPeripheral instances. They are not part of the public
# i.MX952 hardware contract and must never be used by guest software.
_INTERNAL_AP_NS_LMM_SUBSCRIPTION = 0x1E0
_INTERNAL_REMOTE_GSR_SET = 0x1F0

_AP_ENDPOINT_BASE = 0x445B0000
_SCMI_SRAM_OFFSET = 0x1000
_SCMI_CHANNEL_SIZE_BYTES = 0x80
_MU_GCR_OFFSET = 0x114

_SCMI_MESSAGE_TYPE_NOTIFICATION = 3
_LMM_EVENT_MESSAGE_ID = 0
_LMM_EVENT_SHUTDOWN = 1 << 1
_LMM_EVENT_SUSPEND = 1 << 2
_LMM_EVENT_WAKE = 1 << 3

_original_request_value = request.Value if request.IsWrite else 0
# Keep AP at 0x1400 so the underlying protocol engine continues to distinguish
# it from the M7 endpoint. The transport wrapper uses four local AP channels.
_is_ap_endpoint = size >= 0x1400

# Capture AP-NS LMM_NOTIFY request fields before the protocol engine overwrites
# the request payload with the response status.
_pre_ap_ns_lmm_notify_flags = None
if (request.IsWrite and request.Offset == _MU_GCR_OFFSET and
        _is_ap_endpoint and (_original_request_value & (1 << 2))):
    request_base = _SCMI_SRAM_OFFSET + 2 * _SCMI_CHANNEL_SIZE_BYTES
    header = _read32(request_base + 0x18)
    message_id = header & 0xFF
    protocol_id = (header >> 10) & 0xFF
    if protocol_id == 0x80 and message_id == 0x09:
        _pre_ap_ns_lmm_notify_flags = _read32(request_base + 0x1C + 4)

# The base protocol engine only knows its previous request-channel dispatch.
# Present it with A2P local bit 0; AP-NS local bit 2 is processed explicitly
# below. P2A bits are never dispatched as requests.
if request.IsWrite and request.Offset == _MU_GCR_OFFSET:
    request.Value = _original_request_value & 0x1

execfile("scripts/pydev/nxp_imx952_system_manager_full.py")


def _transport_channel_base(channel):
    return SCMI_SRAM + channel * SCMI_CHANNEL_SIZE


def _notification_header(protocol_id, message_id):
    return ((protocol_id & 0xFF) << 10) | \
           ((_SCMI_MESSAGE_TYPE_NOTIFICATION & 0x3) << 8) | \
           (message_id & 0xFF)


def _write_remote_notification(endpoint_base, channel, protocol_id, message_id, words):
    machine = _get_machine()
    if machine is None:
        return False

    channel_base = endpoint_base + _SCMI_SRAM_OFFSET + \
                   channel * _SCMI_CHANNEL_SIZE_BYTES

    # Channel busy/pending while the P2A message is available.
    machine.SystemBus.WriteDoubleWord(channel_base + SMT_CHANNEL_STATUS, 0)
    machine.SystemBus.WriteDoubleWord(
        channel_base + SMT_MESSAGE_HEADER,
        _notification_header(protocol_id, message_id))

    index = 0
    for word in words:
        machine.SystemBus.WriteDoubleWord(
            channel_base + SMT_PAYLOAD + index * 4,
            word & 0xFFFFFFFF)
        index += 1

    # SMT length includes the 4-byte SCMI message header.
    machine.SystemBus.WriteDoubleWord(
        channel_base + SMT_LENGTH,
        4 + 4 * len(words))

    # Cross-instance doorbell bridge: ask the destination endpoint to set its
    # modeled GSR pending bit for the P2A channel.
    machine.SystemBus.WriteDoubleWord(
        endpoint_base + _INTERNAL_REMOTE_GSR_SET,
        1 << channel)
    return True


def _emit_lmm_event_to_ap_ns(event_lm, flags):
    machine = _get_machine()
    if machine is None:
        return False

    subscription = machine.SystemBus.ReadDoubleWord(
        _AP_ENDPOINT_BASE + _INTERNAL_AP_NS_LMM_SUBSCRIPTION)
    if (subscription & flags) == 0:
        return False

    # LMM event payload: causing LM, event LM, event flags.
    return _write_remote_notification(
        _AP_ENDPOINT_BASE,
        3,
        SCMI_PROTOCOL_NXP_LMM,
        _LMM_EVENT_MESSAGE_ID,
        [LM_M7, event_lm, flags])


if request.IsInit:
    transport_channel_count = 4 if _is_ap_endpoint else 3
    channel = 0
    while channel < transport_channel_count:
        _write32(_transport_channel_base(channel) + SMT_CHANNEL_STATUS,
                 SMT_CHANNEL_FREE)
        channel += 1

    if _is_ap_endpoint:
        _write32(_INTERNAL_AP_NS_LMM_SUBSCRIPTION, 0)

elif request.IsWrite:
    # Guest software never uses this private offset; it only bridges a remote
    # P2A event between the M7 and AP modeled MU endpoints.
    if request.Offset == _INTERNAL_REMOTE_GSR_SET and request.Length == 4:
        _write32(MU_GSR, _read32(MU_GSR) | (_original_request_value & 0xF))

    elif request.Offset == _MU_GCR_OFFSET and request.Length == 4:
        if _is_ap_endpoint and (_original_request_value & (1 << 2)):
            # AP-NS request is local channel 2 (global channel 5).
            _process_scmi(2)

            request_base = _transport_channel_base(2)
            if (_pre_ap_ns_lmm_notify_flags is not None and
                    _read32(request_base + SMT_PAYLOAD) == SCMI_SUCCESS):
                _write32(_INTERNAL_AP_NS_LMM_SUBSCRIPTION,
                         _pre_ap_ns_lmm_notify_flags)

        # M7 A2P local channel 0 is handled by the base engine. A System Power
        # transition of M7 logical machine 1 can generate an LMM P2A event for
        # an AP-NS subscriber on local channel 3/global channel 6.
        if not _is_ap_endpoint and (_original_request_value & 0x1):
            request_base = _transport_channel_base(0)
            header = _read32(request_base + SMT_MESSAGE_HEADER)
            message_id = header & 0xFF
            protocol_id = (header >> 10) & 0xFF

            if protocol_id == SCMI_PROTOCOL_SYSTEM and message_id == 0x03:
                state = system_power_state.get(AGENT_M7)
                if state == SYS_STATE_SHUTDOWN:
                    _emit_lmm_event_to_ap_ns(LM_M7, _LMM_EVENT_SHUTDOWN)
                elif state == SYS_STATE_SUSPEND:
                    _emit_lmm_event_to_ap_ns(LM_M7, _LMM_EVENT_SUSPEND)
                elif state == SYS_STATE_POWER_UP:
                    _emit_lmm_event_to_ap_ns(LM_M7, _LMM_EVENT_WAKE)

        _write32(MU_GCR, 0)
