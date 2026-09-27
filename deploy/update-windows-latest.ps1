param(
    [string]$BackupDir = 'E:\AsteriaBackups',
    [switch]$Cpu,
    [switch]$CheckOnly,
    [switch]$AdoptExisting
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$updateScript = Join-Path $PSScriptRoot 'update-windows.ps1'
$powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
$docker = (Get-Command docker.exe -ErrorAction Stop).Source

function Require-Exit([string]$step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE)" }
}

function Invoke-Update([string]$revision, [bool]$checkOnly) {
    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $updateScript,
        '-Revision', $revision, '-BackupDir', $BackupDir)
    if ($Cpu) { $arguments += '-Cpu' }
    if ($AdoptExisting) { $arguments += '-AdoptExisting' }
    if ($checkOnly) { $arguments += '-CheckOnly' }
    & $powershell @arguments
    Require-Exit $(if ($checkOnly) { 'Update preflight' } else { 'Update activation' })
}

function Container-Revision([string]$name) {
    try {
        $raw = (& $docker inspect $name --format '{{json .Config.Env}}' 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { return 'unknown' }
        $entry = (ConvertFrom-Json -InputObject $raw) |
            Where-Object { $_ -like 'ASTERIA_BUILD_REVISION=*' } | Select-Object -Last 1
        if (-not $entry) { return 'unknown' }
        return $entry.Substring('ASTERIA_BUILD_REVISION='.Length)
    } catch { return 'unknown' }
}

if (-not (Test-Path -LiteralPath (Join-Path $repo 'deploy\.env'))) {
    throw 'Local deploy/.env is missing; use the dedicated deployment checkout with its existing secrets.'
}

& git -C $repo fetch origin main --tags
Require-Exit 'Fetch origin/main'
$revision = (& git -C $repo rev-parse origin/main | Out-String).Trim()
Require-Exit 'Resolve origin/main'
if ($revision -notmatch '^[0-9a-fA-F]{40}$') { throw 'origin/main did not resolve to a commit SHA.' }
Write-Host "Latest merged main revision: $revision"

$checkout = (& git -C $repo rev-parse HEAD | Out-String).Trim()
Require-Exit 'Resolve checkout HEAD'
if (-not $AdoptExisting -and $checkout -eq $revision -and
    (Container-Revision 'asteria-lab-api-1') -eq $revision -and
    (Container-Revision 'asteria-lab-worker-1') -eq $revision) {
    if ($CheckOnly) {
        Write-Host 'This revision is already deployed. No update is needed.'
    } else {
        $restartArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            (Join-Path $PSScriptRoot 'restart-windows.ps1'))
        if ($Cpu) { $restartArgs += '-Cpu' }
        & $powershell @restartArgs
        Require-Exit 'Current deployment health check'
        Write-Host 'This revision is already deployed and healthy.'
    }
    exit 0
}

Invoke-Update $revision $true
if ($CheckOnly) { exit 0 }

# The lower-level updater handles the database backup, image rollback tags,
# active-job check, activation and health checks. Never deploy an unmerged branch.
Invoke-Update $revision $false
