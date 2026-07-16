# i.MX952 NXP MISC SCMI extension layer.
#
# Layering:
#   core -> exact SMT/P2A transport -> BBM -> MISC
#
# The resource and permission map follows the pinned mx952evk config_scmi.h.
# Device controls use the exact MIMX952 masks. Board wake/button controls,
# PCA2131 raw access and TEST action are deterministic functional backends.
# Physical register side effects, I2C timing, PHY behavior and real board-event
# generation remain hardware-correlation gates.

_MISC_PROTOCOL = 0x84
_MISC_VERSION = 0x00010001
_MISC_CTRL_FLAG_BRD = 0x8000
_MISC_DEVICE_CONTROL_COUNT = 10
_MISC_BOARD_CONTROL_COUNT = 8
_MISC_REASON_COUNT = 32
_MISC_CONTROL_EVENT_MESSAGE_ID = 0
_MISC_MESSAGE_TYPE_NOTIFICATION = 3
_MISC_M7_NOTIFY_CHANNEL = 1
_MISC_APNS_NOTIFY_CHANNEL = 3
_MISC_NOTIFY_QUEUE_LIMIT = 8
_MISC_PCA2131_MAX_EXT = 24

_MISC_PERM_NONE = 0
_MISC_PERM_GET = 1
_MISC_PERM_NOTIFY = 2
_MISC_PERM_SET = 3
_MISC_PERM_PRIV = 4
_MISC_PERM_EXCLUSIVE = 5
_MISC_PERM_ALL = 255

# Unified device-control IDs 0..9.
_MISC_PDM_CLK_SEL = 0
_MISC_MQS1_SETTINGS = 1
_MISC_SAI3_MCLK = 2
_MISC_SAI4_MCLK = 3
_MISC_SAI5_MCLK = 4
_MISC_ADC_TEST = 5
_MISC_ASRC1_MCLK = 6
_MISC_ASRC2_MCLK = 7
_MISC_BYPASS_AUDMIX = 8
_MISC_COMBO_PHY = 9

# Unified board-control IDs 10..17; SCMI wire IDs use 0x8000|local_id.
_MISC_BRD_SD3_WAKE = 10
_MISC_BRD_M2E_WAKE = 11
_MISC_BRD_BT_WAKE = 12
_MISC_BRD_M2M_WAKE = 13
_MISC_BRD_BUTTON = 14
_MISC_BRD_TEST = 15
_MISC_BRD_PCA2131 = 16
_MISC_BRD_TEST_A = 17

_MISC_DEVICE_MASKS = {
    _MISC_PDM_CLK_SEL: 0x00000001,
    _MISC_MQS1_SETTINGS: 0x0000FF0E,
    _MISC_SAI3_MCLK: 0x000001FF,
    _MISC_SAI4_MCLK: 0x0003FE00,
    _MISC_SAI5_MCLK: 0x07FC0000,
    _MISC_ADC_TEST: 0x00000080,
    _MISC_ASRC1_MCLK: 0x0000003F,
    _MISC_ASRC2_MCLK: 0x00000FC0,
    _MISC_BYPASS_AUDMIX: 0x00000001,
    _MISC_COMBO_PHY: 0x00000007,
}

# Exact generated mx952evk ctrlPerms projection.
_MISC_CONTROL_PERMISSIONS = {
    AGENT_M7: {
        _MISC_BRD_BUTTON: _MISC_PERM_NOTIFY,
        _MISC_BRD_TEST: _MISC_PERM_ALL,
        _MISC_BRD_PCA2131: _MISC_PERM_ALL,
    },
    AGENT_AP_S: {},
    AGENT_AP_NS: {
        _MISC_PDM_CLK_SEL: _MISC_PERM_ALL,
        _MISC_MQS1_SETTINGS: _MISC_PERM_ALL,
        _MISC_SAI3_MCLK: _MISC_PERM_ALL,
        _MISC_SAI4_MCLK: _MISC_PERM_ALL,
        _MISC_SAI5_MCLK: _MISC_PERM_ALL,
        _MISC_ADC_TEST: _MISC_PERM_ALL,
        _MISC_ASRC1_MCLK: _MISC_PERM_ALL,
        _MISC_ASRC2_MCLK: _MISC_PERM_ALL,
        _MISC_BYPASS_AUDMIX: _MISC_PERM_ALL,
        _MISC_COMBO_PHY: _MISC_PERM_ALL,
        _MISC_BRD_SD3_WAKE: _MISC_PERM_NOTIFY,
        _MISC_BRD_M2E_WAKE: _MISC_PERM_NOTIFY,
        _MISC_BRD_BT_WAKE: _MISC_PERM_NOTIFY,
        _MISC_BRD_M2M_WAKE: _MISC_PERM_NOTIFY,
        _MISC_BRD_BUTTON: _MISC_PERM_NOTIFY,
    },
}

