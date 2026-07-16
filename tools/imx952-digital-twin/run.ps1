param(
    [ValidateSet("demo", "mu7", "platform", "qualify")]
    [string]$Mode = "demo",

    [ValidateSet("auto", "local", "docker")]
    [string]$QualificationMode = "auto"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = (Resolve-Path (Join-Path $ScriptDir "../..")).Path

if ($Mode -eq "qualify") {
    $Qualify = Join-Path $ScriptDir "qualify.sh"
    if (Get-Command bash -ErrorAction SilentlyContinue) {
        & bash $Qualify $QualificationMode
        exit $LASTEXITCODE
    }

    throw "Qualification requires bash (Git Bash/WSL) or use the GitHub Actions workflow."
}

$Renode = $env:RENODE_BIN
if ([string]::IsNullOrWhiteSpace($Renode)) {
    $Command = Get-Command renode -ErrorAction SilentlyContinue
    if ($Command) {
        $Renode = $Command.Source
    }
}

if ([string]::IsNullOrWhiteSpace($Renode)) {
    $LocalRenode = Join-Path $RootDir "renode.exe"
    if (Test-Path $LocalRenode) {
        $Renode = $LocalRenode
    }
}

if ([string]::IsNullOrWhiteSpace($Renode)) {
    throw "Renode executable not found. Set RENODE_BIN or add renode to PATH."
}

switch ($Mode) {
    "demo" {
        $Resc = Join-Path $RootDir "scripts/single-node/nxp_imx952_evk_heterogeneous_demo.resc"
    }
    "mu7" {
        $Resc = Join-Path $RootDir "scripts/single-node/nxp_imx952_evk_mu7_firmware_demo.resc"
    }
    "platform" {
        $Resc = Join-Path $RootDir "scripts/single-node/nxp_imx952_evk.resc"
    }
}

Write-Host "[i.MX952] Starting $Mode with $Renode"
Push-Location $RootDir
try {
    & $Renode --console $Resc
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $ExitCode
