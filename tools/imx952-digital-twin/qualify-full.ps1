param(
    [ValidateSet("auto", "local", "docker")]
    [string]$RuntimeMode = "auto",

    [ValidateSet("engineering", "full-physical")]
    [string]$QualificationMode = "engineering",

    [string]$ReferenceEvidence = $env:IMX952_REFERENCE_EVIDENCE,
    [string]$CandidateEvidence = $env:IMX952_CANDIDATE_EVIDENCE
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = (Resolve-Path (Join-Path $ScriptDir "../..")).Path
$EquivDir = Join-Path $ScriptDir "equivalence"
$Profile = Join-Path $EquivDir "profiles/imx952_evk_b0_foundation.json"
$Report = Join-Path $RootDir "imx952-hardware-comparison.json"
$Tests = @(
    "tests/platforms/NXP_IMX952.robot",
    "tests/platforms/NXP_IMX952_FULL_EQUIVALENCE.robot"
)

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

Write-Host "[i.MX952] Qualification mode: $QualificationMode"
Write-Host "[i.MX952] Runtime mode: $RuntimeMode"

Push-Location $RootDir
try {
    Invoke-Checked { python -m unittest discover -s tools/imx952-digital-twin/equivalence/tests -p "test_*.py" -v }
    Invoke-Checked { python tools/imx952-digital-twin/equivalence/qualification_gate.py --mode engineering --skip-tests }

    $UseDocker = $RuntimeMode -eq "docker"
    if ($RuntimeMode -eq "auto") {
        $UseDocker = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
    }

    if ($UseDocker) {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            throw "Docker is not installed or not available in PATH."
        }

        $DockerArgs = @(
            "run", "--rm",
            "-v", "${RootDir}:/workspace",
            "-v", "${RootDir}/scripts/pydev/nxp_imx952_system_manager.py:/opt/renode/scripts/pydev/nxp_imx952_system_manager.py:ro",
            "-v", "${RootDir}/scripts/pydev/nxp_imx952_system_manager_full.py:/opt/renode/scripts/pydev/nxp_imx952_system_manager_full.py:ro",
            "-v", "${RootDir}/scripts/pydev/nxp_imx952_ele.py:/opt/renode/scripts/pydev/nxp_imx952_ele.py:ro",
            "-v", "${RootDir}/scripts/pydev/nxp_imx952_lpi2c7.py:/opt/renode/scripts/pydev/nxp_imx952_lpi2c7.py:ro",
            "-w", "/workspace",
            "antmicro/renode:nightly-dotnet",
            "renode-test", "--show-log"
        ) + $Tests
        & docker @DockerArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Renode Docker qualification failed with exit code $LASTEXITCODE"
        }
    }
    else {
        if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
            throw "Local qualification requires bash and a built Renode repository, or use Docker mode."
        }
        & bash ./test.sh --show-log @Tests
        if ($LASTEXITCODE -ne 0) {
            throw "Local Renode qualification failed with exit code $LASTEXITCODE"
        }
    }

    if ($QualificationMode -eq "full-physical") {
        if ([string]::IsNullOrWhiteSpace($ReferenceEvidence) -or [string]::IsNullOrWhiteSpace($CandidateEvidence)) {
            throw "Full physical qualification requires ReferenceEvidence and CandidateEvidence."
        }

        Invoke-Checked {
            python tools/imx952-digital-twin/equivalence/compare_evidence.py `
                --reference $ReferenceEvidence `
                --candidate $CandidateEvidence `
                --profile $Profile `
                --output $Report
        }
        Invoke-Checked {
            python tools/imx952-digital-twin/equivalence/qualification_gate.py `
                --mode full-physical `
                --skip-tests `
                --comparison-report $Report
        }
    }

    Write-Host "[i.MX952] Qualification completed successfully"
}
finally {
    Pop-Location
}
