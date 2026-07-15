*** Settings ***
Documentation     Validate source-derived i.MX952 System Manager agent and protocol behavior.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}       ${CURDIR}/../../platforms/boards/nxp_imx952_evk_full.repl
${AP_GCR}         0x445B0114
${AP_S_HEADER}    0x445B1018
${AP_S_PAYLOAD}   0x445B101C
${AP_NS_HEADER}   0x445B1098
${AP_NS_PAYLOAD}  0x445B109C
${M7_GCR}         0x44610114
${M7_HEADER}      0x44611018
${M7_PAYLOAD}     0x4461101C

*** Keywords ***
Create Full Candidate
    Execute Command    mach create "imx952-full"
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
    Write Dword    ${AP_GCR}          2

Call M7 Agent
    [Arguments]    ${header}
    Write Dword    ${M7_HEADER}    ${header}
    Write Dword    ${M7_GCR}       1

*** Test Cases ***
AP Secure And Nonsecure Agents Expose Source Derived Core Protocols
    Create Full Candidate
    # Base PROTOCOL_ATTRIBUTES: 3 agents, 5 non-base protocols on AP-S.
    Call AP S    0x00004001
    ${ap_s_status}=    Read Dword    ${AP_S_PAYLOAD}
    ${ap_s_attrs}=     Read Dword    0x445B1020
    Should Be Equal As Numbers    ${ap_s_status}    0
    Should Be Equal As Numbers    ${ap_s_attrs}     0x00000305

    # AP-NS exposes the same implemented core protocol count on its independent channel.
    Call AP NS    0x00004001
    ${ap_ns_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${ap_ns_attrs}=     Read Dword    0x445B10A0
    Should Be Equal As Numbers    ${ap_ns_status}    0
    Should Be Equal As Numbers    ${ap_ns_attrs}     0x00000305

System Power And Performance Versions Match NXP System Manager Sources
    Create Full Candidate
    # System protocol 0x12 / PROTOCOL_VERSION.
    Call AP NS    0x00004800
    ${sys_status}=     Read Dword    ${AP_NS_PAYLOAD}
    ${sys_version}=    Read Dword    0x445B10A0
    Should Be Equal As Numbers    ${sys_status}     0
    Should Be Equal As Numbers    ${sys_version}    0x00020001

    # Performance protocol 0x13 / PROTOCOL_VERSION.
    Call AP NS    0x00004C00
    ${perf_status}=     Read Dword    ${AP_NS_PAYLOAD}
    ${perf_version}=    Read Dword    0x445B10A0
    Should Be Equal As Numbers    ${perf_status}     0
    Should Be Equal As Numbers    ${perf_version}    0x00040000

AP Secure And Nonsecure Performance Permissions Are Different
    Create Full Candidate
    # AP-S can access A55 performance domain 7.
    Write Dword    ${AP_S_PAYLOAD}    7
    Call AP S      0x00004C08
    ${ap_s_a55_status}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${ap_s_a55_status}    0

    # AP-S must not access GPU performance domain 8.
    Write Dword    ${AP_S_PAYLOAD}    8
    Call AP S      0x00004C08
    ${ap_s_gpu_status}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${ap_s_gpu_status}    0xFFFFFFFD

    # AP-NS is granted GPU performance access by the generated mx952evk policy.
    Write Dword    ${AP_NS_PAYLOAD}    8
    Call AP NS      0x00004C08
    ${ap_ns_gpu_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${ap_ns_gpu_status}    0

AP Secure And Nonsecure Power Permissions Are Different
    Create Full Candidate
    # AP-S owns A55 platform power domain 9.
    Write Dword    ${AP_S_PAYLOAD}    9
    Call AP S      0x00004405
    ${ap_s_a55_status}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${ap_s_a55_status}    0

    # AP-S cannot access HSIO power domain 13.
    Write Dword    ${AP_S_PAYLOAD}    13
    Call AP S      0x00004405
    ${ap_s_hsio_status}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${ap_s_hsio_status}    0xFFFFFFFD

    # AP-NS is granted HSIO power access.
    Write Dword    ${AP_NS_PAYLOAD}    13
    Call AP NS      0x00004405
    ${ap_ns_hsio_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${ap_ns_hsio_status}    0

M7 Agent Has Independent Performance Permission
    Create Full Candidate
    # M7 agent can read M7 performance domain 2.
    Write Dword    ${M7_PAYLOAD}    2
    Call M7 Agent    0x00004C08
    ${m7_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_level}=     Read Dword    0x44611020
    Should Be Equal As Numbers    ${m7_status}    0
    Should Be Equal As Numbers    ${m7_level}     2
