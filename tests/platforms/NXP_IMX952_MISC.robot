*** Settings ***
Documentation     Validate source-derived i.MX952 NXP MISC first-slice behavior and qualification boundaries.
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

*** Test Cases ***
MISC Is Advertised Only To AP Nonsecure In First Slice
    Create Full Candidate
    # AP-NS has 9 non-base protocols after adding MISC.
    Call AP NS    0x00004001
    ${ap_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${ap_attrs}=     Read Dword    ${AP_NS_RESPONSE1}
    Should Be Equal As Numbers    ${ap_status}    0
    Should Be Equal As Numbers    ${ap_attrs}     0x00000309

    # M7 keeps its prior 9 non-base protocols; first-slice MISC is not advertised.
    Call M7    0x00004001
    ${m7_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_attrs}=     Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${m7_status}    0
    Should Be Equal As Numbers    ${m7_attrs}     0x00000309

    # Direct M7 use is denied.
    Call M7    0x00021000
    ${m7_misc_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${m7_misc_status}    0xFFFFFFFD

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

AP Nonsecure COMBO PHY Control Is Stateful And Permission Restricted
    Create Full Candidate
    # Control 9=COMBO_PHY, one value word.
    Write Dword    ${AP_NS_PAYLOAD}      9
    Write Dword    ${AP_NS_RESPONSE1}    1
    Write Dword    0x445B1124            0x12345678
    Call AP NS     0x00021003
    ${set_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${AP_NS_PAYLOAD}    9
    Call AP NS     0x00021004
    ${get_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${num_val}=       Read Dword    ${AP_NS_RESPONSE1}
    ${value}=         Read Dword    0x445B1124
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${num_val}       1
    Should Be Equal As Numbers    ${value}         0x12345678

    # Control 8 is not part of this qualified AP-NS MISC slice.
    Write Dword    ${AP_NS_PAYLOAD}    8
    Call AP NS     0x00021004
    ${denied}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${denied}    0xFFFFFFFD

Safe Target Metadata Does Not Fabricate Physical Fuse Values
    Create Full Candidate
    # Silicon info: numeric physical/fuse fields remain zero; text identifies target baseline.
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

    # Config basename starts with "mx95".
    Call AP NS    0x0002100C
    ${cfg_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${m_sel}=         Read Dword    ${AP_NS_RESPONSE1}
    ${cfg_name_0}=    Read Dword    0x445B1124
    Should Be Equal As Numbers    ${cfg_status}    0
    Should Be Equal As Numbers    ${m_sel}         0
    Should Be Equal As Numbers    ${cfg_name_0}    0x3539786D

    # Board name starts with "i.MX" and unmeasured attributes remain zero.
    Call AP NS    0x0002100E
    ${brd_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${brd_attrs}=     Read Dword    ${AP_NS_RESPONSE1}
    ${brd_name_0}=    Read Dword    0x445B1124
    Should Be Equal As Numbers    ${brd_status}    0
    Should Be Equal As Numbers    ${brd_attrs}     0
    Should Be Equal As Numbers    ${brd_name_0}    0x584D2E69

Reset Reason And DDR Region Are Deterministic Model Evidence
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
    ${start_high}=    Read Dword    0x445B112C
    ${end_low}=       Read Dword    0x445B1130
    ${end_high}=      Read Dword    0x445B1134
    Should Be Equal As Numbers    ${ddr_status}    0
    Should Be Equal As Numbers    ${ddr_attrs}     0x00010200
    Should Be Equal As Numbers    ${mts}           0
    Should Be Equal As Numbers    ${start_low}     0x80000000
    Should Be Equal As Numbers    ${start_high}    0
    Should Be Equal As Numbers    ${end_low}       0xFFFFFFFF
    Should Be Equal As Numbers    ${end_high}      0

Unavailable ROM Passover Is Explicitly Not Supported
    Create Full Candidate
    Call AP NS    0x00021007
    ${status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${status}    0xFFFFFFFF
