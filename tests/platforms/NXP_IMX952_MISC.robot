*** Settings ***
Documentation     Validate source-derived i.MX952 MISC permissions, controls, extended access, notifications and safe metadata.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}              ${CURDIR}/../../platforms/boards/nxp_imx952_evk_full.repl
${AP_GCR}                0x445B0114
${AP_GSR}                0x445B0118
${AP_NS_HEADER}          0x445B1118
${AP_NS_PAYLOAD}         0x445B111C
${AP_NS_RESPONSE1}       0x445B1120
${AP_NS_NOTIFY_STATUS}   0x445B1184
${AP_NS_NOTIFY_LENGTH}   0x445B1194
${AP_NS_NOTIFY_HEADER}   0x445B1198
${AP_NS_NOTIFY_PAYLOAD}  0x445B119C
${AP_NS_NOTIFY_FLAGS}    0x445B11A0
${AP_MISC_TRIGGER}       0x445B01F4

${M7_GCR}                0x44610114
${M7_GSR}                0x44610118
${M7_HEADER}             0x44611018
${M7_PAYLOAD}            0x4461101C
${M7_RESPONSE1}          0x44611020
${M7_NOTIFY_STATUS}      0x44611084
${M7_NOTIFY_LENGTH}      0x44611094
${M7_NOTIFY_HEADER}      0x44611098
${M7_NOTIFY_PAYLOAD}     0x4461109C
${M7_NOTIFY_FLAGS}       0x446110A0
${M7_MISC_TRIGGER}       0x446101F4

*** Keywords ***
Create Full Candidate
    Execute Command    mach create "imx952-misc"
    Execute Command    machine LoadPlatformDescription @${PLATFORM}

Write Dword
    [Arguments]    ${address}    ${value}
    Execute Command    sysbus WriteDoubleWord ${address} ${value}

Read Dword
    [Arguments]    ${address}
    ${value}=    Execute Command    sysbus ReadDoubleWord ${address}
    RETURN    ${value.strip()}

Call AP NS
    [Arguments]    ${header}
    Write Dword    ${AP_NS_HEADER}    ${header}
    Write Dword    ${AP_GCR}          4

Call M7
    [Arguments]    ${header}
    Write Dword    ${M7_HEADER}    ${header}
    Write Dword    ${M7_GCR}       1

