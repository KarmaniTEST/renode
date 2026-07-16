# Source-bounded functional NXP i.MX952 EdgeLock Enclave (ELE) MU service.
#
# The model implements deterministic, non-secret early-boot services used by
# NXP U-Boot and fails closed for authentication, lifecycle, fuse programming,
# key, blob and attestation operations. Test RNG is disabled by default and is
# explicitly non-cryptographic. No command in this model proves AHAB/ELE trust.

from Antmicro.Renode.Core import EmulationManager

MU_PAR = 0x004
MU_TSR = 0x124
MU_RSR = 0x12C
MU_TR0 = 0x200
MU_RR0 = 0x280
MU_REGISTER_STRIDE = 4
MU_TR_COUNT = 4
MU_RR_COUNT = 4

ELE_VERSION = 0x06
ELE_VERSION_FW = 0x07
ELE_CMD_TAG = 0x17
ELE_RESP_TAG = 0xE1

ELE_PING_REQ = 0x01
ELE_FW_AUTH_REQ = 0x02
ELE_VOLT_CHANGE_START_REQ = 0x12
ELE_VOLT_CHANGE_FINISH_REQ = 0x13
ELE_OEM_CNTN_AUTH_REQ = 0x87
ELE_VERIFY_IMAGE_REQ = 0x88
ELE_RELEASE_CONTAINER_REQ = 0x89
ELE_WRITE_SECURE_FUSE_REQ = 0x91
ELE_FWD_LIFECYCLE_UP_REQ = 0x95
ELE_READ_FUSE_REQ = 0x97
ELE_GET_FW_VERSION_REQ = 0x9D
ELE_RET_LIFECYCLE_UP_REQ = 0xA0
ELE_GET_EVENTS_REQ = 0xA2
ELE_START_RNG_REQ = 0xA3
ELE_GET_TRNG_STATE_REQ = 0xA4
ELE_COMMIT_REQ = 0xA8
ELE_DERIVE_KEY_REQ = 0xA9
ELE_GENERATE_DEK_BLOB_REQ = 0xAF
ELE_BLOB_REQ = 0xBF
ELE_GET_FW_STATUS_REQ = 0xC5
ELE_GET_RNG_REQ = 0xCD
ELE_WRITE_FUSE_REQ = 0xD6
ELE_GET_INFO_REQ = 0xDA
ELE_ATTEST_REQ = 0xDB
ELE_WRITE_SHADOW_REQ = 0xF2
ELE_READ_SHADOW_REQ = 0xF3

ELE_SUCCESS_IND = 0xD6
ELE_FAILURE_IND = 0x29
ELE_PERMISSION_DENIED_FAILURE_IND = 0xF3
ELE_INVALID_MESSAGE_FAILURE_IND = 0xF4
ELE_BAD_VALUE_FAILURE_IND = 0xF5
ELE_BAD_FUSE_ID_FAILURE_IND = 0xF6
ELE_WRONG_ADDRESS_FAILURE_IND = 0xB4
ELE_DISABLED_FEATURE_FAILURE_IND = 0xB6
ELE_RNG_NOT_STARTED_FAILURE_IND = 0xB8
ELE_INVALID_OPERATION_FAILURE_IND = 0xC0

ELE_MAX_ADDR = 0xE0000000
ELE_MAX_TEST_RNG_BYTES = 4096
ELE_TEST_CONTROL = 0x3F0
ELE_TEST_EVENT = 0x3F4
ELE_TEST_VOLTAGE_STATE = 0x3F8
ELE_TEST_RNG_COUNT = 0x3FC
ELE_TEST_MAGIC = 0x54455354  # ASCII TEST; instrumentation only.

# The i.MX9 SCMI SoC code derives silicon revision from the top byte.
IMX952_SOC_INFO = 0xA0000000
IMX952_LIFECYCLE = 0x00000020
IMX952_UID = [0x95200001, 0x52454E4F, 0x4445494D, 0x58393532]
ELE_GET_INFO_WORDS = 64

