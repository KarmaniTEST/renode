*** Settings ***
Documentation     Validate source-derived i.MX952 SCMI Clock permissions while preserving the global 198-clock ID space.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}          ${CURDIR}/../../platforms/boards/nxp_imx952_evk_full.repl
${AP_GCR}            0x445B0114
${AP_S_HEADER}       0x445B1018
${AP_S_PAYLOAD}      0x445B101C
${AP_S_RESPONSE1}    0x445B1020
${AP_NS_HEADER}      0x445B1118
${AP_NS_PAYLOAD}     0x445B111C
${AP_NS_RESPONSE1}   0x445B1120
${M7_GCR}            0x44610114
${M7_HEADER}         0x44611018
${M7_PAYLOAD}        0x4461101C
${M7_RESPONSE1}      0x44611020

*** Keywords ***
Create Full Candidate
    Execute Command    mach create "imx952-clock-permissions"
    Execute Command    machine LoadPlatformDescription @${PLATFORM}

Write Dword
    [Arguments]    ${address}    ${value}
    Execute Command    sysbus WriteDoubleWord ${address} ${value}

Read Dword
    [Arguments]    ${address}
    ${value}=    Execute Command    sysbus ReadDoubleWord ${address}
    RETURN    ${value.strip()}

Call AP S
    [Arguments]    ${header}
    Write Dword    ${AP_S_HEADER}    ${header}
    Write Dword    ${AP_GCR}         1

Call AP NS
    [Arguments]    ${header}
    Write Dword    ${AP_NS_HEADER}    ${header}
    Write Dword    ${AP_GCR}          4

Call M7
    [Arguments]    ${header}
    Write Dword    ${M7_HEADER}    ${header}
    Write Dword    ${M7_GCR}       1

*** Test Cases ***
Clock Protocol Keeps Global 198 Clock Inventory
    Create Full Candidate
    Call AP S    0x00005001
    ${aps_status}=    Read Dword    ${AP_S_PAYLOAD}
    ${aps_count}=     Read Dword    ${AP_S_RESPONSE1}
    Should Be Equal As Numbers    ${aps_status}    0
    Should Be Equal As Numbers    ${aps_count}     198

    Call AP NS    0x00005001
    ${apns_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${apns_count}=     Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${apns_status}    0
    Should Be Equal As Numbers    ${apns_count}     198

    Call M7    0x00005001
    ${m7_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_count}=     Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${m7_status}    0
    Should Be Equal As Numbers    ${m7_count}     198

Clock Get Permissions Matches Generated Agent Map
    Create Full Candidate
    # AP-S owns ARMPLL_VCO clock 24, but not LPUART1 clock 52.
    Write Dword    ${AP_S_PAYLOAD}    24
    Call AP S      0x0000500F
    ${aps_arm_status}=    Read Dword    ${AP_S_PAYLOAD}
    ${aps_arm_perms}=     Read Dword    ${AP_S_RESPONSE1}
    Should Be Equal As Numbers    ${aps_arm_status}    0
    Should Be Equal As Numbers    ${aps_arm_perms}     0xE0000000

    Write Dword    ${AP_S_PAYLOAD}    52
    Call AP S      0x0000500F
    ${aps_uart_perms}=    Read Dword    ${AP_S_RESPONSE1}
    Should Be Equal As Numbers    ${aps_uart_perms}    0

    # AP-NS owns LPUART1 clock 52, but not AP-S ARMPLL_VCO clock 24.
    Write Dword    ${AP_NS_PAYLOAD}    52
    Call AP NS     0x0000500F
    ${apns_uart_perms}=    Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${apns_uart_perms}    0xE0000000

    Write Dword    ${AP_NS_PAYLOAD}    24
    Call AP NS     0x0000500F
    ${apns_arm_perms}=    Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${apns_arm_perms}    0

    # M7 owns CAN1 clock 44 only from this sample pair.
    Write Dword    ${M7_PAYLOAD}    44
    Call M7        0x0000500F
    ${m7_can_perms}=    Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${m7_can_perms}    0xE0000000

    Write Dword    ${M7_PAYLOAD}    52
    Call M7        0x0000500F
    ${m7_uart_perms}=    Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${m7_uart_perms}    0

Clock Attributes Mark Unassigned Clocks Restricted
    Create Full Candidate
    # AP-S clock 24 is assigned and uses the source-derived ARMPLL_VCO name.
    Write Dword    ${AP_S_PAYLOAD}    24
    Call AP S      0x00005003
    ${allowed_status}=    Read Dword    ${AP_S_PAYLOAD}
    ${allowed_attrs}=     Read Dword    ${AP_S_RESPONSE1}
    ${allowed_name0}=     Read Dword    0x445B1024
    Should Be Equal As Numbers    ${allowed_status}    0
    Should Be Equal As Numbers    ${allowed_attrs} & 0x2    0
    Should Be Equal As Numbers    ${allowed_name0}    0x504D5241

    # AP-S clock 52 remains globally addressable but is marked restricted.
    Write Dword    ${AP_S_PAYLOAD}    52
    Call AP S      0x00005003
    ${restricted_status}=    Read Dword    ${AP_S_PAYLOAD}
    ${restricted_attrs}=     Read Dword    ${AP_S_RESPONSE1}
    Should Be Equal As Numbers    ${restricted_status}    0
    Should Be Equal As Numbers    ${restricted_attrs} & 0x2    0x2

Unauthorized Clock Rate Mutation Is Denied Without State Change
    Create Full Candidate
    # AP-S is not permitted to set LPUART1 clock 52.
    Write Dword    ${AP_S_PAYLOAD}      0
    Write Dword    ${AP_S_RESPONSE1}    52
    Write Dword    0x445B1024            123456789
    Write Dword    0x445B1028            0
    Call AP S      0x00005005
    ${denied}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${denied}    0xFFFFFFFD

    # AP-NS owns clock 52 and can set/read its modeled rate.
    Write Dword    ${AP_NS_PAYLOAD}      0
    Write Dword    ${AP_NS_RESPONSE1}    52
    Write Dword    0x445B1124            123456789
    Write Dword    0x445B1128            0
    Call AP NS     0x00005005
    ${set_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${AP_NS_PAYLOAD}    52
    Call AP NS     0x00005006
    ${get_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${rate_low}=      Read Dword    ${AP_NS_RESPONSE1}
    ${rate_high}=     Read Dword    0x445B1124
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${rate_low}      123456789
    Should Be Equal As Numbers    ${rate_high}     0

Unauthorized Clock Config And Parent Mutation Are Denied
    Create Full Candidate
    # AP-NS does not own ARMPLL_VCO clock 24.
    Write Dword    ${AP_NS_PAYLOAD}      24
    Write Dword    ${AP_NS_RESPONSE1}    1
    Write Dword    0x445B1124            0
    Call AP NS     0x00005007
    ${config_denied}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${config_denied}    0xFFFFFFFD

    # M7 does not own LPUART1 clock 52 and may not change its parent.
    Write Dword    ${M7_PAYLOAD}      52
    Write Dword    ${M7_RESPONSE1}    0
    Call M7        0x0000500D
    ${parent_denied}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${parent_denied}    0xFFFFFFFD
