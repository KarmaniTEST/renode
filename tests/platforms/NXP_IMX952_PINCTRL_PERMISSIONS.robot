*** Settings ***
Documentation     Validate source-derived i.MX952 SCMI Pinctrl permissions, pin configuration state and daisy separation.
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
    Execute Command    mach create "imx952-pinctrl-permissions"
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
Pinctrl Protocol Exposes Global 140 Pin Inventory
    Create Full Candidate
    Call AP S    0x00006401
    ${aps_status}=    Read Dword    ${AP_S_PAYLOAD}
    ${aps_low}=       Read Dword    ${AP_S_RESPONSE1}
    ${aps_high}=      Read Dword    0x445B1024
    Should Be Equal As Numbers    ${aps_status}    0
    Should Be Equal As Numbers    ${aps_low}       140
    Should Be Equal As Numbers    ${aps_high}      0

    Call M7    0x00006401
    ${m7_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_low}=       Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${m7_status}    0
    Should Be Equal As Numbers    ${m7_low}       140

Pin Request Permissions Match Generated Map
    Create Full Candidate
    # M7 owns GPIO_IO14 pin 18.
    Write Dword    ${M7_PAYLOAD}      18
    Write Dword    ${M7_RESPONSE1}    0
    Call M7        0x00006407
    ${m7_allowed}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${m7_allowed}    0

    # M7 does not own pin 20.
    Write Dword    ${M7_PAYLOAD}      20
    Write Dword    ${M7_RESPONSE1}    0
    Call M7        0x00006407
    ${m7_denied}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${m7_denied}    0xFFFFFFFD

    # AP-NS owns pin 20 but explicitly not M7 pin 18.
    Write Dword    ${AP_NS_PAYLOAD}      20
    Write Dword    ${AP_NS_RESPONSE1}    0
    Call AP NS     0x00006407
    ${apns_allowed}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${apns_allowed}    0

    Write Dword    ${AP_NS_PAYLOAD}      18
    Write Dword    ${AP_NS_RESPONSE1}    0
    Call AP NS     0x00006407
    ${apns_denied}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${apns_denied}    0xFFFFFFFD

    # AP-S has no generated pin permissions.
    Write Dword    ${AP_S_PAYLOAD}      20
    Write Dword    ${AP_S_RESPONSE1}    0
    Call AP S      0x00006407
    ${aps_denied}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${aps_denied}    0xFFFFFFFD

M7 Pin Configuration Is Stateful And AP Nonsecure Cannot Mutate It
    Create Full Candidate
    # M7 configures pin 18 MUX type 192 to value 3.
    Write Dword    ${M7_PAYLOAD}       18
    Write Dword    ${M7_RESPONSE1}     0xFFFFFFFF
    Write Dword    0x44611024          4
    Write Dword    0x44611028          192
    Write Dword    0x4461102C          3
    Call M7        0x00006406
    ${set_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    # Read one config type 192 back.
    Write Dword    ${M7_PAYLOAD}       18
    Write Dword    ${M7_RESPONSE1}     192
    Call M7        0x00006405
    ${get_status}=    Read Dword    ${M7_PAYLOAD}
    ${num_configs}=   Read Dword    0x44611024
    ${config_type}=   Read Dword    0x44611028
    ${config_value}=  Read Dword    0x4461102C
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${num_configs}   1
    Should Be Equal As Numbers    ${config_type}   192
    Should Be Equal As Numbers    ${config_value}  3

    # AP-NS may discover pin 18 but must not mutate it.
    Write Dword    ${AP_NS_PAYLOAD}      18
    Write Dword    ${AP_NS_RESPONSE1}    0xFFFFFFFF
    Write Dword    0x445B1124            4
    Write Dword    0x445B1128            192
    Write Dword    0x445B112C            7
    Call AP NS     0x00006406
    ${denied}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${denied}    0xFFFFFFFD

AP Nonsecure Pin Configuration Is Stateful
    Create Full Candidate
    # AP-NS owns pin 20.
    Write Dword    ${AP_NS_PAYLOAD}      20
    Write Dword    ${AP_NS_RESPONSE1}    0xFFFFFFFF
    Write Dword    0x445B1124            4
    Write Dword    0x445B1128            193
    Write Dword    0x445B112C            0x55AA
    Call AP NS     0x00006406
    ${set_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${AP_NS_PAYLOAD}      20
    Write Dword    ${AP_NS_RESPONSE1}    193
    Call AP NS     0x00006405
    ${get_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${num_configs}=   Read Dword    0x445B1124
    ${config_type}=   Read Dword    0x445B1128
    ${config_value}=  Read Dword    0x445B112C
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${num_configs}   1
    Should Be Equal As Numbers    ${config_type}   193
    Should Be Equal As Numbers    ${config_value}  0x55AA

Daisy Permissions Are Independent From Pin Permissions
    Create Full Candidate
    # M7 owns daisy 0. Configure it through pin 18 using DAISY_ID + DAISY_CFG.
    Write Dword    ${M7_PAYLOAD}       18
    Write Dword    ${M7_RESPONSE1}     0xFFFFFFFF
    Write Dword    0x44611024          8
    Write Dword    0x44611028          194
    Write Dword    0x4461102C          0
    Write Dword    0x44611030          195
    Write Dword    0x44611034          2
    Call M7        0x00006406
    ${m7_daisy_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${m7_daisy_status}    0

    # AP-NS owns pin 20 but not daisy 0, so the same daisy mutation is denied.
    Write Dword    ${AP_NS_PAYLOAD}      20
    Write Dword    ${AP_NS_RESPONSE1}    0xFFFFFFFF
    Write Dword    0x445B1124            8
    Write Dword    0x445B1128            194
    Write Dword    0x445B112C            0
    Write Dword    0x445B1130            195
    Write Dword    0x445B1134            2
    Call AP NS     0x00006406
    ${apns_denied}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${apns_denied}    0xFFFFFFFD

    # AP-NS owns daisy 17 (CAN2_RX).
    Write Dword    ${AP_NS_PAYLOAD}      20
    Write Dword    ${AP_NS_RESPONSE1}    0xFFFFFFFF
    Write Dword    0x445B1124            8
    Write Dword    0x445B1128            194
    Write Dword    0x445B112C            17
    Write Dword    0x445B1130            195
    Write Dword    0x445B1134            1
    Call AP NS     0x00006406
    ${apns_allowed}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${apns_allowed}    0

Read Only Pin Attributes Remain Globally Addressable
    Create Full Candidate
    # AP-S can discover a valid pin even though it has no mutation permission.
    Write Dword    ${AP_S_PAYLOAD}      18
    Write Dword    ${AP_S_RESPONSE1}    0
    Call AP S      0x00006403
    ${status}=     Read Dword    ${AP_S_PAYLOAD}
    ${attrs}=      Read Dword    ${AP_S_RESPONSE1}
    ${name0}=      Read Dword    0x445B1024
    Should Be Equal As Numbers    ${status}    0
    Should Be Equal As Numbers    ${attrs}     1
    Should Be Equal As Numbers    ${name0}     0x4F495047

Invalid Pin Is Rejected
    Create Full Candidate
    Write Dword    ${AP_NS_PAYLOAD}      140
    Write Dword    ${AP_NS_RESPONSE1}    0
    Call AP NS     0x00006407
    ${status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${status}    0xFFFFFFFC