# Firmware identity is intentionally unknown rather than fabricated.
ELE_FW_VERSION_VALUE = 0
ELE_FW_SHA1_VALUE = 0

# Deterministic OTP contents. Only explicitly listed IDs are readable.
ELE_FUSES = {
    0x00: 0x00000000,
    0x01: 0x00000000,
}

# Commands that can never return success without a real secure backend.
ELE_SECURE_DENY_COMMANDS = set([
    ELE_FW_AUTH_REQ,
    ELE_OEM_CNTN_AUTH_REQ,
    ELE_VERIFY_IMAGE_REQ,
    ELE_RELEASE_CONTAINER_REQ,
    ELE_WRITE_SECURE_FUSE_REQ,
    ELE_FWD_LIFECYCLE_UP_REQ,
    ELE_RET_LIFECYCLE_UP_REQ,
    ELE_COMMIT_REQ,
    ELE_DERIVE_KEY_REQ,
    ELE_GENERATE_DEK_BLOB_REQ,
    ELE_BLOB_REQ,
    ELE_WRITE_FUSE_REQ,
    ELE_ATTEST_REQ,
    ELE_WRITE_SHADOW_REQ,
])


def _read(offset, length):
    value = 0
    i = 0
    while i < length:
        if 0 <= offset + i < len(memory):
            value |= (memory[offset + i] & 0xFF) << (8 * i)
        i += 1
    return value


def _write(offset, value, length):
    i = 0
    while i < length:
        if 0 <= offset + i < len(memory):
            memory[offset + i] = (value >> (8 * i)) & 0xFF
        i += 1


def _read32(offset):
    return _read(offset, 4)


def _write32(offset, value):
    _write(offset, value & 0xFFFFFFFF, 4)


def _response_header(command, size, version=ELE_VERSION):
    return ((ELE_RESP_TAG << 24) | ((command & 0xFF) << 16) |
            ((size & 0xFF) << 8) | (version & 0xFF))


def _system_bus():
    machines = list(EmulationManager.Instance.CurrentEmulation.Machines)
    if len(machines) == 0:
        raise Exception("i.MX952 ELE has no machine context")
    return machines[0].SystemBus


def _address_valid(address, size):
    return address != 0 and size > 0 and address < ELE_MAX_ADDR and \
        size <= ELE_MAX_ADDR and address + size <= ELE_MAX_ADDR


def _write_info_block(address, requested_size):
    size = min(requested_size, ELE_GET_INFO_WORDS * 4)
    values = [0] * ELE_GET_INFO_WORDS
    values[0] = 0x00000100
    values[1] = IMX952_SOC_INFO
    values[2] = IMX952_LIFECYCLE
    values[3:7] = IMX952_UID
    bus = _system_bus()
    index = 0
    while index * 4 < size:
        bus.WriteDoubleWord(address + index * 4, values[index])
        index += 1


def _write_test_random(address, size):
    # Fixed xorshift stream for repeatable testing. This is not entropy and is
    # unavailable unless ELE_TEST_MAGIC is explicitly written first.
    bus = _system_bus()
    state = (0x952B0001 ^ address ^ size) & 0xFFFFFFFF
    index = 0
    while index < size:
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17) & 0xFFFFFFFF
        state ^= (state << 5) & 0xFFFFFFFF
        bus.WriteByte(address + index, state & 0xFF)
        index += 1


def _queue_response(words):
    global response_words
    response_words = list(words)
    _refresh_rx_registers()


def _success(command, extra=None, version=ELE_VERSION):
    payload = [] if extra is None else list(extra)
    _queue_response([_response_header(command, 2 + len(payload), version),
                     ELE_SUCCESS_IND] + payload)


def _failure(command, indication=ELE_PERMISSION_DENIED_FAILURE_IND,
             version=ELE_VERSION):
    _queue_response([_response_header(command, 2, version), indication])


