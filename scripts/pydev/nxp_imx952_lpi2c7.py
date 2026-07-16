# Functional i.MX 952 LPI2C7 model with the EVK USB Type-C controller.
# Implements the polling-mode master behavior used by NXP U-Boot.

VERID = 0x00
PARAM = 0x04
MCR = 0x10
MSR = 0x14
MFSR = 0x5C
MTDR = 0x60
MRDR = 0x70

MSR_SDF = 0x00000200
MSR_NDF = 0x00000400
MRDR_RXEMPTY = 0x00004000
MCR_RTF = 0x00000100
MCR_RRF = 0x00000200

CMD_TRANSMIT = 0
CMD_RECEIVE = 1
CMD_STOP = 2
CMD_START = 4

TCPC_ADDR = 0x50
TCPC_VENDOR_ID = 0x00
TCPC_PRODUCT_ID = 0x02
TCPC_ALERT = 0x10
TCPC_POWER_STATUS = 0x1E
TCPC_FAULT_STATUS = 0x1F


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


def _new_device():
    return [0] * 256


def _device(address):
    return devices.get(address)


def _initialize_tcpc():
    devices[TCPC_ADDR] = _new_device()
    pointers[TCPC_ADDR] = 0
    dev = devices[TCPC_ADDR]
    # NXP USB vendor ID and a deterministic PTN5110-like product identity.
    dev[TCPC_VENDOR_ID] = 0xC9
    dev[TCPC_VENDOR_ID + 1] = 0x1F
    dev[TCPC_PRODUCT_ID] = 0x10
    dev[TCPC_PRODUCT_ID + 1] = 0x51
    # Initialization complete. No cable/VBUS is attached by default.
    dev[TCPC_POWER_STATUS] = 0x00
    dev[TCPC_ALERT] = 0x00
    dev[TCPC_ALERT + 1] = 0x00
    dev[TCPC_FAULT_STATUS] = 0x80


def _begin(address, direction):
    global current_address, current_direction, write_bytes
    current_address = address & 0x7F
    current_direction = direction & 1
    write_bytes = []
    if _device(current_address) is None:
        _write32(MSR, _read32(MSR) | MSR_NDF)


def _transmit_byte(value):
    global write_bytes
    value &= 0xFF
    write_bytes.append(value)
    if current_address is None or current_direction != 0:
        return

    dev = _device(current_address)
    if dev is None:
        return
    if len(write_bytes) == 1:
        pointers[current_address] = value
    else:
        pointer = pointers.get(current_address, 0) & 0xFF
        # TCPC ALERT and FAULT_STATUS are write-one-to-clear registers.
        if current_address == TCPC_ADDR and (pointer == TCPC_ALERT or pointer == TCPC_ALERT + 1 or pointer == TCPC_FAULT_STATUS):
            dev[pointer] &= (~value) & 0xFF
        else:
            dev[pointer] = value
        pointers[current_address] = (pointer + 1) & 0xFF


def _prepare_receive(count):
    global rx_queue
    rx_queue = []
    if current_address is None:
        rx_queue = [0] * count
        return

    dev = _device(current_address)
    if dev is None:
        rx_queue = [0] * count
        return
    pointer = pointers.get(current_address, 0) & 0xFF
    i = 0
    while i < count:
        rx_queue.append(dev[pointer])
        pointer = (pointer + 1) & 0xFF
        i += 1
    pointers[current_address] = pointer


def _stop():
    global current_address, current_direction, write_bytes
    _write32(MSR, _read32(MSR) | MSR_SDF)
    current_address = None
    current_direction = 0
    write_bytes = []


def _handle_mtdr(value):
    command = (value >> 8) & 0x7
    data = value & 0xFF
    if command == CMD_START:
        _begin((data >> 1) & 0x7F, data & 1)
    elif command == CMD_TRANSMIT:
        _transmit_byte(data)
    elif command == CMD_RECEIVE:
        _prepare_receive(data + 1)
    elif command == CMD_STOP:
        _stop()
    _write32(MFSR, (len(rx_queue) & 0xFF) << 16)


if request.IsInit:
    memory = [0] * 0x10000
    devices = {}
    pointers = {}
    rx_queue = []
    current_address = None
    current_direction = 0
    write_bytes = []
    _write32(VERID, 0x01010000)
    _write32(PARAM, 0x00000202)
    _write32(MSR, 0)
    _write32(MFSR, 0)
    _initialize_tcpc()
elif request.IsRead:
    if request.Offset == MFSR and request.Length == 4:
        request.Value = (len(rx_queue) & 0xFF) << 16
    elif request.Offset == MRDR and request.Length == 4:
        if len(rx_queue) > 0:
            value = rx_queue.pop(0)
            _write32(MFSR, (len(rx_queue) & 0xFF) << 16)
            request.Value = value
        else:
            request.Value = MRDR_RXEMPTY
    else:
        request.Value = _read(request.Offset, request.Length)
elif request.IsWrite:
    offset = request.Offset
    value = request.Value
    length = request.Length
    if offset == MSR and length == 4:
        _write32(MSR, _read32(MSR) & (~value & 0xFFFFFFFF))
    elif offset == MCR and length == 4:
        _write32(MCR, value)
        if value & MCR_RRF:
            rx_queue = []
        if value & MCR_RTF:
            write_bytes = []
        _write32(MFSR, (len(rx_queue) & 0xFF) << 16)
    elif offset == MTDR and length == 4:
        _write32(MTDR, value)
        _handle_mtdr(value)
    else:
        _write(offset, value, length)
