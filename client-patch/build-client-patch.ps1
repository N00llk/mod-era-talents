<#
.SYNOPSIS
Build one locale's MPQ from original client Spell.dbc and SkillLineAbility.dbc.
.EXAMPLE
./client-patch/build-client-patch.ps1 -Locale ruRU -SourceDbc ../mpq-src-data/ruru
.NOTES
Requires a running Docker engine. Sources and repository are mounted read-only;
only the output directory is writable. Custom spell translations must be complete.
#>
param(
    [Parameter(Mandatory)]
    [ValidateSet('enUS', 'enGB', 'koKR', 'frFR', 'deDE', 'zhCN', 'zhTW', 'esES', 'esMX', 'ruRU')]
    [string]$Locale,
    [Parameter(Mandatory)]
    [string]$SourceDbc,
    [string]$OutputPath,
    [switch]$Force,
    [switch]$WithoutAddon
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$sourcePath = (Resolve-Path -LiteralPath $SourceDbc).Path
foreach ($name in @('Spell.dbc', 'SkillLineAbility.dbc')) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourcePath $name) -PathType Leaf)) {
        throw "Missing original client DBC: $sourcePath/$name"
    }
}
if (-not $OutputPath) {
    $OutputPath = Join-Path $PSScriptRoot "out/$Locale/patch-V.mpq"
}
$outputFull = [System.IO.Path]::GetFullPath($OutputPath)
$outputDir = Split-Path -Parent $outputFull
$outputName = Split-Path -Leaf $outputFull
if (-not $Force -and ((Test-Path -LiteralPath $outputFull) -or
        (Test-Path -LiteralPath "$outputFull.json"))) {
    throw "Output already exists: $outputFull. Use -Force to replace it after a successful build."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker is required. Alternatively use tools/build_client_patch.py with native MPQ tools.'
}
& docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Start the Docker engine before building a client patch.' }
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$image = 'mod-era-talents-mpq:local'
& docker build -q -t $image $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw 'Client patch tool image build failed.' }
$dockerArgs = @(
    'run', '--rm',
    '--mount', "type=bind,source=$repo,destination=/work,readonly",
    '--mount', "type=bind,source=$sourcePath,destination=/source,readonly",
    '--mount', "type=bind,source=$outputDir,destination=/out",
    $image, 'python3', '/work/tools/build_client_patch.py',
    '--locale', $Locale, '--source-dbc', '/source', '--out', "/out/$outputName"
)
if ($Force) { $dockerArgs += '--force' }
if ($WithoutAddon) { $dockerArgs += '--without-addon' }
& docker @dockerArgs
if ($LASTEXITCODE -ne 0) { throw 'Client patch build failed.' }
Write-Host "Built $Locale client patch: $outputFull"
Write-Host "Build manifest: $outputFull.json"
