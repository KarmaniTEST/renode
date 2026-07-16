*** Settings ***
Documentation     Validate source-derived i.MX952 BBM RTC/button normal P2A notifications and queue ordering.
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
${AP_S_NOTIFY_STATUS}    0x445B1104
${AP_NS_NOTIFY_STATUS}   0x445B1184
${AP_NS_NOTIFY_LENGTH}   0x445B1194
${AP_NS_NOTIFY_HEADER}   0x445B1198
${AP_NS_NOTIFY_PAYLOAD}  0x445B119C
${AP_RTC_TRIGGER}        0x445B01E8
${AP_BUTTON_TRIGGER}     0x445B01EC

${M7_GCR}                0x44610114
${M7_GSR}                0x44610118
${M7_HEADER}             0x44611018
${M7_PAYLOAD}            0x4461101C
${M7_RESPONSE1}          0x44611020
${M7_NOTIFY_STATUS}      0x44611084
${M7_NOTIFY_LENGTH}      0x44611094
${M7_NOTIFY_HEADER}      0x44611098
${M7_NOTIFY_PAYLOAD}     0x4461109C
${M7_RTC_TRIGGER}        0x446101E8
${M7_BUTTON_TRIGGER}     0x446101EC

*** Keywords ***
Create Full Candidate
    Execute Command    mach create "imx952-bbm-notifications"
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

Subscribe M7 RTC
    [Arguments]    ${rtc_id}    ${flags}
    Write Dword    ${M7_PAYLOAD}      ${rtc_id}
    Write Dword    ${M7_RESPONSE1}    ${flags}
    Call M7        0x0002040A
    ${status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${status}    0

Subscribe AP NS RTC
    [Arguments]    ${rtc_id}    ${flags}
    Write Dword    ${AP_NS_PAYLOAD}      ${rtc_id}
    Write Dword    ${AP_NS_RESPONSE1}    ${flags}
    Call AP NS     0x0002040A
    ${status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${status}    0

*** Test Cases ***
M7 RTC Notification Requires Matching Subscription
    Create Full Candidate
    # Subscribe only to RTC1 update events (bit 2).
    Subscribe M7 RTC    1    4

    # Alarm event is filtered. GSR bit 0 remains from the A2P subscription response.
    Write Dword    ${M7_RTC_TRIGGER}    1
    ${filtered_status}=    Read Dword    ${M7_NOTIFY_STATUS}
    ${filtered_gsr}=       Read Dword    ${M7_GSR}
    Should Be Equal As Numbers    ${filtered_status}    1
    Should Be Equal As Numbers    ${filtered_gsr}       1

    # RTC1 update event is delivered on M7 normal P2A channel 1.
    Write Dword    ${M7_RTC_TRIGGER}    0x201
    ${status}=     Read Dword    ${M7_NOTIFY_STATUS}
    ${length}=     Read Dword    ${M7_NOTIFY_LENGTH}
    ${header}=     Read Dword    ${M7_NOTIFY_HEADER}
    ${payload}=    Read Dword    ${M7_NOTIFY_PAYLOAD}
    ${gsr}=        Read Dword    ${M7_GSR}
    Should Be Equal As Numbers    ${status}     0
    Should Be Equal As Numbers    ${length}     8
    Should Be Equal As Numbers    ${header}     0x00020700
    Should Be Equal As Numbers    ${payload}    0x01000004
    Should Be Equal As Numbers    ${gsr}        3

AP Nonsecure RTC Notification Uses Its Normal P2A Channel
    Create Full Candidate
    Subscribe AP NS RTC    0    1

    # RTC0 alarm event (event selector 0) is represented by a zero trigger value.
    Write Dword    ${AP_RTC_TRIGGER}    0
    ${ap_s_status}=    Read Dword    ${AP_S_NOTIFY_STATUS}
    ${status}=         Read Dword    ${AP_NS_NOTIFY_STATUS}
    ${length}=         Read Dword    ${AP_NS_NOTIFY_LENGTH}
    ${header}=         Read Dword    ${AP_NS_NOTIFY_HEADER}
    ${payload}=        Read Dword    ${AP_NS_NOTIFY_PAYLOAD}
    ${gsr}=            Read Dword    ${AP_GSR}
    Should Be Equal As Numbers    ${ap_s_status}    1
    Should Be Equal As Numbers    ${status}         0
    Should Be Equal As Numbers    ${length}         8
    Should Be Equal As Numbers    ${header}         0x00020700
    Should Be Equal As Numbers    ${payload}        0x00000001
    Should Be Equal As Numbers    ${gsr}            12

M7 Button Detection Notification Uses BBM Message One
    Create Full Candidate
    Write Dword    ${M7_PAYLOAD}    1
    Call M7        0x0002040B
    ${subscribe_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${subscribe_status}    0

    Write Dword    ${M7_BUTTON_TRIGGER}    1
    ${status}=     Read Dword    ${M7_NOTIFY_STATUS}
    ${header}=     Read Dword    ${M7_NOTIFY_HEADER}
    ${payload}=    Read Dword    ${M7_NOTIFY_PAYLOAD}
    Should Be Equal As Numbers    ${status}     0
    Should Be Equal As Numbers    ${header}     0x00020701
    Should Be Equal As Numbers    ${payload}    1

BBM Normal Notification Queue Preserves RTC Event Order
    Create Full Candidate
    Subscribe M7 RTC    1    7

    # First event occupies the channel; second event remains queued.
    Write Dword    ${M7_RTC_TRIGGER}    1
    Write Dword    ${M7_RTC_TRIGGER}    0x101
    ${first_header}=     Read Dword    ${M7_NOTIFY_HEADER}
    ${first_payload}=    Read Dword    ${M7_NOTIFY_PAYLOAD}
    Should Be Equal As Numbers    ${first_header}     0x00020700
    Should Be Equal As Numbers    ${first_payload}    0x01000001

    # Agent releases channel 1; queued rollover event is dispatched immediately.
    Write Dword    ${M7_NOTIFY_STATUS}    1
    ${second_status}=     Read Dword    ${M7_NOTIFY_STATUS}
    ${second_header}=     Read Dword    ${M7_NOTIFY_HEADER}
    ${second_payload}=    Read Dword    ${M7_NOTIFY_PAYLOAD}
    Should Be Equal As Numbers    ${second_status}     0
    Should Be Equal As Numbers    ${second_header}     0x00060700
    Should Be Equal As Numbers    ${second_payload}    0x01000002

Disabling BBM Subscription Suppresses Later Events
    Create Full Candidate
    Subscribe M7 RTC    0    1
    Subscribe M7 RTC    0    0

    Write Dword    ${M7_RTC_TRIGGER}    0
    ${status}=    Read Dword    ${M7_NOTIFY_STATUS}
    ${gsr}=       Read Dword    ${M7_GSR}
    Should Be Equal As Numbers    ${status}    1
    Should Be Equal As Numbers    ${gsr}       1
