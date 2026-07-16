*** Settings ***
Documentation     Validate source-bounded i.MX952 ELE early-boot services and secure-default denial policy.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${PLATFORM}               ${CURDIR}/../../platforms/boards/nxp_imx952_evk_full.repl
${ELE_TR0}                0x47550200
${ELE_TR1}                0x47550204
${ELE_TR2}                0x47550208
${ELE_TR3}                0x4755020C
${ELE_RR0}                0x47550280
${ELE_RR1}                0x47550284
${ELE_RR2}                0x47550288
${ELE_RR3}                0x4755028C
${ELE_TEST_CONTROL}       0x475503F0
${ELE_TEST_EVENT}         0x475503F4
${ELE_VOLTAGE_STATE}      0x475503F8
${ELE_RNG_COUNT}          0x475503FC
${RNG_BUFFER}             0x80001000

*** Keywords ***
Create Full Candidate
    Execute Command    mach create "imx952-ele-policy"
    Execute Command    machine LoadPlatformDescription @${PLATFORM}

Write Dword
    [Arguments]    ${address}    ${value}
    Execute Command    sysbus WriteDoubleWord ${address} ${value}

Read Dword
    [Arguments]    ${address}
    ${value}=    Execute Command    sysbus ReadDoubleWord ${address}
    RETURN    ${value.strip()}

Call ELE One Word
    [Arguments]    ${header}
    Write Dword    ${ELE_TR0}    ${header}

Call ELE Two Words
    [Arguments]    ${header}    ${word1}
    Write Dword    ${ELE_TR0}    ${header}
    Write Dword    ${ELE_TR1}    ${word1}

Call ELE Three Words
    [Arguments]    ${header}    ${word1}    ${word2}
    Write Dword    ${ELE_TR0}    ${header}
    Write Dword    ${ELE_TR1}    ${word1}
    Write Dword    ${ELE_TR2}    ${word2}

Call ELE Four Words
    [Arguments]    ${header}    ${word1}    ${word2}    ${word3}
    Write Dword    ${ELE_TR0}    ${header}
    Write Dword    ${ELE_TR1}    ${word1}
    Write Dword    ${ELE_TR2}    ${word2}
    Write Dword    ${ELE_TR3}    ${word3}

Read Response Two Words
    ${header}=    Read Dword    ${ELE_RR0}
    ${status}=    Read Dword    ${ELE_RR1}
    RETURN    ${header}    ${status}

*** Test Cases ***
Ping Firmware Metadata And Event Query Use NXP Message Layouts
    Create Full Candidate

    Call ELE One Word    0x17010106
    ${ping_header}    ${ping_status}=    Read Response Two Words
    Should Be Equal As Numbers    ${ping_header}    0xE1010206
    Should Be Equal As Numbers    ${ping_status}    0xD6

    Call ELE One Word    0x179D0106
    ${fw_header}=     Read Dword    ${ELE_RR0}
    ${fw_status}=     Read Dword    ${ELE_RR1}
    ${fw_version}=    Read Dword    ${ELE_RR2}
    ${fw_sha}=        Read Dword    ${ELE_RR3}
    Should Be Equal As Numbers    ${fw_header}     0xE19D0406
    Should Be Equal As Numbers    ${fw_status}     0xD6
    Should Be Equal As Numbers    ${fw_version}    0
    Should Be Equal As Numbers    ${fw_sha}        0

    Write Dword    ${ELE_TEST_EVENT}    0x1234ABCD
    Call ELE One Word    0x17A20106
    ${event_header}=    Read Dword    ${ELE_RR0}
    ${event_status}=    Read Dword    ${ELE_RR1}
    ${event_count}=     Read Dword    ${ELE_RR2}
    ${event}=           Read Dword    ${ELE_RR3}
    Should Be Equal As Numbers    ${event_header}    0xE1A20406
    Should Be Equal As Numbers    ${event_status}    0xD6
    Should Be Equal As Numbers    ${event_count}     1
    Should Be Equal As Numbers    ${event}           0x1234ABCD

    Call ELE One Word    0x17A20106
    ${empty_count}=    Read Dword    ${ELE_RR2}
    Should Be Equal As Numbers    ${empty_count}    0

