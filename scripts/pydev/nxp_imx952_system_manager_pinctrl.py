# i.MX952 source-derived SCMI Pinctrl permission/state layer.
#
# Layering:
#   core -> SMT/P2A -> BBM -> MISC -> Clock policy -> Pinctrl policy
#
# The model preserves the global 140-pin inventory while enforcing the exact
# generated mx952evk pinPerms/daisyPerms projection. Functional configuration
# state is modeled; physical pad electrical behavior and signal propagation are
# deliberately outside this layer's equivalence claim.

_PINCTRL_PROTOCOL = 0x19
_PINCTRL_VERSION = 0x00010000
_PIN_COUNT = 140
_DAISY_COUNT = 135

_PINCTRL_SEL_PIN = 0
_PINCTRL_SEL_GROUP = 1
_PINCTRL_TYPE_MUX = 192
_PINCTRL_TYPE_CONFIG = 193
_PINCTRL_TYPE_DAISY_ID = 194
_PINCTRL_TYPE_DAISY_CFG = 195
_PINCTRL_TYPE_EXT = 196
_PINCTRL_FUNC_NONE = 0xFFFFFFFF

_PINCTRL_CFG_TYPE = 0
_PINCTRL_CFG_ALL = 1
_PINCTRL_CFG_NONE = 2

_M7_PIN_IDS = set([18, 19])
_M7_DAISY_IDS = set([0, 69, 70, 71, 72, 73, 74])
_APNS_PIN_EXCLUDE = set([18, 19, 123, 124, 129, 130, 133, 138, 139])
_APNS_DAISY_EXCLUDE = set([0, 69, 70, 71, 72, 73, 74, 102, 103, 104])

_PINCTRL_ORIGINAL_GCR = request.Value if request.IsWrite else 0
_PINCTRL_IS_AP = size >= 0x1400
_PINCTRL_REQUEST_CHANNEL = None
_PINCTRL_PRE_HEADER = 0
_PINCTRL_PRE_WORDS = [0] * 24

if request.IsWrite and request.Offset == 0x114:
    if _PINCTRL_IS_AP and (_PINCTRL_ORIGINAL_GCR & (1 << 2)):
        _PINCTRL_REQUEST_CHANNEL = 2
    elif _PINCTRL_ORIGINAL_GCR & 0x1:
        _PINCTRL_REQUEST_CHANNEL = 0

    if _PINCTRL_REQUEST_CHANNEL is not None:
        _pinctrl_base = 0x1000 + _PINCTRL_REQUEST_CHANNEL * 0x80
        _PINCTRL_PRE_HEADER = _read32(_pinctrl_base + 0x18)
        _pinctrl_index = 0
        while _pinctrl_index < len(_PINCTRL_PRE_WORDS):
            _PINCTRL_PRE_WORDS[_pinctrl_index] = _read32(
                _pinctrl_base + 0x1C + _pinctrl_index * 4)
            _pinctrl_index += 1

        # Mask Pinctrl from all lower layers. This layer restores the captured
        # header/payload and emits the authoritative response after initialization.
        if ((_PINCTRL_PRE_HEADER >> 10) & 0xFF) == _PINCTRL_PROTOCOL:
            _write32(
                _pinctrl_base + 0x18,
                (0xFF << 10) | (_PINCTRL_PRE_HEADER & 0x3FF),
            )

execfile("scripts/pydev/nxp_imx952_system_manager_clock.py")


def _pinctrl_agent_for_request():
    if _PINCTRL_REQUEST_CHANNEL is None:
        return None
    if not _PINCTRL_IS_AP:
        return 0
    if _PINCTRL_REQUEST_CHANNEL == 0:
        return 1
    return 2


def _pinctrl_pin_allowed(agent_id, pin_id):
    if pin_id < 0 or pin_id >= _PIN_COUNT:
        return False
    if agent_id == 0:
        return pin_id in _M7_PIN_IDS
    if agent_id == 1:
        return False
    if agent_id == 2:
        return pin_id not in _APNS_PIN_EXCLUDE
    return False


def _pinctrl_daisy_allowed(agent_id, daisy_id):
    if daisy_id < 0 or daisy_id >= _DAISY_COUNT:
        return False
    if agent_id == 0:
        return daisy_id in _M7_DAISY_IDS
    if agent_id == 1:
        return False
    if agent_id == 2:
        return daisy_id not in _APNS_DAISY_EXCLUDE
    return False


def _pinctrl_restore_request(channel):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    _write32(base + SMT_MESSAGE_HEADER, _PINCTRL_PRE_HEADER)
    index = 0
    while index < len(_PINCTRL_PRE_WORDS):
        _write32(base + SMT_PAYLOAD + index * 4, _PINCTRL_PRE_WORDS[index])
        index += 1