def _refresh_rx_registers():
    rsr = 0
    index = 0
    limit = min(len(response_words), MU_RR_COUNT)
    while index < limit:
        _write32(MU_RR0 + index * MU_REGISTER_STRIDE, response_words[index])
        rsr |= 1 << index
        index += 1
    _write32(MU_RSR, rsr)


def _consume_rx_register(index):
    if index >= len(response_words):
        return 0
    value = response_words[index]
    if len(response_words) <= MU_RR_COUNT:
        _write32(MU_RSR, _read32(MU_RSR) & (~(1 << index) & 0xFFFFFFFF))
    return value


def _valid_request(version, tag, size):
    return tag == ELE_CMD_TAG and size >= 1 and version in set([ELE_VERSION, ELE_VERSION_FW])


def _process_request():
    global tx_words, expected_tx_words, rng_started, voltage_change_active
    global rng_request_count, ele_events
    if len(tx_words) < 1:
        return

    header = tx_words[0]
    version = header & 0xFF
    size = (header >> 8) & 0xFF
    command = (header >> 16) & 0xFF
    tag = (header >> 24) & 0xFF

    if not _valid_request(version, tag, size):
        _queue_response([_response_header(command, 2, version), ELE_FAILURE_IND])
    elif command == ELE_PING_REQ and size == 1:
        _success(command, version=version)
    elif command == ELE_GET_INFO_REQ and size >= 4 and len(tx_words) >= 4:
        address = ((tx_words[1] & 0xFFFFFFFF) << 32) | (tx_words[2] & 0xFFFFFFFF)
        requested_size = tx_words[3] & 0xFFFFFFFF
        if not _address_valid(address, requested_size):
            _failure(command, ELE_WRONG_ADDRESS_FAILURE_IND, version)
        else:
            _write_info_block(address, requested_size)
            _success(command, version=version)
            self.InfoLog("i.MX952 ELE GET_INFO: wrote %d bytes to 0x%X" %
                         (requested_size, address))
    elif command == ELE_READ_FUSE_REQ and size >= 2 and len(tx_words) >= 2:
        fuse_id = tx_words[1] & 0xFFFFFFFF
        if fuse_id not in ELE_FUSES:
            _failure(command, ELE_BAD_FUSE_ID_FAILURE_IND, version)
        else:
            _success(command, [ELE_FUSES[fuse_id]], version)
    elif command == ELE_READ_SHADOW_REQ and size >= 2 and len(tx_words) >= 2:
        fuse_id = tx_words[1] & 0xFFFFFFFF
        if fuse_id not in ELE_FUSES:
            _failure(command, ELE_BAD_FUSE_ID_FAILURE_IND, version)
        else:
            _success(command, [ELE_FUSES[fuse_id]], version)
    elif command == ELE_GET_FW_STATUS_REQ and size == 1:
        _success(command, [0], version)
    elif command == ELE_GET_FW_VERSION_REQ and size == 1:
        _success(command, [ELE_FW_VERSION_VALUE, ELE_FW_SHA1_VALUE], version)
    elif command == ELE_GET_EVENTS_REQ and size == 1:
        selected = ele_events[:1]
        _success(command, [len(selected)] + selected, version)
        ele_events = ele_events[len(selected):]
    elif command == ELE_VOLT_CHANGE_START_REQ and size == 1:
        if voltage_change_active:
            _failure(command, ELE_INVALID_OPERATION_FAILURE_IND, version)
        else:
            voltage_change_active = True
            _write32(ELE_TEST_VOLTAGE_STATE, 1)
            _success(command, version=version)
    elif command == ELE_VOLT_CHANGE_FINISH_REQ and size == 1:
        if not voltage_change_active:
            _failure(command, ELE_INVALID_OPERATION_FAILURE_IND, version)
        else:
            voltage_change_active = False
            _write32(ELE_TEST_VOLTAGE_STATE, 0)
            _success(command, version=version)
    elif command == ELE_START_RNG_REQ and size == 1:
        rng_started = True
        _success(command, version=version)
    elif command == ELE_GET_TRNG_STATE_REQ and size == 1:
        # data[1] is struct {u8 trng_state; u8 csal_state; u16 reserved}.
        state = 0x00000203 if rng_started else 0
        _success(command, [state], version)
    elif command == ELE_GET_RNG_REQ and size == 4 and len(tx_words) >= 4:
        address = tx_words[2] & 0xFFFFFFFF
        requested_size = tx_words[3] & 0xFFFFFFFF
        if version != ELE_VERSION_FW:
            _failure(command, ELE_INVALID_MESSAGE_FAILURE_IND, version)
        elif not rng_started:
            _failure(command, ELE_RNG_NOT_STARTED_FAILURE_IND, version)
        elif not test_rng_enabled:
            _failure(command, ELE_DISABLED_FEATURE_FAILURE_IND, version)
        elif requested_size > ELE_MAX_TEST_RNG_BYTES or not _address_valid(address, requested_size):
            _failure(command, ELE_BAD_VALUE_FAILURE_IND, version)
        else:
            _write_test_random(address, requested_size)
            rng_request_count += 1
            _write32(ELE_TEST_RNG_COUNT, rng_request_count)
            _success(command, version=version)
    elif command in ELE_SECURE_DENY_COMMANDS:
        _failure(command, ELE_PERMISSION_DENIED_FAILURE_IND, version)
        self.WarningLog("i.MX952 ELE secure command denied: 0x%X" % command)
    else:
        _failure(command, ELE_INVALID_MESSAGE_FAILURE_IND, version)
        self.WarningLog("i.MX952 ELE unsupported command 0x%X size=%d" %
                        (command, size))

    tx_words = []
    expected_tx_words = 0