Voltage Change Sequencing Is Stateful And Rejects Invalid Ordering
    Create Full Candidate

    Call ELE One Word    0x17120106
    ${start_header}    ${start_status}=    Read Response Two Words
    ${active}=    Read Dword    ${ELE_VOLTAGE_STATE}
    Should Be Equal As Numbers    ${start_header}    0xE1120206
    Should Be Equal As Numbers    ${start_status}    0xD6
    Should Be Equal As Numbers    ${active}          1

    Call ELE One Word    0x17120106
    ${repeat_header}    ${repeat_status}=    Read Response Two Words
    Should Be Equal As Numbers    ${repeat_header}    0xE1120206
    Should Be Equal As Numbers    ${repeat_status}    0xC0

    Call ELE One Word    0x17130106
    ${finish_header}    ${finish_status}=    Read Response Two Words
    ${inactive}=    Read Dword    ${ELE_VOLTAGE_STATE}
    Should Be Equal As Numbers    ${finish_header}    0xE1130206
    Should Be Equal As Numbers    ${finish_status}    0xD6
    Should Be Equal As Numbers    ${inactive}         0

    Call ELE One Word    0x17130106
    ${invalid_header}    ${invalid_status}=    Read Response Two Words
    Should Be Equal As Numbers    ${invalid_header}    0xE1130206
    Should Be Equal As Numbers    ${invalid_status}    0xC0

TRNG State Is Functional But RNG DMA Fails Closed By Default
    Create Full Candidate

    Call ELE One Word    0x17A40106
    ${cold_header}=    Read Dword    ${ELE_RR0}
    ${cold_status}=    Read Dword    ${ELE_RR1}
    ${cold_state}=     Read Dword    ${ELE_RR2}
    Should Be Equal As Numbers    ${cold_header}    0xE1A40306
    Should Be Equal As Numbers    ${cold_status}    0xD6
    Should Be Equal As Numbers    ${cold_state}     0

    Call ELE One Word    0x17A30106
    ${start_header}    ${start_status}=    Read Response Two Words
    Should Be Equal As Numbers    ${start_header}    0xE1A30206
    Should Be Equal As Numbers    ${start_status}    0xD6

    Call ELE One Word    0x17A40106
    ${ready_header}=    Read Dword    ${ELE_RR0}
    ${ready_status}=    Read Dword    ${ELE_RR1}
    ${ready_state}=     Read Dword    ${ELE_RR2}
    Should Be Equal As Numbers    ${ready_header}    0xE1A40306
    Should Be Equal As Numbers    ${ready_status}    0xD6
    Should Be Equal As Numbers    ${ready_state}     0x203

    Call ELE Four Words    0x17CD0407    0    ${RNG_BUFFER}    16
    ${denied_header}    ${denied_status}=    Read Response Two Words
    ${unchanged}=    Read Dword    ${RNG_BUFFER}
    Should Be Equal As Numbers    ${denied_header}    0xE1CD0207
    Should Be Equal As Numbers    ${denied_status}    0xB6
    Should Be Equal As Numbers    ${unchanged}        0

Explicit Test Mode Enables Deterministic Non Cryptographic RNG Only
    Create Full Candidate
    Call ELE One Word    0x17A30106
    Read Response Two Words

    Write Dword    ${ELE_TEST_CONTROL}    0x54455354
    Call ELE Four Words    0x17CD0407    0    ${RNG_BUFFER}    16
    ${rng_header}    ${rng_status}=    Read Response Two Words
    ${word0}=    Read Dword    ${RNG_BUFFER}
    ${count}=    Read Dword    ${ELE_RNG_COUNT}
    Should Be Equal As Numbers    ${rng_header}    0xE1CD0207
    Should Be Equal As Numbers    ${rng_status}    0xD6
    Should Be Equal As Numbers    ${word0}         0x8993F325
    Should Be Equal As Numbers    ${count}         1

    Write Dword    ${ELE_TEST_CONTROL}    0
    Call ELE Four Words    0x17CD0407    0    0x80001020    4
    ${disabled_header}    ${disabled_status}=    Read Response Two Words
    Should Be Equal As Numbers    ${disabled_header}    0xE1CD0207
    Should Be Equal As Numbers    ${disabled_status}    0xB6

Invalid Fuse IDs And Security Sensitive Commands Fail Closed
    Create Full Candidate

    Call ELE Two Words    0x17970206    2
    ${fuse_header}    ${fuse_status}=    Read Response Two Words
    Should Be Equal As Numbers    ${fuse_header}    0xE1970206
    Should Be Equal As Numbers    ${fuse_status}    0xF6

    # OEM container authentication is denied without a secure backend.
    Call ELE Three Words    0x17870306    0    0x80000000
    ${auth_header}    ${auth_status}=    Read Response Two Words
    Should Be Equal As Numbers    ${auth_header}    0xE1870206
    Should Be Equal As Numbers    ${auth_status}    0xF3

    # Fuse programming is also denied and never mutates the readable fuse map.
    Call ELE Three Words    0x17D60306    0    0xFFFFFFFF
    ${write_header}    ${write_status}=    Read Response Two Words
    Should Be Equal As Numbers    ${write_header}    0xE1D60206
    Should Be Equal As Numbers    ${write_status}    0xF3

    Call ELE One Word    0x17550106
    ${unknown_header}    ${unknown_status}=    Read Response Two Words
    Should Be Equal As Numbers    ${unknown_header}    0xE1550206
    Should Be Equal As Numbers    ${unknown_status}    0xF4