_MISC_REASON_NAMES = {
    0: "CM33_LOCKUP", 1: "CM33_SWREQ", 2: "CM7_LOCKUP", 3: "CM7_SWREQ",
    4: "FCCU", 5: "JTAG_SW", 6: "ELE", 7: "TEMPSENSE",
    8: "WDOG1", 9: "WDOG2", 10: "WDOG3", 11: "WDOG4", 12: "WDOG5",
    13: "JTAG", 14: "CM33_EXC", 15: "BBM", 16: "SW", 17: "SM_ERR",
    18: "FUSA_SRECO", 19: "PMIC", 31: "POR",
}

# Deterministic test/evidence input, not a physical register.
# bits[7:0] board local control 0..4; bit[8] input state.
_INTERNAL_MISC_CONTROL_TRIGGER = 0x1F4

_MISC_ORIGINAL_VALUE = request.Value if request.IsWrite else 0
_MISC_ORIGINAL_GCR = _MISC_ORIGINAL_VALUE
_MISC_IS_AP = size >= 0x1400
_MISC_REQUEST_CHANNEL = None
_MISC_PRE_HEADER = 0
_MISC_PRE_WORDS = [0] * 24

if request.IsWrite and request.Offset == 0x114:
    if _MISC_IS_AP and (_MISC_ORIGINAL_GCR & (1 << 2)):
        _MISC_REQUEST_CHANNEL = 2
    elif (not _MISC_IS_AP) and (_MISC_ORIGINAL_GCR & 0x1):
        _MISC_REQUEST_CHANNEL = 0

    if _MISC_REQUEST_CHANNEL is not None:
        _misc_base_addr = 0x1000 + _MISC_REQUEST_CHANNEL * 0x80
        _MISC_PRE_HEADER = _read32(_misc_base_addr + 0x18)
        _misc_index = 0
        while _misc_index < len(_MISC_PRE_WORDS):
            _MISC_PRE_WORDS[_misc_index] = _read32(
                _misc_base_addr + 0x1C + _misc_index * 4)
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


def _misc_endpoint_agent():
    return AGENT_AP_NS if _MISC_IS_AP else AGENT_M7


def _misc_notify_channel():
    return _MISC_APNS_NOTIFY_CHANNEL if _MISC_IS_AP else _MISC_M7_NOTIFY_CHANNEL


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


def _misc_has_resources(agent_id):
    return bool(_MISC_CONTROL_PERMISSIONS.get(agent_id, {}))


def _misc_protocols_for_agent(agent_id):
    protocols = list(_bbm_protocols_for_agent(agent_id))
    if _misc_has_resources(agent_id) and _MISC_PROTOCOL not in protocols:
        protocols.append(_MISC_PROTOCOL)
    return protocols


def _override_misc_base(channel, agent_id, message_id, words):
    protocols = _misc_protocols_for_agent(agent_id)
    if message_id == 0x01:
        _misc_words(channel, SCMI_SUCCESS, [(3 << 8) | len(protocols)])
    elif message_id == 0x06:
        skip = words[0]
        if skip >= len(protocols):
            _misc_words(channel, SCMI_INVALID_PARAMETERS, [0])
            return
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


def _misc_decode_control(wire_id):
    if (wire_id & _MISC_CTRL_FLAG_BRD) != 0:
        local_id = wire_id & (~_MISC_CTRL_FLAG_BRD & 0xFFFFFFFF)
        if local_id >= _MISC_BOARD_CONTROL_COUNT:
            return None, None, None
        return _MISC_DEVICE_CONTROL_COUNT + local_id, True, local_id
    if wire_id >= _MISC_DEVICE_CONTROL_COUNT:
        return None, None, None
    return wire_id, False, wire_id


def _misc_wire_control(unified_id):
    if unified_id < _MISC_DEVICE_CONTROL_COUNT:
        return unified_id
    return _MISC_CTRL_FLAG_BRD | (unified_id - _MISC_DEVICE_CONTROL_COUNT)