def _pinctrl_finish(channel, payload_length):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    _write32(base + SMT_LENGTH, payload_length + 4)
    _write32(base + SMT_CHANNEL_STATUS, SMT_CHANNEL_FREE)


def _pinctrl_words(channel, status, words):
    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    _write32(base + SMT_PAYLOAD, status)
    index = 0
    while index < len(words):
        _write32(base + SMT_PAYLOAD + 4 + index * 4, words[index])
        index += 1
    _pinctrl_finish(channel, 4 + 4 * len(words))


def _pinctrl_pin_name(pin_id):
    # Exact high-value names from the generated permission split; remaining
    # global pins keep a stable ID-based functional name until the full symbolic
    # name table is promoted into the executable model.
    if pin_id == 18:
        return "GPIO_IO14"
    if pin_id == 19:
        return "GPIO_IO15"
    return "PIN-%03d" % pin_id


def _pinctrl_attributes(channel, words):
    pin_id = words[0] & 0xFFFF
    selector = words[1] & 0x3
    if selector != _PINCTRL_SEL_PIN:
        _pinctrl_words(channel, SCMI_NOT_FOUND, [])
        return
    if pin_id >= _PIN_COUNT:
        _pinctrl_words(channel, SCMI_NOT_FOUND, [])
        return

    base = SCMI_SRAM + channel * SCMI_CHANNEL_SIZE
    _write32(base + SMT_PAYLOAD, SCMI_SUCCESS)
    _write32(base + SMT_PAYLOAD + 4, 1)  # one pin
    _write_ascii(base + SMT_PAYLOAD + 8, _pinctrl_pin_name(pin_id), 16)
    _pinctrl_finish(channel, 24)


def _pinctrl_settings_get(channel, words):
    pin_id = words[0]
    attributes = words[1]
    cfg_flag = (attributes >> 18) & 0x3
    selector = (attributes >> 16) & 0x3
    skip = (attributes >> 8) & 0xFF
    config_type = attributes & 0xFF

    if selector > _PINCTRL_SEL_GROUP:
        _pinctrl_words(channel, SCMI_INVALID_PARAMETERS, [])
        return
    if selector != _PINCTRL_SEL_PIN:
        _pinctrl_words(channel, SCMI_NOT_SUPPORTED, [])
        return
    if pin_id >= _PIN_COUNT:
        _pinctrl_words(channel, SCMI_NOT_FOUND, [])
        return

    if cfg_flag == _PINCTRL_CFG_TYPE:
        config_types = [config_type]
        skip = 0
    elif cfg_flag == _PINCTRL_CFG_ALL:
        config_types = [_PINCTRL_TYPE_MUX, _PINCTRL_TYPE_CONFIG, _PINCTRL_TYPE_EXT]
    elif cfg_flag == _PINCTRL_CFG_NONE:
        config_types = []
        skip = 0
    else:
        _pinctrl_words(channel, SCMI_INVALID_PARAMETERS, [])
        return

    supported = set([_PINCTRL_TYPE_MUX, _PINCTRL_TYPE_CONFIG, _PINCTRL_TYPE_EXT])
    for config in config_types:
        if config not in supported:
            _pinctrl_words(channel, SCMI_NOT_SUPPORTED, [])
            return

    selected = config_types[skip:skip + 12]
    remaining = max(0, len(config_types) - skip - len(selected))
    function_selected = pinctrl_functions.get(pin_id, _PINCTRL_FUNC_NONE)
    response_words = [function_selected, (remaining << 24) | len(selected)]
    for config in selected:
        response_words.append(config)
        response_words.append(pinctrl_pin_values.get((pin_id, config), 0))
    _pinctrl_words(channel, SCMI_SUCCESS, response_words)