if request.IsInit:
    memory = [0] * 0x10000
    tx_words = []
    expected_tx_words = 0
    response_words = []
    ele_events = []
    rng_started = False
    test_rng_enabled = False
    rng_request_count = 0
    voltage_change_active = False
    _write32(MU_PAR, (MU_RR_COUNT << 8) | MU_TR_COUNT)
    _write32(MU_TSR, (1 << MU_TR_COUNT) - 1)
    _write32(MU_RSR, 0)
    _write32(ELE_TEST_CONTROL, 0)
    _write32(ELE_TEST_EVENT, 0)
    _write32(ELE_TEST_VOLTAGE_STATE, 0)
    _write32(ELE_TEST_RNG_COUNT, 0)
elif request.IsRead:
    offset = request.Offset
    if (request.Length == 4 and MU_RR0 <= offset < MU_RR0 + MU_RR_COUNT * 4
            and ((offset - MU_RR0) % 4) == 0):
        request.Value = _consume_rx_register((offset - MU_RR0) // 4)
    else:
        request.Value = _read(offset, request.Length)
elif request.IsWrite:
    offset = request.Offset
    value = request.Value
    length = request.Length

    if offset == ELE_TEST_CONTROL and length == 4:
        test_rng_enabled = value == ELE_TEST_MAGIC
        _write32(ELE_TEST_CONTROL, ELE_TEST_MAGIC if test_rng_enabled else 0)
    elif offset == ELE_TEST_EVENT and length == 4:
        if len(ele_events) < 8:
            ele_events.append(value & 0xFFFFFFFF)
        _write32(ELE_TEST_EVENT, 0)
    elif (length == 4 and MU_TR0 <= offset < MU_TR0 + MU_TR_COUNT * 4
          and ((offset - MU_TR0) % 4) == 0):
        index = (offset - MU_TR0) // 4
        _write32(offset, value)
        if index == 0:
            tx_words = [value & 0xFFFFFFFF]
            expected_tx_words = (value >> 8) & 0xFF
        else:
            while len(tx_words) < index:
                tx_words.append(0)
            if len(tx_words) == index:
                tx_words.append(value & 0xFFFFFFFF)
            else:
                tx_words[index] = value & 0xFFFFFFFF
        if expected_tx_words > 0 and len(tx_words) >= expected_tx_words:
            _process_request()
    else:
        _write(offset, value, length)