def _misc_permission(agent_id, unified_id):
    return _MISC_CONTROL_PERMISSIONS.get(agent_id, {}).get(
        unified_id, _MISC_PERM_NONE)


def _misc_notify_base():
    return SCMI_SRAM + _misc_notify_channel() * SCMI_CHANNEL_SIZE


def _misc_notification_header():
    global misc_notify_token
    header = (((_MISC_PROTOCOL & 0xFF) << 10) |
              ((_MISC_MESSAGE_TYPE_NOTIFICATION & 0x3) << 8) |
              (_MISC_CONTROL_EVENT_MESSAGE_ID & 0xFF) |
              ((misc_notify_token & 0x3FF) << 18))
    misc_notify_token = (misc_notify_token + 1) & 0x3FF
    return header


def _misc_notify_channel_free():
    return (_read32(_misc_notify_base() + SMT_CHANNEL_STATUS) &
            SMT_CHANNEL_FREE) != 0


def _misc_try_dispatch_notification():
    if not misc_notify_queue or not _misc_notify_channel_free():
        return False
    ctrl_id, flags = misc_notify_queue.pop(0)
    base = _misc_notify_base()
    channel = _misc_notify_channel()
    _write32(base + SMT_CHANNEL_STATUS, 0)
    _write32(base + SMT_MESSAGE_HEADER, _misc_notification_header())
    _write32(base + SMT_PAYLOAD, ctrl_id)
    _write32(base + SMT_PAYLOAD + 4, flags)
    _write32(base + SMT_LENGTH, 12)
    _write32(MU_GSR, _read32(MU_GSR) | (1 << channel))
    _update_m7_scmi_irq()
    return True


def _misc_queue_notification(ctrl_id, flags):
    global misc_notify_overflow
    if len(misc_notify_queue) >= _MISC_NOTIFY_QUEUE_LIMIT:
        misc_notify_overflow += 1
        return False
    misc_notify_queue.append((ctrl_id, flags))
    _misc_try_dispatch_notification()
    return True


def _misc_emit_board_event(local_id, state):
    if local_id < 0 or local_id > 4:
        return False
    agent_id = _misc_endpoint_agent()
    unified_id = _MISC_DEVICE_CONTROL_COUNT + local_id
    misc_board_inputs[local_id] = 1 if state else 0
    flags = (1 if not state else 2)
    subscribed = misc_control_notify.get((agent_id, unified_id), 0)
    if (subscribed & flags) == 0:
        return False
    return _misc_queue_notification(_misc_wire_control(unified_id), flags)


def _misc_process_control_set(channel, agent_id, words):
    unified_id, is_board, unused_local = _misc_decode_control(words[0])
    if unified_id is None:
        _misc_status(channel, SCMI_NOT_FOUND)
        return
    if _misc_permission(agent_id, unified_id) < _MISC_PERM_EXCLUSIVE:
        _misc_status(channel, SCMI_DENIED)
        return
    num_val = words[1]
    if num_val > 8:
        _misc_status(channel, SCMI_INVALID_PARAMETERS)
        return
    if is_board:
        _misc_status(channel, SCMI_NOT_SUPPORTED)
        return
    if num_val != 1:
        _misc_status(channel, SCMI_INVALID_PARAMETERS)
        return
    mask = _MISC_DEVICE_MASKS[unified_id]
    misc_device_controls[unified_id] = words[2] & mask
    _misc_status(channel, SCMI_SUCCESS)


def _misc_process_control_get(channel, agent_id, words):
    unified_id, is_board, local_id = _misc_decode_control(words[0])
    if unified_id is None:
        _misc_status(channel, SCMI_NOT_FOUND)
        return
    if _misc_permission(agent_id, unified_id) < _MISC_PERM_GET:
        _misc_status(channel, SCMI_DENIED)
        return
    if not is_board:
        _misc_words(channel, SCMI_SUCCESS,
                    [1, misc_device_controls.get(unified_id, 0)])
    elif local_id <= 4:
        _misc_words(channel, SCMI_SUCCESS,
                    [1, misc_board_inputs.get(local_id, 0)])
    else:
        _misc_status(channel, SCMI_NOT_SUPPORTED)


