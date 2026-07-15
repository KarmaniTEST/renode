*** Settings ***
Documentation     Validate the initial NXP i.MX 952 EVK 4x Cortex-A55 + Cortex-M7 platform with a deterministic shared-DDR handshake.
Suite Setup       Setup
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}       ${CURDIR}/../../platforms/boards/nxp_imx952_evk.repl
${A55_HEX}        ${CURDIR}/NXP_IMX952/a55_handshake.hex
${M7_HEX}         ${CURDIR}/NXP_IMX952/m7_handshake.hex
${MAGIC_ADDR}     0x88020000
${COMMAND_ADDR}   0x88020004
${STATUS_ADDR}    0x88020008
${RESULT_ADDR}    0x8802000C

*** Keywords ***
Create Test Machine
    Execute Command    mach create "imx952-evk-a55-m7-handshake"
    Execute Command    machine LoadPlatformDescription @${PLATFORM}

Verify Processor Topology
    ${a55_0}=    Execute Command    a55Cluster.a55_0 PC
    ${a55_1}=    Execute Command    a55Cluster.a55_1 PC
    ${a55_2}=    Execute Command    a55Cluster.a55_2 PC
    ${a55_3}=    Execute Command    a55Cluster.a55_3 PC
    ${m7}=       Execute Command    m7 PC
    Should Not Be Empty    ${a55_0}
    Should Not Be Empty    ${a55_1}
    Should Not Be Empty    ${a55_2}
    Should Not Be Empty    ${a55_3}
    Should Not Be Empty    ${m7}

Load Handshake Firmware
    Execute Command    sysbus LoadHEX @${A55_HEX}
    Execute Command    sysbus LoadHEX @${M7_HEX}
    Execute Command    a55Cluster.a55_0 PC 0x80000000
    Execute Command    m7 SP 0x20040000
    Execute Command    m7 PC 0x00000008

Read Dword
    [Arguments]    ${address}
    ${value}=    Execute Command    sysbus ReadDoubleWord ${address}
    RETURN    ${value.strip()}

*** Test Cases ***
A55 Core 0 And M7 Complete Handshake On Four-Core EVK Model
    [Timeout]    30 seconds
    Create Test Machine
    Verify Processor Topology
    Load Handshake Firmware
    Execute Command    emulation RunFor "0.01"
    ${magic}=      Read Dword    ${MAGIC_ADDR}
    ${command}=    Read Dword    ${COMMAND_ADDR}
    ${status}=     Read Dword    ${STATUS_ADDR}
    ${result}=     Read Dword    ${RESULT_ADDR}
    Should Be Equal As Numbers    ${magic}      0xA55A55A5
    Should Be Equal As Numbers    ${command}    0x95200001
    Should Be Equal As Numbers    ${status}     0x4D370001
    Should Be Equal As Numbers    ${result}     0x600D600D
