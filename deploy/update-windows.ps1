param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$Revision,
    [string]$BackupDir = 'E:\AsteriaBackups',
    [switch]$Cpu,
    [switch]$CheckOnly,
    [switch]$AdoptExisting
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$envFile = Join-Path $repo 'deploy\.env'
$docker = (Get-Command docker.exe -ErrorAction Stop).Source
$previousRevision = $null
$oldBackend = $null
$oldWeb = $null
$oldWorker = $null
$switched = $false
$containersChanged = $false
$activationStarted = $false
$imageTag = 'local'
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
    if ($env:ASTERIA_LAN_BIND_HOST -and (Test-Path -LiteralPath 'deploy/compose.lan.yaml')) {
        $argsList += @('-f', 'deploy/compose.lan.yaml')
    }
    $argsList += @('--env-file', 'deploy/.env')
    return $argsList
}

function Active-Work {
    $sql = "SELECT (SELECT count(*) FROM research_runs WHERE status IN ('queued','running','waiting_approval','cancel_requested')) + (SELECT count(*) FROM coordinator_turns WHERE status='running') + (SELECT count(*) FROM knowledge_versions WHERE status IN ('queued','indexing'))"
    $count = (& $docker exec asteria-lab-postgres-1 psql -U asteria -d asteria -tAc $sql | Out-String).Trim()
    Require-Exit 'Active task check'
    if ($count -notmatch '^\d+$') { throw "Invalid active task count: $count" }
    return [int]$count
}

