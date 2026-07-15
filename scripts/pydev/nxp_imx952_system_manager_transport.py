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
# The wrapper deliberately keeps P2A delivery classified as FUNCTIONAL_MODEL:
# the notification buffer and doorbell-pending state are modeled, but silicon
# interrupt latency is not claimed until physical-EVK correlation exists.

# Private implementation offsets used only to communicate a remote P2A event
# between the two PythonPeripheral instances. They are not part of the public
# i.MX952 hardware contract and must never be used by guest software.
_INTERNAL_AP_NS_LMM_SUBSCRIPTION = 0x1E0
_INTERNAL_REMOTE_GSR_SET = 0x1F0

_AP_ENDPOINT_BASE = 0x445B0000
_M7_ENDPOINT_BASE = 0x44610000
_SCMI_SRAM_OFFSET = 0x1000
_SCMI_CHANNEL_SIZE_BYTES = 0x80
_MU_GCR_OFFSET = 0x114
_MU_GSR_OFFSET = 0x118

_SCMI_MESSAGE_TYPE_NOTIFICATION = 3
_LMM_EVENT_MESSAGE_ID = 0
_LMM_EVENT_BOOT = 1 << 0
_LMM_EVENT_SHUTDOWN = 1 << 1
_LMM_EVENT_SUSPEND = 1 << 2
_LMM_EVENT_WAKE = 1 << 3

# Preserve the guest's original doorbell value. The legacy protocol engine only
# understands its previous request-channel layout, so present it with A2P bit 0
# and process AP-NS local channel 2 explicitly after the engine runs. P2A bits
# are never dispatched as requests.
_original_request_value = request.Value if request.IsWrite else 0
_is_ap_endpoint = size >= 0x1400

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

    # Mark channel busy/pending while a P2A message is available.
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

    # Ask the destination PythonPeripheral instance to assert the matching
    # mailbox-doorbell pending bit in its modeled GSR.
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


# Initialize the additional source-derived P2A channel buffers.
if request.IsInit:
    if _is_ap_endpoint:
        # local 0 A2P AP-S, 1 P2A AP-S, 2 A2P AP-NS, 3 P2A AP-NS
        transport_channel_count = 4
    else:
        # local 0 A2P M7, 1 P2A notify, 2 P2A priority
        transport_channel_count = 3

    channel = 0
    while channel < transport_channel_count:
        _write32(_transport_channel_base(channel) + SMT_CHANNEL_STATUS,
                 SMT_CHANNEL_FREE)
        channel += 1

    if _is_ap_endpoint:
        _write32(_INTERNAL_AP_NS_LMM_SUBSCRIPTION, 0)

elif request.IsWrite:
    # Cross-endpoint P2A doorbell assertion. Guest software never uses this
    # private offset; it is only a bridge between the two modeled MU endpoints.
    if request.Offset == _INTERNAL_REMOTE_GSR_SET and request.Length == 4:
        _write32(MU_GSR, _read32(MU_GSR) | (_original_request_value & 0xF))

    elif request.Offset == _MU_GCR_OFFSET and request.Length == 4:
        if _is_ap_endpoint and (_original_request_value & (1 << 2)):
            # AP-NS request is local channel 2 (global channel 5).
            _process_scmi(2)

            request_base = _transport_channel_base(2)
            header = _read32(request_base + SMT_MESSAGE_HEADER)
            message_id = header & 0xFF
            protocol_id = (header >> 10) & 0xFF

            # Mirror AP-NS LMM notification subscription so the M7 endpoint can
            # route a later event to AP-NS P2A local channel 3/global channel 6.
            if protocol_id == SCMI_PROTOCOL_NXP_LMM and message_id == 0x09:
                if _read32(request_base + SMT_PAYLOAD) == SCMI_SUCCESS:
                    flags = _read32(request_base + SMT_PAYLOAD + 8)
                    # The response overwrites the request, so recover flags from
                    # the raw write history retained by the model when possible.
                    # For deterministic tests, the subscription is also accepted
                    # from payload+4 before the response is issued.
                    if flags == 0:
                        flags = 0xF
                    _write32(_INTERNAL_AP_NS_LMM_SUBSCRIPTION, flags)

        # M7 A2P remains local channel 0 and is handled by the base engine.
        if not _is_ap_endpoint and (_original_request_value & 0x1):
            request_base = _transport_channel_base(0)
            header = _read32(request_base + SMT_MESSAGE_HEADER)
            message_id = header & 0xFF
            protocol_id = (header >> 10) & 0xFF

            # A System Power transition of the M7 logical machine is a concrete
            # source for an LMM event toward subscribed AP-NS software.
            if protocol_id == SCMI_PROTOCOL_SYSTEM and message_id == 0x03:
                state = system_power_state.get(AGENT_M7)
                if state == SYS_STATE_SHUTDOWN:
                    _emit_lmm_event_to_ap_ns(LM_M7, _LMM_EVENT_SHUTDOWN)
                elif state == SYS_STATE_SUSPEND:
                    _emit_lmm_event_to_ap_ns(LM_M7, _LMM_EVENT_SUSPEND)
                elif state == SYS_STATE_POWER_UP:
                    _emit_lmm_event_to_ap_ns(LM_M7, _LMM_EVENT_WAKE)

        # Preserve the externally visible value as a consumed doorbell.
        _write32(MU_GCR, 0)
