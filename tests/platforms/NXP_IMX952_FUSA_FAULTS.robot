*** Settings ***
Documentation     Validate i.MX952 M7 FuSa fault permissions, state, group notification and priority fault events.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}              ${CURDIR}/../../platforms/boards/nxp_imx952_evk_full.repl
${M7_GCR}                0x44610114
${M7_GSR}                0x44610118
${M7_HEADER}             0x44611018
${M7_PAYLOAD}            0x4461101C
${M7_RESPONSE1}          0x44611020
${M7_RESPONSE2}          0x44611024
${M7_PRIORITY_STATUS}    0x44611104
${M7_PRIORITY_LENGTH}    0x44611114
${M7_PRIORITY_HEADER}    0x44611118
${M7_PRIORITY_PAYLOAD0}  0x4461111C
${M7_PRIORITY_PAYLOAD1}  0x44611120
${M7_FAULT_TRIGGER}      0x446101F8

*** Keywords ***
Create Full Candidate
    Execute Command    mach create "imx952-fusa-faults"
    Execute Command    machine LoadPlatformDescription @${PLATFORM}

Write Dword
    [Arguments]    ${address}    ${value}
    Execute Command    sysbus WriteDoubleWord ${address} ${value}

Read Dword
    [Arguments]    ${address}
    ${value}=    Execute Command    sysbus ReadDoubleWord ${address}
    RETURN    ${value.strip()}

Call M7
    [Arguments]    ${header}
    Write Dword    ${M7_HEADER}    ${header}
    Write Dword    ${M7_GCR}       1

Configure Fault Notifications
    [Arguments]    ${first}    ${mask}    ${enable}
    Write Dword    ${M7_PAYLOAD}      ${first}
    Write Dword    ${M7_RESPONSE1}    ${mask}
    Write Dword    ${M7_RESPONSE2}    ${enable}
    Call M7        0x00020C0A

*** Test Cases ***
FuSa Fault Get And Set Enforce Exact Five Fault Permission Map
    Create Full Candidate
    # SW0 fault 22 is permitted and initially clear.
    Write Dword    ${M7_PAYLOAD}    22
    Call M7        0x00020C08
    ${get0}=      Read Dword    ${M7_PAYLOAD}
    ${state0}=    Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${get0}      0
    Should Be Equal As Numbers    ${state0}    0

    # NXP maps any nonzero flags[1:0] to asserted/set.
    Write Dword    ${M7_PAYLOAD}      22
    Write Dword    ${M7_RESPONSE1}    1
    Call M7        0x00020C09
    ${set_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${M7_PAYLOAD}    22
    Call M7        0x00020C08
    ${get1}=      Read Dword    ${M7_PAYLOAD}
    ${state1}=    Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${get1}      0
    Should Be Equal As Numbers    ${state1}    1

    # WDOG4 fault 20 is globally valid but not permitted to M7.
    Write Dword    ${M7_PAYLOAD}    20
    Call M7        0x00020C08
    ${denied}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${denied}    0xFFFFFFFD

    # 89 is outside the global 0..88 inventory.
    Write Dword    ${M7_PAYLOAD}    89
    Call M7        0x00020C08
    ${not_found}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${not_found}    0xFFFFFFFC

Fault Group Notify Applies Mixed Window Permissions And Returns Effective Mask
    Create Full Candidate
    # Window starts at fault20. Mask faults20..23; only 21..23 are permitted.
    Configure Fault Notifications    20    0xF    0xA
    ${status}=      Read Dword    ${M7_PAYLOAD}
    ${first}=       Read Dword    ${M7_RESPONSE1}
    ${enabled}=     Read Dword    ${M7_RESPONSE2}
    Should Be Equal As Numbers    ${status}     0
    Should Be Equal As Numbers    ${first}      20
    Should Be Equal As Numbers    ${enabled}    0xA

    # Disable fault23 and retain fault21.
    Configure Fault Notifications    20    0x8    0
    ${status2}=     Read Dword    ${M7_PAYLOAD}
    ${enabled2}=    Read Dword    ${M7_RESPONSE2}
    Should Be Equal As Numbers    ${status2}     0
    Should Be Equal As Numbers    ${enabled2}    0x2

    # An update containing only unpermitted fault20 is denied.
    Configure Fault Notifications    20    1    1
    ${denied}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${denied}    0xFFFFFFFD

FuSa Fault Recovery And Command Clear Preserve Priority FIFO Order
    Create Full Candidate
    Configure Fault Notifications    22    1    1
    ${subscribe}=    Read Dword    ${M7_PAYLOAD}
    ${enabled}=      Read Dword    ${M7_RESPONSE2}
    Should Be Equal As Numbers    ${subscribe}    0
    Should Be Equal As Numbers    ${enabled}      1

    # Deterministic recovery input asserts fault22 and emits state flag 1.
    Write Dword    ${M7_FAULT_TRIGGER}    0x116
    ${status}=     Read Dword    ${M7_PRIORITY_STATUS}
    ${length}=     Read Dword    ${M7_PRIORITY_LENGTH}
    ${header}=     Read Dword    ${M7_PRIORITY_HEADER}
    ${fault}=      Read Dword    ${M7_PRIORITY_PAYLOAD0}
    ${flags}=      Read Dword    ${M7_PRIORITY_PAYLOAD1}
    Should Be Equal As Numbers    ${status}    0
    Should Be Equal As Numbers    ${length}    12
    Should Be Equal As Numbers    ${header}    0x00020F02
    Should Be Equal As Numbers    ${fault}     22
    Should Be Equal As Numbers    ${flags}     1

    # Clear through SCMI while channel 2 is busy; clear event remains queued.
    Write Dword    ${M7_PAYLOAD}      22
    Write Dword    ${M7_RESPONSE1}    0
    Call M7        0x00020C09
    ${clear_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${clear_status}    0
    ${still_fault}=    Read Dword    ${M7_PRIORITY_PAYLOAD0}
    ${still_flags}=    Read Dword    ${M7_PRIORITY_PAYLOAD1}
    Should Be Equal As Numbers    ${still_fault}    22
    Should Be Equal As Numbers    ${still_flags}    1

    Write Dword    ${M7_GSR}                4
    Write Dword    ${M7_PRIORITY_STATUS}    1
    ${second_status}=    Read Dword    ${M7_PRIORITY_STATUS}
    ${second_header}=    Read Dword    ${M7_PRIORITY_HEADER}
    ${second_fault}=     Read Dword    ${M7_PRIORITY_PAYLOAD0}
    ${second_flags}=     Read Dword    ${M7_PRIORITY_PAYLOAD1}
    Should Be Equal As Numbers    ${second_status}    0
    Should Be Equal As Numbers    ${second_header}    0x00060F02
    Should Be Equal As Numbers    ${second_fault}     22
    Should Be Equal As Numbers    ${second_flags}     0

    Write Dword    ${M7_PAYLOAD}    22
    Call M7        0x00020C08
    ${get_status}=    Read Dword    ${M7_PAYLOAD}
    ${state}=         Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${state}         0
