param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$Revision,
    [string]$BackupDir = 'E:\AsteriaBackups',
    [switch]$Cpu,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$envFile = Join-Path $repo 'deploy\.env'
$docker = (Get-Command docker.exe -ErrorAction Stop).Source
$previousRevision = $null
$oldBackend = $null
$oldWeb = $null
$switched = $false
$containersChanged = $false
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

function Require-Exit([string]$step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE)" }
}

function Wait-Health([string]$name, [int]$attempts = 30) {
    for ($i = 0; $i -lt $attempts; $i++) {
        $state = (& $docker inspect $name --format '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $state -eq 'running/healthy') { return }
        Start-Sleep -Seconds 4
    }
    throw "$name did not become healthy"
}

function Wait-Running([string]$name, [int]$attempts = 15) {
    for ($i = 0; $i -lt $attempts; $i++) {
        $state = (& $docker inspect $name --format '{{.State.Status}}' 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $state -eq 'running') { return }
        Start-Sleep -Seconds 4
    }
    throw "$name did not start"
}

function Compose-Args {
    $argsList = @('compose', '-f', 'compose.yaml')
    if (-not $Cpu) { $argsList += @('-f', 'deploy/compose.gpu.yaml') }
    if ($env:ASTERIA_LAN_BIND_HOST) { $argsList += @('-f', 'deploy/compose.lan.yaml') }
    $argsList += @('--env-file', 'deploy/.env')
    return $argsList
}

if (-not (Test-Path -LiteralPath $envFile)) { throw 'Local deploy/.env is missing; keep the existing secret file.' }
if (-not (Test-Path -LiteralPath (Split-Path -Qualifier $BackupDir))) { throw "Backup drive is unavailable: $BackupDir" }
& $docker info --format '{{.ServerVersion}}' | Out-Null
Require-Exit 'Docker engine check'
$dirty = (& git -C $repo status --porcelain --untracked-files=normal | Out-String).Trim()
Require-Exit 'Git status'
if ($dirty) { throw 'Deployment checkout has local code changes. Use a clean clone or commit them before updating.' }
& git -C $repo fetch origin main --tags
Require-Exit 'Git fetch'
& git -C $repo cat-file -e "$Revision^{commit}"
Require-Exit 'Target commit check'
& git -C $repo merge-base --is-ancestor $Revision origin/main
Require-Exit 'Target must be merged into origin/main'

$previousRevision = (& git -C $repo rev-parse HEAD | Out-String).Trim()
Write-Host "Current: $previousRevision"
Write-Host "Target:  $Revision"
if ($CheckOnly) {
    Write-Host 'Revision and Docker checks passed. No deployment changes made.'
    exit 0
}

$activeSql = "SELECT (SELECT count(*) FROM research_runs WHERE status IN ('queued','running','waiting_approval','cancel_requested')) + (SELECT count(*) FROM coordinator_turns WHERE status='running') + (SELECT count(*) FROM knowledge_versions WHERE status IN ('queued','indexing'))"
$active = (& $docker exec asteria-lab-postgres-1 psql -U asteria -d asteria -tAc $activeSql | Out-String).Trim()
Require-Exit 'Active task check'
if ($active -notmatch '^\d+$' -or [int]$active -ne 0) {
    throw "Update deferred: active work count is $active"
}

New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$backupFile = Join-Path $BackupDir "asteria-db-before-$stamp.dump"
& $docker exec asteria-lab-postgres-1 pg_dump -U asteria -d asteria -Fc -f /tmp/asteria-pre-update.dump
Require-Exit 'Database backup inside container'
& $docker cp 'asteria-lab-postgres-1:/tmp/asteria-pre-update.dump' $backupFile
Require-Exit 'Database backup copy'
& $docker exec asteria-lab-postgres-1 rm -f /tmp/asteria-pre-update.dump
Require-Exit 'Database backup temporary-file cleanup'
if (-not (Test-Path -LiteralPath $backupFile) -or (Get-Item -LiteralPath $backupFile).Length -lt 1024) {
    throw 'Database backup is missing or too small; update stopped.'
}
Write-Host "Database backup: $backupFile"

$oldBackend = (& $docker inspect 'asteria-lab-api-1' --format '{{.Image}}' | Out-String).Trim()
Require-Exit 'Running backend image check'
$oldWeb = (& $docker inspect 'asteria-lab-web-1' --format '{{.Image}}' | Out-String).Trim()
Require-Exit 'Running web image check'
& $docker image tag $oldBackend "asteria-backend:rollback-$stamp"
Require-Exit 'Tag backend rollback image'
& $docker image tag $oldWeb "asteria-web:rollback-$stamp"
Require-Exit 'Tag web rollback image'

Push-Location $repo
try {
    & git switch --detach $Revision
    Require-Exit 'Checkout target commit'
    $switched = $true
    $env:ASTERIA_BUILD_REVISION = $Revision
    Remove-Item Env:\ASTERIA_LAN_BIND_HOST -ErrorAction SilentlyContinue
    $lanLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^ASTERIA_LAN_BIND_HOST=' } | Select-Object -Last 1
    if ($lanLine) { $env:ASTERIA_LAN_BIND_HOST = $lanLine.Substring('ASTERIA_LAN_BIND_HOST='.Length) }
    $compose = Compose-Args
    & $docker @compose config --quiet
    Require-Exit 'Compose config'
    & $docker @compose build api worker web
    Require-Exit 'Compose build'

    $containersChanged = $true
    & $docker @compose up -d --no-build --no-deps --force-recreate api
    Require-Exit 'API start'
    Wait-Health 'asteria-lab-api-1'
    & $docker @compose up -d --no-build --no-deps --force-recreate worker web
    Require-Exit 'Worker and web start'
    Wait-Running 'asteria-lab-worker-1'
    Wait-Health 'asteria-lab-web-1'
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8018/health' -TimeoutSec 10
    if ($health.status -ne 'ok') { throw 'API health response is not OK' }
    $login = Invoke-WebRequest -Uri 'http://127.0.0.1:3023/login' -UseBasicParsing -TimeoutSec 10
    if ($login.StatusCode -ne 200) { throw 'Login page did not return HTTP 200' }
    & $docker @compose ps
    Require-Exit 'Compose status'
    Write-Host "SUCCESS: deployed $Revision; database backup at $backupFile"
} catch {
    $failure = $_
    if ($oldBackend -and $oldWeb) {
        & $docker image tag $oldBackend 'asteria-backend:local' | Out-Null
        & $docker image tag $oldWeb 'asteria-web:local' | Out-Null
    }
    if ($switched) { & git switch --detach $previousRevision | Out-Null }
    if ($containersChanged) {
        $env:ASTERIA_BUILD_REVISION = $previousRevision
        $compose = Compose-Args
        & $docker @compose up -d --no-build --no-deps --force-recreate api worker web | Out-Host
    }
    throw $failure
} finally {
    Pop-Location
}
