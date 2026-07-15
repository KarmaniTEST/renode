*** Settings ***
Documentation     Validate the NXP i.MX 952 EVK heterogeneous platform and early boot services.
Test Setup        Reset Emulation
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
    Execute Command    mach create "imx952-evk"
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

Write Dword
    [Arguments]    ${address}    ${value}
    Execute Command    sysbus WriteDoubleWord ${address} ${value}

Read Dword
    [Arguments]    ${address}
    ${value}=    Execute Command    sysbus ReadDoubleWord ${address}
    RETURN    ${value.strip()}

*** Test Cases ***
Four A55 Cores And M7 Complete Shared Memory Handshake
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

System Manager Handles SCMI Base Clock And Power Protocols
    Create Test Machine
    # Base protocol version, protocol 0x10 / message 0.
    Write Dword    0x445B1018    0x00004000
    Write Dword    0x445B0114    0x00000001
    ${base_status}=    Read Dword    0x445B101C
    ${base_version}=   Read Dword    0x445B1020
    Should Be Equal As Numbers    ${base_status}     0
    Should Be Equal As Numbers    ${base_version}    0x00020000

    # Clock RATE_GET, protocol 0x14 / message 6, for A55 clock ID 70.
    Write Dword    0x445B101C    70
    Write Dword    0x445B1018    0x00005006
    Write Dword    0x445B0114    0x00000001
    ${clock_status}=    Read Dword    0x445B101C
    ${a55_rate}=        Read Dword    0x445B1020
    Should Be Equal As Numbers    ${clock_status}    0
    Should Be Equal As Numbers    ${a55_rate}        1700000000

    # Power domain state set/get for the HSIO domain ID used by board_init().
    Write Dword    0x445B101C    0
    Write Dword    0x445B1020    13
    Write Dword    0x445B1024    0
    Write Dword    0x445B1018    0x00004404
    Write Dword    0x445B0114    0x00000001
    ${power_set_status}=    Read Dword    0x445B101C
    Should Be Equal As Numbers    ${power_set_status}    0

    Write Dword    0x445B101C    13
    Write Dword    0x445B1018    0x00004405
    Write Dword    0x445B0114    0x00000001
    ${power_get_status}=    Read Dword    0x445B101C
    ${power_state}=         Read Dword    0x445B1020
    Should Be Equal As Numbers    ${power_get_status}    0
    Should Be Equal As Numbers    ${power_state}         0

EdgeLock Enclave Provides SoC Identity Fuses And Firmware Status
    Create Test Machine
    # GET_INFO command, writing the 256-byte information block into DDR.
    Write Dword    0x47550200    0x17DA0406
    Write Dword    0x47550204    0x00000000
    Write Dword    0x47550208    0x80001000
    Write Dword    0x4755020C    0x00000100
    ${get_info_header}=    Read Dword    0x47550280
    ${get_info_status}=    Read Dword    0x47550284
    ${info_header}=        Read Dword    0x80001000
    ${soc_info}=           Read Dword    0x80001004
    Should Be Equal As Numbers    ${get_info_header}    0xE1DA0206
    Should Be Equal As Numbers    ${get_info_status}    0xD6
    Should Be Equal As Numbers    ${info_header}        0x00000100
    Should Be Equal As Numbers    ${soc_info}           0xA0000000

    # READ_FUSE command for deterministic blank fuse ID 0.
    Write Dword    0x47550200    0x17970206
    Write Dword    0x47550204    0x00000000
    ${fuse_header}=    Read Dword    0x47550280
    ${fuse_status}=    Read Dword    0x47550284
    ${fuse_value}=     Read Dword    0x47550288
    Should Be Equal As Numbers    ${fuse_header}    0xE1970306
    Should Be Equal As Numbers    ${fuse_status}    0xD6
    Should Be Equal As Numbers    ${fuse_value}     0

    # GET_FW_STATUS command.
    Write Dword    0x47550200    0x17C50106
    ${fw_header}=    Read Dword    0x47550280
    ${fw_status}=    Read Dword    0x47550284
    ${fw_state}=     Read Dword    0x47550288
    Should Be Equal As Numbers    ${fw_header}    0xE1C50306
    Should Be Equal As Numbers    ${fw_status}    0xD6
    Should Be Equal As Numbers    ${fw_state}     0

LPI2C7 Reads EVK Type C Controller Identity
    Create Test Machine
    # START write to address 0x50 and select TCPC register 0x00.
    Write Dword    0x422F0060    0x000004A0
    Write Dword    0x422F0060    0x00000000
    # Repeated START for read and receive two bytes.
    Write Dword    0x422F0060    0x000004A1
    Write Dword    0x422F0060    0x00000101
    ${vendor_lo}=    Read Dword    0x422F0070
    ${vendor_hi}=    Read Dword    0x422F0070
    Write Dword    0x422F0060    0x00000200
    Should Be Equal As Numbers    ${vendor_lo}    0xC9
    Should Be Equal As Numbers    ${vendor_hi}    0x1F
