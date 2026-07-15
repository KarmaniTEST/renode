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
AP Secure And Nonsecure Agents Expose Source Derived Protocols
    Create Full Candidate
    # Base PROTOCOL_ATTRIBUTES: 3 agents, 5 non-base protocols on AP-S.
    Call AP S    0x00004001
    ${ap_s_status}=    Read Dword    ${AP_S_PAYLOAD}
    ${ap_s_attrs}=     Read Dword    0x445B1020
    Should Be Equal As Numbers    ${ap_s_status}    0
    Should Be Equal As Numbers    ${ap_s_attrs}     0x00000305

    # AP-NS additionally advertises Sensor and NXP LMM because its generated
    # policy grants readable A55 sensor access and LMM notification permission.
    Call AP NS    0x00004001
    ${ap_ns_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${ap_ns_attrs}=     Read Dword    0x445B10A0
    Should Be Equal As Numbers    ${ap_ns_status}    0
    Should Be Equal As Numbers    ${ap_ns_attrs}     0x00000307

System Power Performance Sensor And LMM Versions Match NXP Sources
    Create Full Candidate
    Call AP NS    0x00004800
    ${sys_status}=     Read Dword    ${AP_NS_PAYLOAD}
    ${sys_version}=    Read Dword    0x445B10A0
    Should Be Equal As Numbers    ${sys_status}     0
    Should Be Equal As Numbers    ${sys_version}    0x00020001

    Call AP NS    0x00004C00
    ${perf_status}=     Read Dword    ${AP_NS_PAYLOAD}
    ${perf_version}=    Read Dword    0x445B10A0
    Should Be Equal As Numbers    ${perf_status}     0
    Should Be Equal As Numbers    ${perf_version}    0x00040000

    Call AP NS    0x00005400
    ${sensor_status}=     Read Dword    ${AP_NS_PAYLOAD}
    ${sensor_version}=    Read Dword    0x445B10A0
    Should Be Equal As Numbers    ${sensor_status}     0
    Should Be Equal As Numbers    ${sensor_version}    0x00030001

    # NXP LMM protocol 0x80 / PROTOCOL_VERSION.
    Call AP NS    0x00020000
    ${lmm_status}=     Read Dword    ${AP_NS_PAYLOAD}
    ${lmm_version}=    Read Dword    0x445B10A0
    Should Be Equal As Numbers    ${lmm_status}     0
    Should Be Equal As Numbers    ${lmm_version}    0x00010001

AP Secure And Nonsecure Performance Permissions Are Different
    Create Full Candidate
    Write Dword    ${AP_S_PAYLOAD}    7
    Call AP S      0x00004C08
    ${ap_s_a55_status}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${ap_s_a55_status}    0

    Write Dword    ${AP_S_PAYLOAD}    8
    Call AP S      0x00004C08
    ${ap_s_gpu_status}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${ap_s_gpu_status}    0xFFFFFFFD

    Write Dword    ${AP_NS_PAYLOAD}    8
    Call AP NS      0x00004C08
    ${ap_ns_gpu_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${ap_ns_gpu_status}    0

AP Secure And Nonsecure Power Permissions Are Different
    Create Full Candidate
    Write Dword    ${AP_S_PAYLOAD}    9
    Call AP S      0x00004405
    ${ap_s_a55_status}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${ap_s_a55_status}    0

    Write Dword    ${AP_S_PAYLOAD}    13
    Call AP S      0x00004405
    ${ap_s_hsio_status}=    Read Dword    ${AP_S_PAYLOAD}
    Should Be Equal As Numbers    ${ap_s_hsio_status}    0xFFFFFFFD

    Write Dword    ${AP_NS_PAYLOAD}    13
    Call AP NS      0x00004405
    ${ap_ns_hsio_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${ap_ns_hsio_status}    0

AP Nonsecure Sensor Access Is Restricted To A55 Temperature
    Create Full Candidate
    Write Dword    ${AP_NS_PAYLOAD}    1
    Call AP NS     0x00005406
    ${a55_sensor_status}=    Read Dword    ${AP_NS_PAYLOAD}
    ${a55_sensor_value}=     Read Dword    0x445B10A0
    Should Be Equal As Numbers    ${a55_sensor_status}    0
    Should Be Equal As Numbers    ${a55_sensor_value}     50000

    Write Dword    ${AP_NS_PAYLOAD}    0
    Call AP NS     0x00005406
    ${ana_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${ana_status}    0xFFFFFFFD

AP Nonsecure LMM Permission Is Notification Only
    Create Full Candidate
    # AP-NS may configure notifications for M7 logical machine 1.
    Write Dword    ${AP_NS_PAYLOAD}        1
    Write Dword    0x445B10A0             0x0000000F
    Call AP NS     0x00020009
    ${notify_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${notify_status}    0

    # The same AP-NS agent must not boot/reset/control LM1 or LM2.
    Write Dword    ${AP_NS_PAYLOAD}    1
    Call AP NS     0x00020004
    ${boot_lm1_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${boot_lm1_status}    0xFFFFFFFD

    Write Dword    ${AP_NS_PAYLOAD}    2
    Call AP NS     0x00020005
    ${reset_lm2_status}=    Read Dword    ${AP_NS_PAYLOAD}
    Should Be Equal As Numbers    ${reset_lm2_status}    0xFFFFFFFD

M7 Agent Controls AP Logical Machine Through LMM
    Create Full Candidate
    # M7 agent has full LMM permission for AP logical machine 2.
    Write Dword    ${M7_PAYLOAD}    2
    Call M7 Agent    0x00020003
    ${attrs_status}=    Read Dword    ${M7_PAYLOAD}
    ${returned_lm}=     Read Dword    0x44611020
    ${initial_state}=   Read Dword    0x44611028
    Should Be Equal As Numbers    ${attrs_status}    0
    Should Be Equal As Numbers    ${returned_lm}     2
    Should Be Equal As Numbers    ${initial_state}   1

    # Shutdown LM2 and verify OFF state.
    Write Dword    ${M7_PAYLOAD}    2
    Write Dword    0x44611020       0
    Call M7 Agent    0x00020006
    ${shutdown_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${shutdown_status}    0

    Write Dword    ${M7_PAYLOAD}    2
    Call M7 Agent    0x00020003
    ${off_state}=    Read Dword    0x44611028
    Should Be Equal As Numbers    ${off_state}    0

    # Boot LM2 and verify ON state again.
    Write Dword    ${M7_PAYLOAD}    2
    Call M7 Agent    0x00020004
    ${boot_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${boot_status}    0

    Write Dword    ${M7_PAYLOAD}    2
    Call M7 Agent    0x00020003
    ${on_state}=    Read Dword    0x44611028
    Should Be Equal As Numbers    ${on_state}    1

M7 Agent Has Independent Performance And Sensor Permissions
    Create Full Candidate
    Write Dword    ${M7_PAYLOAD}    2
    Call M7 Agent    0x00004C08
    ${m7_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_level}=     Read Dword    0x44611020
    Should Be Equal As Numbers    ${m7_status}    0
    Should Be Equal As Numbers    ${m7_level}     2

    Write Dword    ${M7_PAYLOAD}    0
    Call M7 Agent    0x00005406
    ${m7_sensor_status}=    Read Dword    ${M7_PAYLOAD}
    ${m7_sensor_value}=     Read Dword    0x44611020
    Should Be Equal As Numbers    ${m7_sensor_status}    0
    Should Be Equal As Numbers    ${m7_sensor_value}     45000

    Write Dword    ${M7_PAYLOAD}    1
    Call M7 Agent    0x00005406
    ${m7_a55_status}=    Read Dword    ${M7_PAYLOAD}
    Should Be Equal As Numbers    ${m7_a55_status}    0xFFFFFFFD