def _pinctrl_settings_configure(channel, agent_id, words):
    pin_id = words[0]
    function_id = words[1]
    attributes = words[2]
    selector = attributes & 0x3
    num_configs = (attributes >> 2) & 0xFF
    function_valid = ((attributes >> 10) & 1) != 0

    if num_configs > 8:
        _pinctrl_words(channel, SCMI_INVALID_PARAMETERS, [])
        return
    if selector > _PINCTRL_SEL_GROUP:
        _pinctrl_words(channel, SCMI_INVALID_PARAMETERS, [])
        return
    if selector != _PINCTRL_SEL_PIN:
        _pinctrl_words(channel, SCMI_NOT_SUPPORTED, [])
        return
    if pin_id >= _PIN_COUNT:
        _pinctrl_words(channel, SCMI_NOT_FOUND, [])
        return

    if function_valid and not _pinctrl_pin_allowed(agent_id, pin_id):
        _pinctrl_words(channel, SCMI_DENIED, [])
        return

    daisy_id = 0
    index = 0
    pending_pin_updates = []
    pending_daisy_updates = []
    while index < num_configs:
        config_type = words[3 + index * 2]
        value = words[4 + index * 2]

        if config_type == _PINCTRL_TYPE_DAISY_ID:
            daisy_id = value
        elif config_type == _PINCTRL_TYPE_DAISY_CFG:
            if daisy_id >= _DAISY_COUNT:
                _pinctrl_words(channel, SCMI_NOT_FOUND, [])
                return
            if not _pinctrl_daisy_allowed(agent_id, daisy_id):
                _pinctrl_words(channel, SCMI_DENIED, [])
                return
            pending_daisy_updates.append((daisy_id, value))
        elif config_type in set([_PINCTRL_TYPE_MUX, _PINCTRL_TYPE_CONFIG, _PINCTRL_TYPE_EXT]):
            if not _pinctrl_pin_allowed(agent_id, pin_id):
                _pinctrl_words(channel, SCMI_DENIED, [])
                return
            pending_pin_updates.append((pin_id, config_type, value))
        else:
            _pinctrl_words(channel, SCMI_NOT_SUPPORTED, [])
            return
        index += 1

    for update_pin, config_type, value in pending_pin_updates:
        pinctrl_pin_values[(update_pin, config_type)] = value
    for update_daisy, value in pending_daisy_updates:
        pinctrl_daisy_values[update_daisy] = value
    if function_valid:
        pinctrl_functions[pin_id] = function_id

    _pinctrl_words(channel, SCMI_SUCCESS, [])


def _pinctrl_request_pin(channel, agent_id, words):
    pin_id = words[0]
    selector = words[1] & 0x3
    if selector != _PINCTRL_SEL_PIN:
        _pinctrl_words(channel, SCMI_INVALID_PARAMETERS, [])
    elif pin_id >= _PIN_COUNT:
        _pinctrl_words(channel, SCMI_NOT_FOUND, [])
    elif not _pinctrl_pin_allowed(agent_id, pin_id):
        _pinctrl_words(channel, SCMI_DENIED, [])
    else:
        pinctrl_requested.add((agent_id, pin_id))
        _pinctrl_words(channel, SCMI_SUCCESS, [])


def _pinctrl_release_pin(channel, agent_id, words):
    pin_id = words[0]
    selector = words[1] & 0x3
    if selector != _PINCTRL_SEL_PIN:
        _pinctrl_words(channel, SCMI_INVALID_PARAMETERS, [])
    elif pin_id >= _PIN_COUNT:
        _pinctrl_words(channel, SCMI_NOT_FOUND, [])
    else:
        pinctrl_requested.discard((agent_id, pin_id))
        _pinctrl_words(channel, SCMI_SUCCESS, [])


def _process_pinctrl_filtered(channel, agent_id, message_id, words):
    if message_id == 0x00:
        _pinctrl_words(channel, SCMI_SUCCESS, [_PINCTRL_VERSION])
    elif message_id == 0x01:
        # attributesLow: groups[31:16]=0, pins[15:0]=140; attributesHigh functions=0
        _pinctrl_words(channel, SCMI_SUCCESS, [_PIN_COUNT, 0])
    elif message_id == 0x02:
        requested = words[0]
        supported = set([0x00, 0x01, 0x02, 0x03, 0x05, 0x06, 0x07, 0x08, 0x10])
        if requested in supported:
            _pinctrl_words(channel, SCMI_SUCCESS, [0])
        else:
            _pinctrl_words(channel, SCMI_NOT_FOUND, [])
    elif message_id == 0x03:
        _pinctrl_attributes(channel, words)
    elif message_id == 0x05:
        _pinctrl_settings_get(channel, words)
    elif message_id == 0x06:
        _pinctrl_settings_configure(channel, agent_id, words)
    elif message_id == 0x07:
        _pinctrl_request_pin(channel, agent_id, words)
    elif message_id == 0x08:
        _pinctrl_release_pin(channel, agent_id, words)
    elif message_id == 0x10:
        if words[0] <= _PINCTRL_VERSION:
            _pinctrl_words(channel, SCMI_SUCCESS, [])
        else:
            _pinctrl_words(channel, SCMI_NOT_SUPPORTED, [])
    else:
        _pinctrl_words(channel, SCMI_NOT_SUPPORTED, [])


if request.IsInit:
    pinctrl_pin_values = {}
    pinctrl_daisy_values = {}
    pinctrl_functions = {}
    pinctrl_requested = set()

elif (request.IsWrite and request.Offset == 0x114 and
      _PINCTRL_REQUEST_CHANNEL is not None and
      ((_PINCTRL_PRE_HEADER >> 10) & 0xFF) == _PINCTRL_PROTOCOL):
    _pinctrl_restore_request(_PINCTRL_REQUEST_CHANNEL)
    _process_pinctrl_filtered(
        _PINCTRL_REQUEST_CHANNEL,
        _pinctrl_agent_for_request(),
        _PINCTRL_PRE_HEADER & 0xFF,
        _PINCTRL_PRE_WORDS,
    )
