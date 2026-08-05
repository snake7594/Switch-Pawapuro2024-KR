param(
    [string]$OriginalDir = (Join-Path $PSScriptRoot 'original'),
    [string]$DeltaDir = $PSScriptRoot,
    [string]$OutputDir = (Join-Path $PSScriptRoot 'out')
)

$ErrorActionPreference = 'Stop'
$xdelta = Join-Path $PSScriptRoot 'xdelta3.exe'
if (-not (Test-Path -LiteralPath $xdelta)) { throw "xdelta3.exe not found: $xdelta" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$jobs = @(
    @{ Name='main'; Delta='Pawapuro2026-1.1.0-main.xdelta' },
    @{ Name='RES00.RDB'; Delta='Pawapuro2026-1.1.0-RES00.RDB.xdelta' },
    @{ Name='RES00.RDI'; Delta='Pawapuro2026-1.1.0-RES00.RDI.xdelta' },
    @{ Name='RES10.RDB'; Delta='Pawapuro2026-1.1.0-RES10.RDB.xdelta' }
)

foreach ($job in $jobs) {
    $source = Join-Path $OriginalDir $job.Name
    $delta = Join-Path $DeltaDir $job.Delta
    $output = Join-Path $OutputDir $job.Name
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing original file: $source" }
    if (-not (Test-Path -LiteralPath $delta)) { throw "Missing xdelta file: $delta" }
    Write-Host "Patching $($job.Name)..."
    & $xdelta -d -f -B 268435456 -s $source $delta $output
    if ($LASTEXITCODE -ne 0) { throw "xdelta failed for $($job.Name): $LASTEXITCODE" }
}
Write-Host "Done. Output: $OutputDir"
