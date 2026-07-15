param(
    [ValidateSet("demo", "platform", "full-platform", "qualify", "qualify-full")]
    [string]$Mode = "demo",

    [ValidateSet("auto", "local", "docker")]
    [string]$RuntimeMode = "auto",

    [ValidateSet("engineering", "full-physical")]
    [string]$QualificationMode = "engineering"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = (Resolve-Path (Join-Path $ScriptDir "../..")).Path

if ($Mode -eq "qualify") {
    $Qualify = Join-Path $ScriptDir "qualify.sh"
    if (Get-Command bash -ErrorAction SilentlyContinue) {
        & bash $Qualify $RuntimeMode
        exit $LASTEXITCODE
    }
    throw "Qualification requires bash (Git Bash/WSL) or use the GitHub Actions workflow."
}

if ($Mode -eq "qualify-full") {
    $QualifyFull = Join-Path $ScriptDir "qualify-full.ps1"
    & $QualifyFull -RuntimeMode $RuntimeMode -QualificationMode $QualificationMode
    exit $LASTEXITCODE
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
    "platform" {
        $Resc = Join-Path $RootDir "scripts/single-node/nxp_imx952_evk.resc"
    }
    "full-platform" {
        $Resc = Join-Path $RootDir "scripts/single-node/nxp_imx952_evk_full.resc"
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
