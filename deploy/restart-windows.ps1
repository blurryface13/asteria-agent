param(
    [switch]$Cpu,
    [int]$EngineWaitSeconds = 240,
    [int]$ServiceWaitSeconds = 240
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$envFile = Join-Path $repo 'deploy\.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Local deploy/.env is missing.' }

$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
if ($dockerCommand) { $docker = $dockerCommand.Source }
else {
    $docker = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
    if (-not (Test-Path -LiteralPath $docker)) { throw 'Docker Desktop CLI was not found.' }
}

function Docker-Ready {
    try {
        & $docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Get-Container-State([string]$name) {
    try {
        $state = (& $docker inspect $name --format '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { return 'missing' }
        return $state
    } catch { return 'missing' }
}

function Services-Ready {
    foreach ($name in @('asteria-lab-postgres-1', 'asteria-lab-redis-1', 'asteria-lab-ollama-1',
            'asteria-lab-api-1', 'asteria-lab-web-1')) {
        if ((Get-Container-State $name) -ne 'running/healthy') { return $false }
    }
    return ((Get-Container-State 'asteria-lab-worker-1') -eq 'running/none')
}

function Active-Work {
    $sql = "SELECT (SELECT count(*) FROM research_runs WHERE status IN ('queued','running','waiting_approval','cancel_requested')) + (SELECT count(*) FROM coordinator_turns WHERE status='running') + (SELECT count(*) FROM knowledge_versions WHERE status IN ('queued','indexing'))"
    $raw = (& $docker exec asteria-lab-postgres-1 psql -U asteria -d asteria -tAc $sql | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $raw -notmatch '^\d+$') { throw 'Could not check active research work.' }
    return [int]$raw
}

function Get-HttpStatusWithoutProxy([string]$url) {
    $request = [System.Net.HttpWebRequest][System.Net.WebRequest]::Create($url)
    $request.Proxy = $null
    $request.Timeout = 10000
    $response = $request.GetResponse()
    try { return [int]$response.StatusCode }
    finally { $response.Dispose() }
}

function Show-VhdOwners {
    $settingsPath = Join-Path $env:APPDATA 'Docker\settings-store.json'
    if (-not (Test-Path -LiteralPath $settingsPath)) { return }
    try {
        $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
        $root = $settings.CustomWslDistroDir
        if (-not $root) { return }
        foreach ($relative in @('main\ext4.vhdx', 'disk\docker_data.vhdx')) {
            $path = Join-Path $root $relative
            if (Test-Path -LiteralPath $path) {
                Write-Warning "WSL disk owner: $path => $((Get-Acl -LiteralPath $path).Owner)"
            }
        }
    } catch { Write-Warning "Could not inspect Docker WSL disk owners: $_" }
}

if (-not (Docker-Ready)) {
    Write-Host 'Starting Docker Desktop...'
    & $docker desktop start --timeout $EngineWaitSeconds
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Docker Desktop start reported an error; checking engine state.' }
    $deadline = (Get-Date).AddSeconds($EngineWaitSeconds)
    while (-not (Docker-Ready) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 5 }
    if (-not (Docker-Ready)) {
        Show-VhdOwners
        throw 'Docker engine is unavailable. Inspect Docker Desktop/WSL errors; do not unregister WSL or delete VHDX files.'
    }
}

$lanMode = 'compose'
$lanModeLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^ASTERIA_LAN_MODE=' } | Select-Object -Last 1
if ($lanModeLine) { $lanMode = $lanModeLine.Substring('ASTERIA_LAN_MODE='.Length) }
if ($lanMode -notin @('compose', 'portproxy')) { throw "Unsupported ASTERIA_LAN_MODE: $lanMode" }
$lanLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^ASTERIA_LAN_BIND_HOST=' } | Select-Object -Last 1
$lanBindHost = if ($lanLine) { $lanLine.Substring('ASTERIA_LAN_BIND_HOST='.Length) } else { $null }
if ($lanBindHost) { $env:ASTERIA_LAN_BIND_HOST = $lanBindHost }
if ($lanMode -eq 'portproxy' -and -not $lanBindHost) { throw 'Portproxy LAN mode requires ASTERIA_LAN_BIND_HOST.' }

$compose = @('compose', '-f', 'compose.yaml')
if (-not $Cpu) { $compose += @('-f', 'deploy/compose.gpu.yaml') }
if ($lanMode -eq 'compose' -and $lanBindHost) { $compose += @('-f', 'deploy/compose.lan.yaml') }
$compose += @('--env-file', 'deploy/.env')

Push-Location $repo
try {
    & $docker @compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration is invalid.' }
    # Docker's restart policy may still be bringing containers online after
    # the engine itself becomes ready. Give it time before reconciling Compose.
    $graceDeadline = (Get-Date).AddSeconds(45)
    while (-not (Services-Ready) -and (Get-Date) -lt $graceDeadline) { Start-Sleep -Seconds 5 }
    if (-not (Services-Ready)) {
        if ((Get-Container-State 'asteria-lab-worker-1') -eq 'running/none' -and
            (Get-Container-State 'asteria-lab-postgres-1') -eq 'running/healthy' -and
            (Active-Work) -ne 0) {
            throw 'A research task is active; refusing to reconcile containers while the Worker is running.'
        }
        Write-Host 'Starting existing Asteria images and volumes...'
        & $docker @compose up -d --no-build
        if ($LASTEXITCODE -ne 0) { throw 'Compose failed to start the existing services.' }
    }
    $deadline = (Get-Date).AddSeconds($ServiceWaitSeconds)
    while (-not (Services-Ready) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 5 }
    if (-not (Services-Ready)) {
        & $docker @compose ps
        throw 'Asteria services did not all become healthy.'
    }
    if ((Get-HttpStatusWithoutProxy 'http://127.0.0.1:3023/login') -ne 200) { throw 'Local login page is unavailable.' }
    if ((Get-HttpStatusWithoutProxy 'http://127.0.0.1:8018/health') -ne 200) { throw 'Local API is unavailable.' }
    if ($lanMode -eq 'portproxy') {
        $lanUrl = "http://${lanBindHost}:3023/login"
        foreach ($url in @($lanUrl, "http://${lanBindHost}:8018/health")) {
            try { $lanStatus = Get-HttpStatusWithoutProxy $url }
            catch { throw "LAN forwarding failed at $url. Check Wi-Fi IPv4, Windows portproxy and firewall: $_" }
            if ($lanStatus -ne 200) { throw "LAN endpoint returned HTTP $lanStatus at $url" }
        }
        Write-Host "LAN login: $lanUrl"
    }
    & $docker @compose ps
    Write-Host 'SUCCESS: Asteria is running with the existing images and data volumes.'
} finally {
    Pop-Location
}