function Container-Revision([string]$name) {
    # Read only the image revision, never print the container's environment or keys.
    $raw = (& $docker inspect $name --format '{{json .Config.Env}}' | Out-String).Trim()
    Require-Exit "Container revision check: $name"
    $entries = ConvertFrom-Json -InputObject $raw
    $entry = $entries | Where-Object { $_ -like 'ASTERIA_BUILD_REVISION=*' } | Select-Object -Last 1
    if (-not $entry) { return 'unknown' }
    return $entry.Substring('ASTERIA_BUILD_REVISION='.Length)
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
$deployedRevision = Container-Revision 'asteria-lab-api-1'
$workerRevision = Container-Revision 'asteria-lab-worker-1'
if ($workerRevision -ne $deployedRevision) {
    throw "API and Worker image revisions differ ($deployedRevision / $workerRevision); align them before updating."
}
if ($deployedRevision -ne $previousRevision -and -not $AdoptExisting) {
    throw "Running image revision ($deployedRevision) differs from checkout ($previousRevision). First Windows adoption requires -AdoptExisting after confirming the running image and backup; ordinary updates refuse this mismatch."
}
$schemaChanges = @(& git -C $repo diff --name-only $previousRevision $Revision -- backend | Where-Object { $_ -match '(^|/)schema\.sql$|(^|/)migrations?/' })
Require-Exit 'Schema migration check'
if ($schemaChanges.Count -gt 0) {
    throw 'Database schema changes require a separate reviewed migration/rollback plan; automatic image rollback is not enough.'
}
if ((Active-Work) -ne 0) {
    throw 'Update deferred: research, coordinator, or indexing work is active.'
}
Write-Host "Current: $previousRevision"
Write-Host "Running image revision: $deployedRevision"
Write-Host "Target:  $Revision"
if ($CheckOnly) {
    Write-Host 'Revision, Docker, schema-change, and active-work checks passed. No deployment changes made.'
    exit 0
}

$configuredImageTag = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^ASTERIA_IMAGE_TAG=' } | Select-Object -Last 1
if ($env:ASTERIA_IMAGE_TAG) {
    $imageTag = $env:ASTERIA_IMAGE_TAG
} elseif ($configuredImageTag) {
    $imageTag = $configuredImageTag.Substring('ASTERIA_IMAGE_TAG='.Length)
}
if ($imageTag -notmatch '^[A-Za-z0-9_.-]+$') { throw 'Invalid ASTERIA_IMAGE_TAG' }

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
$oldWorker = (& $docker inspect 'asteria-lab-worker-1' --format '{{.Image}}' | Out-String).Trim()
Require-Exit 'Running worker image check'
if ($oldWorker -ne $oldBackend) { throw 'API and Worker use different backend images; update requires a consistent baseline.' }
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
    if (-not $env:ASTERIA_LAN_BIND_HOST) {
        $lanLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^ASTERIA_LAN_BIND_HOST=' } | Select-Object -Last 1
        if ($lanLine) { $env:ASTERIA_LAN_BIND_HOST = $lanLine.Substring('ASTERIA_LAN_BIND_HOST='.Length) }
    }
    $compose = Compose-Args
    if ($env:ASTERIA_LAN_BIND_HOST -and -not (Test-Path -LiteralPath 'deploy/compose.lan.yaml')) {
        throw 'LAN bind is configured but target revision lacks deploy/compose.lan.yaml'
    }
    & $docker @compose config --quiet
    Require-Exit 'Compose config'
    & $docker @compose build api worker web
    Require-Exit 'Compose build'
    & $docker run --rm "asteria-backend:$imageTag" python /tmp/verify-installed-packages.py
    Require-Exit 'Built backend package integrity check'

    # Stop ingress before the final check. A user could submit a new paid job
    # during the (potentially lengthy) Docker build after the first check.
    $containersChanged = $true
    & $docker @compose stop web api
    Require-Exit 'Stop new submissions'
    if ((Active-Work) -ne 0) {
        throw 'Update deferred: work started during image build; previous services will be restored.'
    }
    $activationStarted = $true
    & $docker @compose stop worker
    Require-Exit 'Stop worker before activation'
    & $docker @compose up -d --no-build --no-deps --force-recreate api
    Require-Exit 'API start'
    Wait-Health 'asteria-lab-api-1'
    & $docker @compose up -d --no-build --no-deps --force-recreate worker web
    Require-Exit 'Worker and web start'
    Wait-Running 'asteria-lab-worker-1'
    Wait-Health 'asteria-lab-web-1'
    if ((Container-Revision 'asteria-lab-api-1') -ne $Revision -or
        (Container-Revision 'asteria-lab-worker-1') -ne $Revision) {
        throw 'Activated API/Worker image revision does not match the requested commit'
    }
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8018/health' -TimeoutSec 10
    if ($health.status -ne 'ok') { throw 'API health response is not OK' }
    $login = Invoke-WebRequest -Uri 'http://127.0.0.1:3023/login' -UseBasicParsing -TimeoutSec 10
    if ($login.StatusCode -ne 200) { throw 'Login page did not return HTTP 200' }
    & $docker @compose ps
    Require-Exit 'Compose status'
    Write-Host "SUCCESS: deployed $Revision; database backup at $backupFile"
} catch {
    $failure = $_
    try {
        if ($oldBackend -and $oldWeb) {
            & $docker image tag $oldBackend "asteria-backend:$imageTag" | Out-Null
            Require-Exit 'Restore backend image tag'
            & $docker image tag $oldWeb "asteria-web:$imageTag" | Out-Null
            Require-Exit 'Restore web image tag'
        }
        if ($switched) {
            & git switch --detach $previousRevision | Out-Null
            Require-Exit 'Restore previous checkout'
        }
        if ($containersChanged) {
            $env:ASTERIA_BUILD_REVISION = $deployedRevision
            $compose = Compose-Args
            if ($activationStarted) {
                & $docker @compose up -d --no-build --no-deps --force-recreate api worker web | Out-Host
            } else {
                # An old Worker may have begun a task during build. Do not
                # recreate or stop it while restoring the old API/Web ingress.
                & $docker @compose up -d --no-build --no-deps api web | Out-Host
            }
            Require-Exit 'Restore previous containers'
            Wait-Health 'asteria-lab-api-1'
            Wait-Running 'asteria-lab-worker-1'
            Wait-Health 'asteria-lab-web-1'
        }
    } catch {
        throw "Update failed: $failure; automatic rollback ALSO failed: $_. Keep the database backup and previous image IDs; do not run down -v."
    }
    throw "Update failed and previous containers were restored: $failure"
} finally {
    Pop-Location
}
