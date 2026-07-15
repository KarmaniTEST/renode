*** Settings ***
Documentation     Validate the NXP i.MX 952 EVK heterogeneous platform and early boot services.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}       ${CURDIR}/../../platforms/boards/nxp_imx952_evk.repl
${SIP_SCRIPT}     ${CURDIR}/../../scripts/single-node/nxp_imx952_evk.resc
${A55_HEX}        ${CURDIR}/NXP_IMX952/a55_handshake.hex
${A55_SIP_HEX}    ${CURDIR}/NXP_IMX952/a55_sip_boot_m7.hex
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

A55 NXP SiP Service Releases M7 And Completes Handshake
    [Timeout]    30 seconds
    Execute Command    i @${SIP_SCRIPT}
    Execute Command    sysbus LoadHEX @${M7_HEX}
    Execute Command    sysbus LoadHEX @${A55_SIP_HEX}
    Execute Command    a55Cluster.a55_0 PC 0x80000000
    Execute Command    emulation RunFor "0.02"
    ${prep}=       Read Dword    0x88020020
    ${prepared}=   Read Dword    0x88020024
    ${start}=      Read Dword    0x88020028
    ${started}=    Read Dword    0x8802002C
    ${status}=     Read Dword    ${STATUS_ADDR}
    Should Be Equal As Numbers    ${prep}       0
    Should Be Equal As Numbers    ${prepared}   1
    Should Be Equal As Numbers    ${start}      0
    Should Be Equal As Numbers    ${started}    1
    Should Be Equal As Numbers    ${status}     0x4D370001

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

M7 System Manager Starts Cortex M7 Through NXP SCMI CPU Protocol
    [Timeout]    30 seconds
    Create Test Machine
    Execute Command    m7 IsHalted true
    Execute Command    sysbus LoadHEX @${M7_HEX}
    Write Dword    ${MAGIC_ADDR}      0xA55A55A5
    Write Dword    ${COMMAND_ADDR}    0x95200001

    # Enable MU5 response interrupt channel 0 and query the M7-agent Base protocol.
    Write Dword    0x44610110    0x00000001
    Write Dword    0x44611018    0x00004000
    Write Dword    0x44610114    0x00000001
    ${m7_base_status}=     Read Dword    0x4461101C
    ${m7_base_version}=    Read Dword    0x44611020
    ${m7_response_gsr}=    Read Dword    0x44610118
    Should Be Equal As Numbers    ${m7_base_status}     0
    Should Be Equal As Numbers    ${m7_base_version}    0x00020000
    Should Be Equal As Numbers    ${m7_response_gsr}    1
    Write Dword    0x44610118    0x00000001
    ${m7_cleared_gsr}=    Read Dword    0x44610118
    Should Be Equal As Numbers    ${m7_cleared_gsr}    0

    # NXP CPU protocol 0x82 / RESET_VECTOR_SET (message 0x6).
    # CPU ID 1 is the i.MX 952 Cortex-M7; START flag releases it from reset.
    Write Dword    0x4461101C    1
    Write Dword    0x44611020    0x40000000
    Write Dword    0x44611024    0x00000000
    Write Dword    0x44611028    0x00000000
    Write Dword    0x44611018    0x00020806
    Write Dword    0x44610114    0x00000001
    ${vector_status}=    Read Dword    0x4461101C
    Should Be Equal As Numbers    ${vector_status}    0

    # INFO_GET (message 0xC) must report CPU_RUN_MODE_START.
    Write Dword    0x4461101C    1
    Write Dword    0x44611018    0x0002080C
    Write Dword    0x44610114    0x00000001
    ${info_status}=    Read Dword    0x4461101C
    ${run_mode}=       Read Dword    0x44611020
    Should Be Equal As Numbers    ${info_status}    0
    Should Be Equal As Numbers    ${run_mode}       0

    Execute Command    emulation RunFor "0.01"
    ${status}=    Read Dword    ${STATUS_ADDR}
    Should Be Equal As Numbers    ${status}    0x4D370001

    # CPU_STOP (message 0x5) halts the real modeled M7.
    Write Dword    0x4461101C    1
    Write Dword    0x44611018    0x00020805
    Write Dword    0x44610114    0x00000001
    ${stop_status}=    Read Dword    0x4461101C
    Should Be Equal As Numbers    ${stop_status}    0
    Write Dword    0x4461101C    1
    Write Dword    0x44611018    0x0002080C
    Write Dword    0x44610114    0x00000001
    ${stopped_mode}=    Read Dword    0x44611020
    Should Be Equal As Numbers    ${stopped_mode}    2

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

LPI2C7 Reads EVK Type C Controller Identity And NACKs Unknown Devices
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

    # Clear status and address an unmodelled device at 0x51. The controller
    # must report NACK Detect (MSR[NDF], bit 10) instead of inventing a device.
    Write Dword    0x422F0014    0x00007F00
    Write Dword    0x422F0060    0x000004A2
    ${unknown_status}=    Read Dword    0x422F0014
    Should Be Equal As Numbers    ${unknown_status}    0x00000400

MU7 Transfers Data Bidirectionally Between A55 And M7 Endpoints
    Create Test Machine
    # Enable receive interrupt for word 0 on both endpoints.
    Write Dword    0x42050128    0x00000001
    Write Dword    0x42440128    0x00000001

    # A55 -> M7: write TX0 on A instance, observe RX status/data on B instance.
    Write Dword    0x42050200    0xA55A0001
    ${m7_rx_status}=    Read Dword    0x4244012C
    ${m7_rx_data}=      Read Dword    0x42440280
    ${m7_rx_cleared}=   Read Dword    0x4244012C
    Should Be Equal As Numbers    ${m7_rx_status}     0x00000001
    Should Be Equal As Numbers    ${m7_rx_data}       0xA55A0001
    Should Be Equal As Numbers    ${m7_rx_cleared}    0x00000000

    # M7 -> A55: write TX0 on B instance, observe RX status/data on A instance.
    Write Dword    0x42440200    0x4D370001
    ${a55_rx_status}=    Read Dword    0x4205012C
    ${a55_rx_data}=      Read Dword    0x42050280
    ${a55_rx_cleared}=   Read Dword    0x4205012C
    Should Be Equal As Numbers    ${a55_rx_status}     0x00000001
    Should Be Equal As Numbers    ${a55_rx_data}       0x4D370001
    Should Be Equal As Numbers    ${a55_rx_cleared}    0x00000000

    # General-purpose interrupt flag propagation in both directions.
    Write Dword    0x42050114    0x00000001
    ${m7_gsr}=    Read Dword    0x42440118
    Should Be Equal As Numbers    ${m7_gsr}    0x00000001
    Write Dword    0x42440118    0x00000001
    ${m7_gsr_cleared}=    Read Dword    0x42440118
    Should Be Equal As Numbers    ${m7_gsr_cleared}    0x00000000