Subscribe M7 Board Control
    [Arguments]    ${wire_id}    ${flags}
    Write Dword    ${M7_PAYLOAD}      ${wire_id}
    Write Dword    ${M7_RESPONSE1}    ${flags}
    Call M7        0x00021008
    ${status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${status}    0

Subscribe AP NS Board Control
    [Arguments]    ${wire_id}    ${flags}
    Write Dword    ${AP_NS_PAYLOAD}      ${wire_id}
    Write Dword    ${AP_NS_RESPONSE1}    ${flags}
    Call AP NS     0x00021008
    ${status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${status}    0

*** Test Cases ***
MISC Is Advertised To Source Permitted M7 And AP Nonsecure Agents
    Create Full Candidate
    # AP-NS: core + BBM + MISC = 9 non-base protocols.
    Call AP NS    0x00004001
    ${ap_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${ap_attrs}=     Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${ap_status}    0
    Should Be Equal As Numbers    ${ap_attrs}     0x00000309

    # M7: core + BBM + MISC + FuSa = 11 non-base protocols.
    Call M7    0x00004001
    ${m7_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_attrs}=     Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${m7_status}    0
    Should Be Equal As Numbers    ${m7_attrs}     0x0000030B

    # Direct M7 MISC version is available because M7 has board resources.
    Call M7    0x00021000
    ${m7_misc_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_version}=        Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${m7_misc_status}    0
    Should Be Equal As Numbers    ${m7_version}        0x00010001

MISC Version And Inventory Match Pinned Sources
    Create Full Candidate
    Call AP NS    0x00021000
    ${version_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${version}=           Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${version_status}    0
    Should Be Equal As Numbers    ${version}           0x00010001

    # 8 board controls, 32 reasons, 10 device controls.
    Call AP NS    0x00021001
    ${attr_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${attrs}=          Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${attr_status}    0
    Should Be Equal As Numbers    ${attrs}          0x0820000A

AP Nonsecure Has All Ten Masked Device Controls
    Create Full Candidate
    # MQS1_SETTINGS control 1 uses exact mask 0x0000FF0E.
    Write Dword    ${AP_NS_PAYLOAD}      1
    Write Dword    ${AP_NS_RESPONSE1}    1
    Write Dword    0x445B1124            0xFFFFFFFF
    Call AP NS     0x00021003
    ${set_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${AP_NS_PAYLOAD}    1
    Call AP NS     0x00021004
    ${get_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${num_val}=       Read Dword    ${AP_NS_RESPONSE1}
    ${value}=         Read Dword    0x445B1124
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${num_val}       1
    Should Be Equal As Numbers    ${value}         0x0000FF0E

    # BYPASS_AUDMIX control 8 is now correctly source-permitted and mask-limited.
    Write Dword    ${AP_NS_PAYLOAD}      8
    Write Dword    ${AP_NS_RESPONSE1}    1
    Write Dword    0x445B1124            3
    Call AP NS     0x00021003
    ${set8}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${set8}    0
    Write Dword    ${AP_NS_PAYLOAD}    8
    Call AP NS     0x00021004
    ${get8}=      Read Dword    ${AP_NS_PAYLOAD}
    ${value8}=    Read Dword    0x445B1124
    Should Be Equal As Numbers    ${get8}      0
    Should Be Equal As Numbers    ${value8}    1

Board Control Flag And Permission Hierarchy Are Enforced
    Create Full Candidate
    # M7 BUTTON is board-local control 4, encoded as 0x8004. NOTIFY includes GET.
    Write Dword    ${M7_PAYLOAD}    0x8004
    Call M7        0x00021004
    ${button_get}=    Read Dword    ${M7_PAYLOAD}
    ${button_num}=    Read Dword    ${M7_RESPONSE1}
    ${button_val}=    Read Dword    0x44611024
    Should Be Equal As Numbers    ${button_get}    0
    Should Be Equal As Numbers    ${button_num}    1
    Should Be Equal As Numbers    ${button_val}    0

    # M7 has no device-control permission.
    Write Dword    ${M7_PAYLOAD}    0
    Call M7        0x00021004
    ${device_denied}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${device_denied}    0xFFFFFFFD

    # AP-NS has no TEST board-control permission.
    Write Dword    ${AP_NS_PAYLOAD}    0x8005
    Call AP NS     0x00021004
    ${test_denied}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${test_denied}    0xFFFFFFFD

M7 PCA2131 Extended Access Is Stateful And Bounded
    Create Full Candidate
    # Board-local PCA2131 control 6 is encoded as 0x8006.
    Write Dword    ${M7_PAYLOAD}       0x8006
    Write Dword    ${M7_RESPONSE1}     0x10
    Write Dword    0x44611024          3
    Write Dword    0x44611028          3
    Write Dword    0x4461102C          0xAA
    Write Dword    0x44611030          0xBB
    Write Dword    0x44611034          0xCC
    Call M7        0x00021020
    ${set_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${M7_PAYLOAD}       0x8006
    Write Dword    ${M7_RESPONSE1}     0x10
    Write Dword    0x44611024          3
    Call M7        0x00021021
    ${get_status}=    Read Dword    ${M7_PAYLOAD}
    ${num_val}=       Read Dword    ${M7_RESPONSE1}
    ${v0}=            Read Dword    0x44611024
    ${v1}=            Read Dword    0x44611028
    ${v2}=            Read Dword    0x4461102C
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${num_val}       3
    Should Be Equal As Numbers    ${v0}            0xAA
    Should Be Equal As Numbers    ${v1}            0xBB
    Should Be Equal As Numbers    ${v2}            0xCC

    # Device extended access is source-defined as unsupported.
    Write Dword    ${AP_NS_PAYLOAD}       9
    Write Dword    ${AP_NS_RESPONSE1}     0
    Write Dword    0x445B1124             1
    Call AP NS     0x00021021
    ${device_ext}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${device_ext}    0xFFFFFFFF

M7 TEST Action Is Recorded Without Fabricating Safety Reaction
    Create Full Candidate
    Write Dword    ${M7_PAYLOAD}       0x8005
    Write Dword    ${M7_RESPONSE1}     0
    Write Dword    0x44611024          0
    Call M7        0x00021005
    ${status}=     Read Dword    ${M7_PAYLOAD}
    ${num_rtn}=    Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${status}     0
    Should Be Equal As Numbers    ${num_rtn}    0

MISC Control Events Use Agent Normal P2A Channels
    Create Full Candidate
    Subscribe M7 Board Control    0x8004    3
    # board local 4, state high -> event flags 2.
    Write Dword    ${M7_MISC_TRIGGER}    0x104
    ${m7_status}=     Read Dword    ${M7_NOTIFY_STATUS}
    ${m7_length}=     Read Dword    ${M7_NOTIFY_LENGTH}
    ${m7_header}=     Read Dword    ${M7_NOTIFY_HEADER}
    ${m7_ctrl}=       Read Dword    ${M7_NOTIFY_PAYLOAD}
    ${m7_flags}=      Read Dword    ${M7_NOTIFY_FLAGS}
    ${m7_gsr}=        Read Dword    ${M7_GSR}
    Should Be Equal As Numbers    ${m7_status}    0
    Should Be Equal As Numbers    ${m7_length}    12
    Should Be Equal As Numbers    ${m7_header}    0x00021300
    Should Be Equal As Numbers    ${m7_ctrl}      0x8004
    Should Be Equal As Numbers    ${m7_flags}     2
    Should Be Equal As Numbers    ${m7_gsr}       3

    Subscribe AP NS Board Control    0x8000    3
    # SD3_WAKE board local 0, state high.
    Write Dword    ${AP_MISC_TRIGGER}    0x100
    ${ap_status}=     Read Dword    ${AP_NS_NOTIFY_STATUS}
    ${ap_header}=     Read Dword    ${AP_NS_NOTIFY_HEADER}
    ${ap_ctrl}=       Read Dword    ${AP_NS_NOTIFY_PAYLOAD}
    ${ap_flags}=      Read Dword    ${AP_NS_NOTIFY_FLAGS}
    ${ap_gsr}=        Read Dword    ${AP_GSR}
    Should Be Equal As Numbers    ${ap_status}    0
    Should Be Equal As Numbers    ${ap_header}    0x00021300
    Should Be Equal As Numbers    ${ap_ctrl}      0x8000
    Should Be Equal As Numbers    ${ap_flags}     2
    Should Be Equal As Numbers    ${ap_gsr}       12

MISC Normal Queue Preserves Event Order While Busy
    Create Full Candidate
    Subscribe M7 Board Control    0x8004    3
    Write Dword    ${M7_MISC_TRIGGER}    4
    Write Dword    ${M7_MISC_TRIGGER}    0x104
    ${first_header}=    Read Dword    ${M7_NOTIFY_HEADER}
    ${first_flags}=     Read Dword    ${M7_NOTIFY_FLAGS}
    Should Be Equal As Numbers    ${first_header}    0x00021300
    Should Be Equal As Numbers    ${first_flags}     1

    Write Dword    ${M7_NOTIFY_STATUS}    1
    ${second_status}=    Read Dword    ${M7_NOTIFY_STATUS}
    ${second_header}=    Read Dword    ${M7_NOTIFY_HEADER}
    ${second_flags}=     Read Dword    ${M7_NOTIFY_FLAGS}
    Should Be Equal As Numbers    ${second_status}    0
    Should Be Equal As Numbers    ${second_header}    0x00061300
    Should Be Equal As Numbers    ${second_flags}     2

Safe Target Metadata Does Not Fabricate Physical Fuse Values
    Create Full Candidate
    Call AP NS    0x0002100B
    ${si_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${device_id}=    Read Dword    ${AP_NS_RESPONSE1}
    ${si_rev}=       Read Dword    0x445B1124
    ${part_num}=     Read Dword    0x445B1128
    ${si_name_0}=    Read Dword    0x445B112C
    Should Be Equal As Numbers    ${si_status}    0
    Should Be Equal As Numbers    ${device_id}    0
    Should Be Equal As Numbers    ${si_rev}       0
    Should Be Equal As Numbers    ${part_num}     0
    Should Be Equal As Numbers    ${si_name_0}    0x584D2E69

    Call AP NS    0x0002100C
    ${cfg_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${m_sel}=         Read Dword    ${AP_NS_RESPONSE1}
    ${cfg_name_0}=    Read Dword    0x445B1124
    Should Be Equal As Numbers    ${cfg_status}    0
    Should Be Equal As Numbers    ${m_sel}         0
    Should Be Equal As Numbers    ${cfg_name_0}    0x3539786D

    Call AP NS    0x0002100E
    ${brd_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${brd_attrs}=     Read Dword    ${AP_NS_RESPONSE1}
    ${brd_name_0}=    Read Dword    0x445B1124
    Should Be Equal As Numbers    ${brd_status}    0
    Should Be Equal As Numbers    ${brd_attrs}     0
    Should Be Equal As Numbers    ${brd_name_0}    0x584D2E69

Reset Reason DDR Region And ROM Boundary Remain Deterministic
    Create Full Candidate
    Call AP NS    0x0002100A
    ${reason_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${boot_flags}=       Read Dword    ${AP_NS_RESPONSE1}
    ${shutdown_flags}=   Read Dword    0x445B1124
    Should Be Equal As Numbers    ${reason_status}     0
    Should Be Equal As Numbers    ${boot_flags}        0x8000001F
    Should Be Equal As Numbers    ${shutdown_flags}    0x8000001F

    Write Dword    ${AP_NS_PAYLOAD}    0
    Call AP NS     0x00021022
    ${ddr_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${ddr_attrs}=     Read Dword    ${AP_NS_RESPONSE1}
    ${mts}=           Read Dword    0x445B1124
    ${start_low}=     Read Dword    0x445B1128
    ${end_low}=       Read Dword    0x445B1130
    Should Be Equal As Numbers    ${ddr_status}    0
    Should Be Equal As Numbers    ${ddr_attrs}     0x00010200
    Should Be Equal As Numbers    ${mts}           0
    Should Be Equal As Numbers    ${start_low}     0x80000000
    Should Be Equal As Numbers    ${end_low}       0xFFFFFFFF

    Call AP NS    0x00021007
    ${rom_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${rom_status}    0xFFFFFFFF
