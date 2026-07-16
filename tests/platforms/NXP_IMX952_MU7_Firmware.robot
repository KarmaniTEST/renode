*** Settings ***
Documentation     Validate firmware-level A55/M7 communication through the native i.MX952 MU7 model.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}       ${CURDIR}/../../platforms/boards/nxp_imx952_evk.repl
${A55_MU7_HEX}    ${CURDIR}/NXP_IMX952/a55_mu7_firmware.hex
${M7_MU7_HEX}     ${CURDIR}/NXP_IMX952/m7_mu7_firmware.hex
${A55_RESULT}     0x88020030
${M7_RESULT}      0x88020034

*** Keywords ***
Create Test Machine
    Execute Command    mach create "imx952-evk-mu7-firmware"
    Execute Command    machine LoadPlatformDescription @${PLATFORM}

Read Dword
    [Arguments]    ${address}
    ${value}=    Execute Command    sysbus ReadDoubleWord ${address}
    RETURN    ${value.strip()}

*** Test Cases ***
A55 And M7 Firmware Exchange A Request And Response Through MU7
    [Timeout]    30 seconds
    Create Test Machine
    Execute Command    sysbus LoadHEX @${A55_MU7_HEX}
    Execute Command    sysbus LoadHEX @${M7_MU7_HEX}
    Execute Command    a55Cluster.a55_0 PC 0x80000000
    Execute Command    a55Cluster.a55_0 IsHalted false
    Execute Command    m7 SP 0x20040000
    Execute Command    m7 PC 0x00000008
    Execute Command    m7 IsHalted false
    Execute Command    emulation RunFor "0.02"
    ${a55_result}=    Read Dword    ${A55_RESULT}
    ${m7_result}=     Read Dword    ${M7_RESULT}
    Should Be Equal As Numbers    ${a55_result}    0x600D7007
    Should Be Equal As Numbers    ${m7_result}     0x4D3755AA
