# i.MX952 source-bounded SCMI FuSa S-check layer.
#
# Layering:
#   core -> SMT/P2A -> BBM -> MISC -> Clock -> Pinctrl -> FuSa -> S-check
#
# NXP's pinned FuSa protocol exposes FUSA_SCHECK_EVNTRIG (0x0B) and
# FUSA_SCHECK_TEST_EXEC (0x0E). The pinned LMM backend currently accepts both
# calls and returns success without implementing SCST/SAF execution or a
# hardware reaction. This wrapper mirrors that exact functional boundary and
# records deterministic invocation evidence only. It does not claim physical
# fault suppression, SCST execution, safety-island behavior or timing.

_SCHECK_PROTOCOL = 0x83
_SCHECK_EVENT_COMMAND = 0x0B
_SCHECK_TEST_EXEC_COMMAND = 0x0E
_SCHECK_MESSAGE_ATTRIBUTES = 0x02

# Deterministic evidence registers inside the Python peripheral window.
# These are test instrumentation, not i.MX952 production registers.
_SCHECK_EVENT_COUNT_OFFSET = 0x200
_SCHECK_LAST_TEST_ID_OFFSET = 0x204
_SCHECK_TEST_EXEC_COUNT_OFFSET = 0x208

_SCHECK_ORIGINAL_VALUE = request.Value if request.IsWrite else 0
_SCHECK_IS_AP = size >= 0x1400
_SCHECK_REQUEST_CHANNEL = None
_SCHECK_PRE_HEADER = 0
_SCHECK_PRE_WORDS = [0, 0]
_SCHECK_INTERCEPT = False

# FuSa is M7-only. Capture only local M7 A2P channel 0 requests.
if (request.IsWrite and request.Offset == 0x114 and
        not _SCHECK_IS_AP and (_SCHECK_ORIGINAL_VALUE & 0x1)):
    _SCHECK_REQUEST_CHANNEL = 0
    _scheck_base = 0x1000
    _SCHECK_PRE_HEADER = _read32(_scheck_base + 0x18)
    _SCHECK_PRE_WORDS[0] = _read32(_scheck_base + 0x1C)
    _SCHECK_PRE_WORDS[1] = _read32(_scheck_base + 0x20)

    _scheck_protocol = (_SCHECK_PRE_HEADER >> 10) & 0xFF
    _scheck_message = _SCHECK_PRE_HEADER & 0xFF
    _scheck_requested_message = _SCHECK_PRE_WORDS[0]
    _SCHECK_INTERCEPT = (
        _scheck_protocol == _SCHECK_PROTOCOL and
        (
            _scheck_message in set([
                _SCHECK_EVENT_COMMAND,
                _SCHECK_TEST_EXEC_COMMAND,
            ]) or
            (
                _scheck_message == _SCHECK_MESSAGE_ATTRIBUTES and
                _scheck_requested_message in set([
                    _SCHECK_EVENT_COMMAND,
                    _SCHECK_TEST_EXEC_COMMAND,
                ])
            )
        )
    )
    if _SCHECK_INTERCEPT:
        # Prevent the lower FuSa layer from finalizing this request. The exact
        # header and payload are restored after the qualified lower stack runs.
        _write32(
            _scheck_base + 0x18,
            (0xFF << 10) | (_SCHECK_PRE_HEADER & 0x3FF),
        )

execfile("scripts/pydev/nxp_imx952_system_manager_fusa.py")


def _scheck_restore_request():
    base = SCMI_SRAM + SCMI_CHANNEL_SIZE * 0
    _write32(base + SMT_MESSAGE_HEADER, _SCHECK_PRE_HEADER)
    _write32(base + SMT_PAYLOAD, _SCHECK_PRE_WORDS[0])
    _write32(base + SMT_PAYLOAD + 4, _SCHECK_PRE_WORDS[1])


def _scheck_publish_evidence():
    _write32(_SCHECK_EVENT_COUNT_OFFSET, fusa_scheck_event_count)
    _write32(_SCHECK_LAST_TEST_ID_OFFSET, fusa_scheck_last_test_id)
    _write32(_SCHECK_TEST_EXEC_COUNT_OFFSET, fusa_scheck_test_exec_count)


def _scheck_complete_response():
    # The lower layer has already applied the A2P response doorbell semantics.
    # Reassert them after replacing the masked response for clarity and drift
    # resistance.
    _write32(MU_GSR, _read32(MU_GSR) | 0x1)
    _update_m7_scmi_irq()


if request.IsInit:
    fusa_scheck_event_count = 0
    fusa_scheck_last_test_id = 0
    fusa_scheck_test_exec_count = 0
    _scheck_publish_evidence()

elif (request.IsWrite and request.Offset == 0x114 and
      _SCHECK_REQUEST_CHANNEL == 0 and _SCHECK_INTERCEPT):
    _scheck_restore_request()
    message_id = _SCHECK_PRE_HEADER & 0xFF

    if message_id == _SCHECK_MESSAGE_ATTRIBUTES:
        _set_response(0, SCMI_SUCCESS, [0])

    elif message_id == _SCHECK_EVENT_COMMAND:
        # Match the pinned NXP LMM boundary: accept and return success. The
        # backend has no additional side effect at the pinned commit.
        fusa_scheck_event_count += 1
        _scheck_publish_evidence()
        _set_response(0, SCMI_SUCCESS, [])

    elif message_id == _SCHECK_TEST_EXEC_COMMAND:
        # The pinned backend accepts the caller-provided targetTestId without
        # range validation. Record it as deterministic functional evidence.
        fusa_scheck_last_test_id = _SCHECK_PRE_WORDS[0] & 0xFFFFFFFF
        fusa_scheck_test_exec_count += 1
        _scheck_publish_evidence()
        _set_response(0, SCMI_SUCCESS, [])

    else:
        _set_response(0, SCMI_NOT_SUPPORTED, [])

    _scheck_complete_response()
