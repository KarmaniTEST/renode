*** Settings ***
Documentation     Validate the source-derived M7 FuSa first slice and queued priority notification delivery on SMT channel 2.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}              ${CURDIR}/../../platforms/boards/nxp_imx952_evk_full.repl
${AP_GCR}                0x445B0114
${AP_S_HEADER}           0x445B1018
${AP_S_PAYLOAD}          0x445B101C
${AP_S_RESPONSE1}        0x445B1020
${M7_GCR}                0x44610114
${M7_GSR}                0x44610118
${M7_HEADER}             0x44611018
${M7_PAYLOAD}            0x4461101C
${M7_RESPONSE1}          0x44611020
${M7_RESPONSE2}          0x44611024
${M7_RESPONSE3}          0x44611028
${M7_PRIORITY_STATUS}    0x44611104
${M7_PRIORITY_LENGTH}    0x44611114
${M7_PRIORITY_HEADER}    0x44611118
${M7_PRIORITY_PAYLOAD0}  0x4461111C
${M7_PRIORITY_PAYLOAD1}  0x44611120
${M7_FUSA_TRIGGER}       0x446101E4

*** Keywords ***
Create Full Candidate
    Execute Command    mach create "imx952-fusa-priority"
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

Call AP S
    [Arguments]    ${header}
    Write Dword    ${AP_S_HEADER}    ${header}
    Write Dword    ${AP_GCR}         1

GSR Priority Bit Should Be
    [Arguments]    ${expected}
    ${gsr}=    Read Dword    ${M7_GSR}
    ${priority}=    Evaluate    int('${gsr}', 0) & 0x4
    Should Be Equal As Numbers    ${priority}    ${expected}

*** Test Cases ***
M7 Base Discovery Advertises FuSa And AP Secure Does Not
    Create Full Candidate
    Call M7    0x00004001
    ${m7_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_attrs}=     Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${m7_status}    0
    Should Be Equal As Numbers    ${m7_attrs}     0x30B

    Write Dword    ${M7_PAYLOAD}    0
    Call M7        0x00004006
    ${list_status}=    Read Dword    ${M7_PAYLOAD}
    ${list_count}=     Read Dword    ${M7_RESPONSE1}
    ${list_word0}=     Read Dword    ${M7_RESPONSE2}
    ${list_word1}=     Read Dword    ${M7_RESPONSE3}
    ${list_word2}=     Read Dword    0x4461102C
    Should Be Equal As Numbers    ${list_status}    0
    Should Be Equal As Numbers    ${list_count}     11
    Should Be Equal As Numbers    ${list_word0}     0x14131211
    Should Be Equal As Numbers    ${list_word1}     0x82801915
    Should Be Equal As Numbers    ${list_word2}     0x00838481

    Call AP S    0x00004001
    ${aps_status}=    Read Dword    ${AP_S_PAYLOAD}
    ${aps_attrs}=     Read Dword    ${AP_S_RESPONSE1}
    Should Be Equal As Numbers    ${aps_status}    0
    Should Be Equal As Numbers    ${aps_attrs}     0x305

    Call AP S    0x00020C00
    ${aps_fusa}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${aps_fusa}    0xFFFFFFFF

FuSa Version Attributes And Message Inventory Match Pinned Source
    Create Full Candidate
    Call M7    0x00020C00
    ${version_status}=    Read Dword    ${M7_PAYLOAD}
    ${version}=           Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${version_status}    0
    Should Be Equal As Numbers    ${version}           0x00010000

    Call M7    0x00020C01
    ${attrs_status}=    Read Dword    ${M7_PAYLOAD}
    ${attrs1}=         Read Dword    ${M7_RESPONSE1}
    ${attrs2}=         Read Dword    ${M7_RESPONSE2}
    Should Be Equal As Numbers    ${attrs_status}    0
    Should Be Equal As Numbers    ${attrs1}         0x00590101
    Should Be Equal As Numbers    ${attrs2}         0

    Write Dword    ${M7_PAYLOAD}    8
    Call M7        0x00020C02
    ${supported}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${supported}    0

    Write Dword    ${M7_PAYLOAD}    0x0B
    Call M7        0x00020C02
    ${not_supported}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${not_supported}    0xFFFFFFFC

