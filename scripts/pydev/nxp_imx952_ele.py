# Functional subset of the NXP i.MX95-family EdgeLock Enclave (ELE) MU service.
# Implements the MU V2 transport and early boot services used by i.MX 952 U-Boot.

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
ELE_CMD_TAG = 0x17
ELE_RESP_TAG = 0xE1
ELE_READ_FUSE_REQ = 0x97
ELE_GET_FW_STATUS_REQ = 0xC5
ELE_GET_INFO_REQ = 0xDA
ELE_READ_SHADOW_REQ = 0xF3
ELE_SUCCESS_IND = 0xD6
ELE_FAILURE_IND = 0x29

# The i.MX9 SCMI SoC code derives silicon revision from the top byte.
# A0 represents revision 1.0.
IMX952_SOC_INFO = 0xA0000000
IMX952_LIFECYCLE = 0x00000020
IMX952_UID = [0x95200001, 0x52454E4F, 0x4445494D, 0x58393532]
ELE_GET_INFO_WORDS = 64

# Deterministic OTP contents. Unknown IDs read as zero, representing an
# unprogrammed fuse in the virtual platform.
ELE_FUSES = {
    0x00: 0x00000000,
    0x01: 0x00000000,
}


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


def _response_header(command, size):
    return (ELE_RESP_TAG << 24) | ((command & 0xFF) << 16) | ((size & 0xFF) << 8) | ELE_VERSION


def _system_bus():
    machines = list(EmulationManager.Instance.CurrentEmulation.Machines)
    if len(machines) == 0:
        raise Exception("i.MX952 ELE has no machine context")
    return machines[0].SystemBus


def _write_info_block(address, requested_size):
    size = requested_size
    if size > ELE_GET_INFO_WORDS * 4:
        size = ELE_GET_INFO_WORDS * 4

    values = [0] * ELE_GET_INFO_WORDS
    values[0] = 0x00000100
    values[1] = IMX952_SOC_INFO
    values[2] = IMX952_LIFECYCLE
    values[3] = IMX952_UID[0]
    values[4] = IMX952_UID[1]
    values[5] = IMX952_UID[2]
    values[6] = IMX952_UID[3]

    bus = _system_bus()
    index = 0
    while index * 4 < size:
        bus.WriteDoubleWord(address + index * 4, values[index])
        index += 1


def _queue_response(words):
    global response_words
    response_words = list(words)
    _refresh_rx_registers()


def _refresh_rx_registers():
    rsr = 0
    index = 0
    limit = len(response_words)
    if limit > MU_RR_COUNT:
        limit = MU_RR_COUNT
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
        rsr = _read32(MU_RSR) & (~(1 << index) & 0xFFFFFFFF)
        _write32(MU_RSR, rsr)
    return value


def _process_request():
    global tx_words, expected_tx_words
    if len(tx_words) < 1:
        return

    header = tx_words[0]
    version = header & 0xFF
    size = (header >> 8) & 0xFF
    command = (header >> 16) & 0xFF
    tag = (header >> 24) & 0xFF

    if version != ELE_VERSION or tag != ELE_CMD_TAG or size < 1:
        _queue_response([_response_header(command, 2), ELE_FAILURE_IND])
        tx_words = []
        expected_tx_words = 0
        return

    if command == ELE_GET_INFO_REQ and size >= 4 and len(tx_words) >= 4:
        address = ((tx_words[1] & 0xFFFFFFFF) << 32) | (tx_words[2] & 0xFFFFFFFF)
        requested_size = tx_words[3] & 0xFFFFFFFF
        _write_info_block(address, requested_size)
        _queue_response([_response_header(command, 2), ELE_SUCCESS_IND])
        self.InfoLog("i.MX952 ELE GET_INFO: wrote %d bytes to 0x%X" % (requested_size, address))
    elif command == ELE_READ_FUSE_REQ and size >= 2 and len(tx_words) >= 2:
        fuse_id = tx_words[1] & 0xFFFFFFFF
        _queue_response([_response_header(command, 3), ELE_SUCCESS_IND, ELE_FUSES.get(fuse_id, 0)])
    elif command == ELE_READ_SHADOW_REQ and size >= 2 and len(tx_words) >= 2:
        fuse_id = tx_words[1] & 0xFFFFFFFF
        _queue_response([_response_header(command, 3), ELE_SUCCESS_IND, ELE_FUSES.get(fuse_id, 0)])
    elif command == ELE_GET_FW_STATUS_REQ:
        # Firmware status low nibble 0 represents the normal operational state.
        _queue_response([_response_header(command, 3), ELE_SUCCESS_IND, 0])
    else:
        _queue_response([_response_header(command, 2), ELE_FAILURE_IND])
        self.WarningLog("i.MX952 ELE: unsupported command 0x%X size=%d" % (command, size))

    tx_words = []
    expected_tx_words = 0


if request.IsInit:
    memory = [0] * 0x10000
    tx_words = []
    expected_tx_words = 0
    response_words = []
    _write32(MU_PAR, (MU_RR_COUNT << 8) | MU_TR_COUNT)
    _write32(MU_TSR, (1 << MU_TR_COUNT) - 1)
    _write32(MU_RSR, 0)
elif request.IsRead:
    offset = request.Offset
    if request.Length == 4 and MU_RR0 <= offset < MU_RR0 + MU_RR_COUNT * 4 and ((offset - MU_RR0) % 4) == 0:
        request.Value = _consume_rx_register((offset - MU_RR0) // 4)
    else:
        request.Value = _read(offset, request.Length)
elif request.IsWrite:
    offset = request.Offset
    value = request.Value
    length = request.Length

    if length == 4 and MU_TR0 <= offset < MU_TR0 + MU_TR_COUNT * 4 and ((offset - MU_TR0) % 4) == 0:
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