def _misc_process_control_action(channel, agent_id, words):
    global misc_test_action_count
    unified_id, is_board, local_id = _misc_decode_control(words[0])
    if unified_id is None:
        _misc_status(channel, SCMI_NOT_FOUND)
        return
    if _misc_permission(agent_id, unified_id) < _MISC_PERM_EXCLUSIVE:
        _misc_status(channel, SCMI_DENIED)
        return
    num_arg = words[2]
    if num_arg > 8:
        _misc_status(channel, SCMI_INVALID_PARAMETERS)
        return
    if not is_board:
        # The pinned device implementation accepts actions and returns no words.
        _misc_words(channel, SCMI_SUCCESS, [0])
    elif local_id == 5:
        # Source calls SM_Error(). The model records the request but does not
        # fabricate a physical safety reaction.
        misc_test_action_count += 1
        _misc_words(channel, SCMI_SUCCESS, [0])
    elif local_id == 7:
        _misc_words(channel, SCMI_SUCCESS, [num_arg] + list(words[3:3 + num_arg]))
    else:
        _misc_status(channel, SCMI_NOT_SUPPORTED)


def _misc_process_control_notify(channel, agent_id, words):
    unified_id, is_board, local_id = _misc_decode_control(words[0])
    if unified_id is None:
        _misc_status(channel, SCMI_NOT_FOUND)
        return
    if _misc_permission(agent_id, unified_id) < _MISC_PERM_NOTIFY:
        _misc_status(channel, SCMI_DENIED)
        return
    if not is_board:
        _misc_status(channel, SCMI_NOT_SUPPORTED)
        return
    if local_id > 4:
        _misc_status(channel, SCMI_NOT_FOUND)
        return
    misc_control_notify[(agent_id, unified_id)] = words[1]
    _misc_status(channel, SCMI_SUCCESS)


def _misc_process_ext_set(channel, agent_id, words):
    unified_id, is_board, local_id = _misc_decode_control(words[0])
    if unified_id is None:
        _misc_status(channel, SCMI_NOT_FOUND)
        return
    if _misc_permission(agent_id, unified_id) < _MISC_PERM_EXCLUSIVE:
        _misc_status(channel, SCMI_DENIED)
        return
    address = words[1] & 0xFF
    requested_len = words[2]
    num_val = words[3]
    if requested_len != num_val or num_val > _MISC_PCA2131_MAX_EXT:
        _misc_status(channel, SCMI_INVALID_PARAMETERS)
        return
    if not is_board or local_id != 6:
        _misc_status(channel, SCMI_NOT_SUPPORTED)
        return
    index = 0
    while index < num_val:
        misc_pca2131_registers[(address + index) & 0xFF] = words[4 + index] & 0xFF
        index += 1
    _misc_status(channel, SCMI_SUCCESS)


def _misc_process_ext_get(channel, agent_id, words):
    unified_id, is_board, local_id = _misc_decode_control(words[0])
    if unified_id is None:
        _misc_status(channel, SCMI_NOT_FOUND)
        return
    if _misc_permission(agent_id, unified_id) < _MISC_PERM_GET:
        _misc_status(channel, SCMI_DENIED)
        return
    address = words[1] & 0xFF
    requested_len = words[2]
    if requested_len > _MISC_PCA2131_MAX_EXT:
        _misc_status(channel, SCMI_INVALID_PARAMETERS)
        return
    if not is_board or local_id != 6:
        _misc_status(channel, SCMI_NOT_SUPPORTED)
        return
    values = []
    index = 0
    while index < requested_len:
        values.append(misc_pca2131_registers.get((address + index) & 0xFF, 0))
        index += 1
    _misc_words(channel, SCMI_SUCCESS, [requested_len] + values)


