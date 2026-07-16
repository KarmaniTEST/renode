*** Settings ***
Documentation     Validate source-bounded i.MX952 FuSa S-check commands without claiming physical SCST/SAF execution.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}                  ${CURDIR}/../../platforms/boards/nxp_imx952_evk_full.repl
${AP_GCR}                    0x445B0114
${AP_S_HEADER}               0x445B1018
${AP_S_PAYLOAD}              0x445B101C
${M7_GCR}                    0x44610114
${M7_HEADER}                 0x44611018
${M7_PAYLOAD}                0x4461101C
${M7_RESPONSE1}              0x44611020
${M7_PRIORITY_STATUS}        0x44611104
${M7_SCHECK_EVENT_COUNT}     0x44610200
${M7_SCHECK_LAST_TEST_ID}    0x44610204
${M7_SCHECK_TEST_COUNT}      0x44610208

*** Keywords ***
Create Full Candidate
    Execute Command    mach create "imx952-fusa-scheck"
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

*** Test Cases ***
Scheck Commands Are Advertised Through FuSa Message Attributes
    Create Full Candidate

    Write Dword    ${M7_PAYLOAD}    0x0B
    Call M7        0x00020C02
    ${event_attr}=    Read Dword    ${M7_PAYLOAD}
    ${event_flags}=   Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${event_attr}     0
    Should Be Equal As Numbers    ${event_flags}    0

    Write Dword    ${M7_PAYLOAD}    0x0E
    Call M7        0x00020C02
    ${test_attr}=    Read Dword    ${M7_PAYLOAD}
    ${test_flags}=   Read Dword    ${M7_RESPONSE1}
    Should Be Equal As Numbers    ${test_attr}     0
    Should Be Equal As Numbers    ${test_flags}    0

    # Message 0x0C remains absent from the pinned FuSa command inventory.
    Write Dword    ${M7_PAYLOAD}    0x0C
    Call M7        0x00020C02
    ${missing}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${missing}    0xFFFFFFFC

Scheck Event Trigger Is Accepted And Counted Without Fabricated Event
    Create Full Candidate
    ${initial}=    Read Dword    ${M7_SCHECK_EVENT_COUNT}
    ${priority_before}=    Read Dword    ${M7_PRIORITY_STATUS}
    Should Be Equal As Numbers    ${initial}            0
    Should Be Equal As Numbers    ${priority_before}    1

    Call M7    0x00020C0B
    ${first_status}=    Read Dword    ${M7_PAYLOAD}
    Call M7    0x00020C0B
    ${second_status}=    Read Dword    ${M7_PAYLOAD}
    ${count}=            Read Dword    ${M7_SCHECK_EVENT_COUNT}
    ${priority_after}=   Read Dword    ${M7_PRIORITY_STATUS}
    Should Be Equal As Numbers    ${first_status}      0
    Should Be Equal As Numbers    ${second_status}     0
    Should Be Equal As Numbers    ${count}             2
    Should Be Equal As Numbers    ${priority_after}    1

Scheck Test Execution Forwards Arbitrary Target Identifier At Pinned Boundary
    Create Full Candidate

    Write Dword    ${M7_PAYLOAD}    0x12345678
    Call M7        0x00020C0E
    ${first_status}=    Read Dword    ${M7_PAYLOAD}
    ${first_id}=        Read Dword    ${M7_SCHECK_LAST_TEST_ID}
    ${first_count}=     Read Dword    ${M7_SCHECK_TEST_COUNT}
    Should Be Equal As Numbers    ${first_status}    0
    Should Be Equal As Numbers    ${first_id}        0x12345678
    Should Be Equal As Numbers    ${first_count}     1

    # The pinned LMM backend performs no target range validation.
    Write Dword    ${M7_PAYLOAD}    0xFFFFFFFF
    Call M7        0x00020C0E
    ${second_status}=    Read Dword    ${M7_PAYLOAD}
    ${second_id}=        Read Dword    ${M7_SCHECK_LAST_TEST_ID}
    ${second_count}=     Read Dword    ${M7_SCHECK_TEST_COUNT}
    ${priority}=         Read Dword    ${M7_PRIORITY_STATUS}
    Should Be Equal As Numbers    ${second_status}    0
    Should Be Equal As Numbers    ${second_id}        0xFFFFFFFF
    Should Be Equal As Numbers    ${second_count}     2
    Should Be Equal As Numbers    ${priority}         1

AP Secure Cannot Invoke M7 Only Scheck Commands
    Create Full Candidate
    Call AP S    0x00020C0B
    ${event_status}=    Read Dword    ${AP_S_PAYLOAD}
    Call AP S    0x00020C0E
    ${test_status}=     Read Dword    ${AP_S_PAYLOAD}
    ${event_count}=     Read Dword    ${M7_SCHECK_EVENT_COUNT}
    ${test_count}=      Read Dword    ${M7_SCHECK_TEST_COUNT}
    Should Be Equal As Numbers    ${event_status}    0xFFFFFFFF
    Should Be Equal As Numbers    ${test_status}     0xFFFFFFFF
    Should Be Equal As Numbers    ${event_count}     0
    Should Be Equal As Numbers    ${test_count}      0