FuSa F EENV State Notification Uses Queued Priority Channel
    Create Full Candidate
    # Default F-EENV state is PRE_SAFETY with MSEL zero.
    Call M7    0x00020C03
    ${get_status}=    Read Dword    ${M7_PAYLOAD}
    ${initial_state}=    Read Dword    ${M7_RESPONSE1}
    ${initial_msel}=     Read Dword    ${M7_RESPONSE2}
    Should Be Equal As Numbers    ${get_status}       0
    Should Be Equal As Numbers    ${initial_state}    1
    Should Be Equal As Numbers    ${initial_msel}     0

    # Subscribe and inject state=SAFETY_RUNTIME(2), MSEL=7.
    Write Dword    ${M7_PAYLOAD}    1
    Call M7        0x00020C05
    ${notify_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${notify_status}    0

    Write Dword    ${M7_FUSA_TRIGGER}    0x0702
    ${priority_status}=    Read Dword    ${M7_PRIORITY_STATUS}
    ${priority_length}=    Read Dword    ${M7_PRIORITY_LENGTH}
    ${priority_header}=    Read Dword    ${M7_PRIORITY_HEADER}
    ${priority_state}=     Read Dword    ${M7_PRIORITY_PAYLOAD0}
    ${priority_msel}=      Read Dword    ${M7_PRIORITY_PAYLOAD1}
    Should Be Equal As Numbers    ${priority_status}    0
    Should Be Equal As Numbers    ${priority_length}    12
    Should Be Equal As Numbers    ${priority_header}    0x00020F00
    Should Be Equal As Numbers    ${priority_state}     2
    Should Be Equal As Numbers    ${priority_msel}      7
    GSR Priority Bit Should Be    4

    # A second event is queued while channel 2 is busy and must not overwrite it.
    Write Dword    ${M7_FUSA_TRIGGER}    0x0803
    ${still_first_state}=    Read Dword    ${M7_PRIORITY_PAYLOAD0}
    ${still_first_msel}=     Read Dword    ${M7_PRIORITY_PAYLOAD1}
    Should Be Equal As Numbers    ${still_first_state}    2
    Should Be Equal As Numbers    ${still_first_msel}     7

    # Agent acknowledges the first doorbell and frees channel 2; queued event dispatches.
    Write Dword    ${M7_GSR}                4
    Write Dword    ${M7_PRIORITY_STATUS}    1
    ${second_status}=    Read Dword    ${M7_PRIORITY_STATUS}
    ${second_header}=    Read Dword    ${M7_PRIORITY_HEADER}
    ${second_state}=     Read Dword    ${M7_PRIORITY_PAYLOAD0}
    ${second_msel}=      Read Dword    ${M7_PRIORITY_PAYLOAD1}
    Should Be Equal As Numbers    ${second_status}    0
    Should Be Equal As Numbers    ${second_header}    0x00060F00
    Should Be Equal As Numbers    ${second_state}     3
    Should Be Equal As Numbers    ${second_msel}      8
    GSR Priority Bit Should Be    4

Disabled FuSa Subscription Suppresses Priority Delivery But Updates State
    Create Full Candidate
    Write Dword    ${M7_PAYLOAD}    0
    Call M7        0x00020C05
    ${disable_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${disable_status}    0

    Write Dword    ${M7_GSR}             0xFFFFFFFF
    Write Dword    ${M7_FUSA_TRIGGER}    0x0901
    GSR Priority Bit Should Be    0

    Call M7    0x00020C03
    ${get_status}=    Read Dword    ${M7_PAYLOAD}
    ${state}=         Read Dword    ${M7_RESPONSE1}
    ${msel}=          Read Dword    ${M7_RESPONSE2}
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${state}         1
    Should Be Equal As Numbers    ${msel}          9

FuSa S EENV State Is Stateful And Validated
    Create Full Candidate
    Write Dword    ${M7_PAYLOAD}    0xFFFFFFFF
    Call M7        0x00020C06
    ${get_status}=    Read Dword    ${M7_PAYLOAD}
    ${seenv_id}=      Read Dword    ${M7_RESPONSE1}
    ${lm_id}=         Read Dword    ${M7_RESPONSE2}
    ${state}=         Read Dword    ${M7_RESPONSE3}
    Should Be Equal As Numbers    ${get_status}    0
    Should Be Equal As Numbers    ${seenv_id}      0
    Should Be Equal As Numbers    ${lm_id}         1
    Should Be Equal As Numbers    ${state}         1

    Write Dword    ${M7_PAYLOAD}      3
    Write Dword    ${M7_RESPONSE1}    0x12345678
    Call M7        0x00020C07
    ${set_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${set_status}    0

    Write Dword    ${M7_PAYLOAD}    0
    Call M7        0x00020C06
    ${new_state}=    Read Dword    ${M7_RESPONSE3}
    Should Be Equal As Numbers    ${new_state}    3

    Write Dword    ${M7_PAYLOAD}      5
    Write Dword    ${M7_RESPONSE1}    0
    Call M7        0x00020C07
    ${invalid}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${invalid}    0xFFFFFFFE