def _process_misc(channel, agent_id, message_id, words):
    if not _misc_has_resources(agent_id):
        _misc_status(channel, SCMI_DENIED)
        return

    if message_id == 0x00:
        _misc_words(channel, SCMI_SUCCESS, [_MISC_VERSION])
    elif message_id == 0x01:
        attributes = ((_MISC_BOARD_CONTROL_COUNT & 0xFF) << 24) | \
                     ((_MISC_REASON_COUNT & 0xFF) << 16) | \
                     (_MISC_DEVICE_CONTROL_COUNT & 0xFFFF)
        _misc_words(channel, SCMI_SUCCESS, [attributes])
    elif message_id == 0x02:
        if words[0] in _misc_supported_messages():
            _misc_words(channel, SCMI_SUCCESS, [0])
        else:
            _misc_status(channel, SCMI_NOT_FOUND)
    elif message_id == 0x03:
        _misc_process_control_set(channel, agent_id, words)
    elif message_id == 0x04:
        _misc_process_control_get(channel, agent_id, words)
    elif message_id == 0x05:
        _misc_process_control_action(channel, agent_id, words)
    elif message_id == 0x06:
        base = _misc_base(channel)
        _write32(base + SMT_PAYLOAD, SCMI_SUCCESS)
        _write32(base + SMT_PAYLOAD + 4, 0)
        _write32(base + SMT_PAYLOAD + 8, 0x44F76DCB)
        _write_ascii(base + SMT_PAYLOAD + 12, "pinned-source", 16)
        _write_ascii(base + SMT_PAYLOAD + 28, "model", 16)
        _misc_finish(channel, 44)
    elif message_id == 0x07:
        _misc_status(channel, SCMI_NOT_SUPPORTED)
    elif message_id == 0x08:
        _misc_process_control_notify(channel, agent_id, words)
    elif message_id == 0x09:
        reason_id = words[0]
        if reason_id >= _MISC_REASON_COUNT:
            _misc_status(channel, SCMI_NOT_FOUND)
        else:
            _misc_text_response(channel, SCMI_SUCCESS, [0],
                                _MISC_REASON_NAMES.get(reason_id,
                                                       "REASON-%d" % reason_id),
                                8, 16)
    elif message_id == 0x0A:
        _misc_words(channel, SCMI_SUCCESS, [0x8000001F, 0x8000001F])
    elif message_id == 0x0B:
        _misc_text_response(channel, SCMI_SUCCESS, [0, 0, 0],
                            "i.MX952 B0", 16, 16)
    elif message_id == 0x0C:
        _misc_text_response(channel, SCMI_SUCCESS, [0], "mx952evk", 8, 16)
    elif message_id == 0x0D:
        _misc_words(channel, SCMI_SUCCESS, [0])
    elif message_id == 0x0E:
        _misc_text_response(channel, SCMI_SUCCESS, [0], "i.MX952 EVK", 8, 16)
    elif message_id == 0x10:
        if words[0] <= _MISC_VERSION:
            _misc_status(channel, SCMI_SUCCESS)
        else:
            _misc_status(channel, SCMI_NOT_SUPPORTED)
    elif message_id == 0x20:
        _misc_process_ext_set(channel, agent_id, words)
    elif message_id == 0x21:
        _misc_process_ext_get(channel, agent_id, words)
    elif message_id == 0x22:
        region_id = words[0]
        if region_id != 0:
            _misc_status(channel, SCMI_NOT_FOUND)
        else:
            # Functional one-region 2 GiB model: LPDDR5, 64-bit width, no ECC.
            # MTS remains zero until physical EVK evidence is captured.
            attributes = (1 << 16) | (2 << 8)
            _misc_words(channel, SCMI_SUCCESS,
                        [attributes, 0, 0x80000000, 0, 0xFFFFFFFF, 0])
    else:
        _misc_status(channel, SCMI_NOT_SUPPORTED)


if request.IsInit:
    misc_device_controls = {}
    for _misc_ctrl in range(_MISC_DEVICE_CONTROL_COUNT):
        misc_device_controls[_misc_ctrl] = 0
    misc_board_inputs = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    misc_control_notify = {}
    misc_pca2131_registers = {}
    misc_test_action_count = 0
    misc_notify_queue = []
    misc_notify_token = 0
    misc_notify_overflow = 0
    _write32(_INTERNAL_MISC_CONTROL_TRIGGER, 0)

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

elif (request.IsWrite and request.Offset == _INTERNAL_MISC_CONTROL_TRIGGER and
      request.Length == 4):
    local_id = _MISC_ORIGINAL_VALUE & 0xFF
    state = ((_MISC_ORIGINAL_VALUE >> 8) & 0x1) != 0
    _misc_emit_board_event(local_id, state)
    _write32(_INTERNAL_MISC_CONTROL_TRIGGER, 0)

elif (request.IsWrite and
      request.Offset == (_misc_notify_base() + SMT_CHANNEL_STATUS) and
      request.Length == 4 and (_MISC_ORIGINAL_VALUE & SMT_CHANNEL_FREE)):
    _misc_try_dispatch_notification()
