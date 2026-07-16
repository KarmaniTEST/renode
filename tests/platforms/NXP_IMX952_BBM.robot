*** Settings ***
Documentation     Validate source-derived i.MX952 NXP BBM resources and permissions. Notification delivery is qualified separately in NXP_IMX952_BBM_NOTIFICATIONS.robot.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}          ${CURDIR}/../../platforms/boards/nxp_imx952_evk_full.repl
${AP_GCR}            0x445B0114
${AP_NS_HEADER}      0x445B1118
${AP_NS_PAYLOAD}     0x445B111C
${AP_NS_RESPONSE1}   0x445B1120
${M7_GCR}            0x44610114
${M7_HEADER}         0x44611018
${M7_PAYLOAD}        0x4461101C
${M7_RESPONSE1}      0x44611020

*** Keywords ***
Create Full Candidate
    Execute Command    mach create "imx952-bbm"
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

*** Test Cases ***
BBM Is Advertised Only To Agents With Source Permissions
    Create Full Candidate
    # AP-NS has nine non-base protocols after BBM and MISC are layered.
    Call AP NS    0x00004001
    ${ap_ns_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${ap_ns_attrs}=     Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${ap_ns_status}    0
    Should Be Equal As Numbers    ${ap_ns_attrs}     0x00000309

    # M7 has eleven non-base protocols after BBM, MISC and FuSa are layered.
    Call M7    0x00004001
    ${m7_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_attrs}=     Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${m7_status}    0
    Should Be Equal As Numbers    ${m7_attrs}     0x0000030B

BBM Version And Resource Counts Match Pinned Contract
    Create Full Candidate
    Call AP NS    0x00020400
    ${version_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${version}=           Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${version_status}    0
    Should Be Equal As Numbers    ${version}           0x00010000

    Call AP NS    0x00020401
    ${attr_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${attrs}=          Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${attr_status}    0
    Should Be Equal As Numbers    ${attrs}          0x00020008

AP Nonsecure Can Access Only GPR4 Through GPR7
    Create Full Candidate
    Write Dword    ${AP_NS_PAYLOAD}     4
    Write Dword    ${AP_NS_RESPONSE1}   0xA5A55A5A
    Call AP NS     0x00020403
    ${set_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${AP_NS_PAYLOAD}    4
    Call AP NS     0x00020404
    ${get_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${gpr4}=          Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${gpr4}          0xA5A55A5A

    Write Dword    ${AP_NS_PAYLOAD}    3
    Call AP NS     0x00020404
    ${gpr3_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${gpr3_status}    0xFFFFFFFD

M7 Has RTC And Button Rights But No GPR Rights
    Create Full Candidate
    Write Dword    ${M7_PAYLOAD}    4
    Call M7        0x00020404
    ${gpr_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${gpr_status}    0xFFFFFFFD

    Call M7    0x00020409
    ${button_status}=    Read Dword    ${M7_PAYLOAD}
    ${button_state}=     Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${button_status}    0
    Should Be Equal As Numbers    ${button_state}     0

AP Nonsecure BBNSM RTC Time Is Deterministically Stateful
    Create Full Candidate
    Write Dword    ${AP_NS_PAYLOAD}      0
    Write Dword    ${AP_NS_RESPONSE1}    0
    Write Dword    0x445B1124            0x23456789
    Write Dword    0x445B1128            0x00000001
    Call AP NS     0x00020406
    ${set_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${AP_NS_PAYLOAD}      0
    Write Dword    ${AP_NS_RESPONSE1}    0
    Call AP NS     0x00020407
    ${get_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${time_low}=      Read Dword    ${AP_NS_RESPONSE1}
    ${time_high}=     Read Dword    0x445B1124
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${time_low}      0x23456789
    Should Be Equal As Numbers    ${time_high}     0x00000001

M7 Can Access EVK PCA2131 RTC Through Its ALL Permission
    Create Full Candidate
    Write Dword    ${M7_PAYLOAD}       1
    Write Dword    ${M7_RESPONSE1}     0
    Write Dword    0x44611024          123456
    Write Dword    0x44611028          0
    Call M7        0x00020406
    ${set_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${M7_PAYLOAD}       1
    Write Dword    ${M7_RESPONSE1}     0
    Call M7        0x00020407
    ${get_status}=    Read Dword    ${M7_PAYLOAD}
    ${time_low}=      Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${time_low}      123456
