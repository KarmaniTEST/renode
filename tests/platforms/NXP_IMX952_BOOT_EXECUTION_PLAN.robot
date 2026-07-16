*** Settings ***
Documentation     Validate the synthetic verified post-auth plan loads only ATF/U-Boot ranges and does not auto-start A55.
Test Setup        Reset Emulation
Suite Teardown    Teardown
Resource          ${RENODEKEYWORDS}

*** Variables ***
${BOOT_PLAN}       /workspace/boot-fixture/imx952-post-auth.resc

*** Test Cases ***
Verified Plan Loads ATF And U Boot Bytes At Pinned Destinations
    Execute Command    include @${BOOT_PLAN}

    ${atf_word}=      Execute Command    sysbus ReadDoubleWord 0x8A200000
    ${uboot_word}=    Execute Command    sysbus ReadDoubleWord 0x90200000
    Should Be Equal As Numbers    ${atf_word.strip()}      0x2D465441
    Should Be Equal As Numbers    ${uboot_word.strip()}    0x4F4F4255

Generated Plan Leaves A55 Halted Behind Explicit Start Macro
    Execute Command    include @${BOOT_PLAN}

    ${halted0}=    Execute Command    a55_0 IsHalted
    ${halted1}=    Execute Command    a55_1 IsHalted
    ${halted2}=    Execute Command    a55_2 IsHalted
    ${halted3}=    Execute Command    a55_3 IsHalted
    Should Be Equal    ${halted0.strip().lower()}    true
    Should Be Equal    ${halted1.strip().lower()}    true
    Should Be Equal    ${halted2.strip().lower()}    true
    Should Be Equal    ${halted3.strip().lower()}    true

    ${pc}=    Execute Command    a55_0 PC
    Should Be Equal As Numbers    ${pc.strip()}    0x8A200000
