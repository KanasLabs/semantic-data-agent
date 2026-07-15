param(
    [ValidateSet("Up", "Init", "Status", "Down", "Reset")]
    [string]$Action = "Up"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = Join-Path $ProjectRoot "infra\starrocks\docker-compose.yml"
$InitSql = Join-Path $ProjectRoot "infra\starrocks\init.sql"
$ConnectionFile = Join-Path $ProjectRoot "infra\starrocks\wren-connection.yml"
$ContainerName = "data-agent-starrocks"
$WrenBin = Join-Path $ProjectRoot ".venv-wren\Scripts\wren.exe"
$WrenPython = Join-Path $ProjectRoot ".venv-wren\python.exe"
$WrenHome = Join-Path $ProjectRoot "data\wren\home"
$WrenProject = Join-Path $ProjectRoot "data\wren\starrocks_mvp_wren_project"
$DockerConfig = Join-Path $env:TEMP "data-agent-mvp-docker-config"

New-Item -ItemType Directory -Path $DockerConfig -Force | Out-Null
$env:DOCKER_CONFIG = $DockerConfig
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"

function Assert-CommandSucceeded {
    param([string]$Description)

    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Wait-StarRocks {
    param([int]$TimeoutSeconds = 240)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $health = docker inspect --format "{{.State.Health.Status}}" $ContainerName 2>$null
        if ($LASTEXITCODE -eq 0 -and $health -eq "healthy") {
            return
        }
        Start-Sleep -Seconds 5
    }
    docker compose -f $ComposeFile logs --tail 80
    throw "StarRocks did not become healthy within $TimeoutSeconds seconds."
}

function Initialize-StarRocks {
    docker cp $InitSql "${ContainerName}:/tmp/data_agent_mvp_init.sql"
    Assert-CommandSucceeded "Copying StarRocks initialization SQL"
    docker exec $ContainerName mysql -h 127.0.0.1 -P 9030 -u root -e "source /tmp/data_agent_mvp_init.sql"
    Assert-CommandSucceeded "Initializing the StarRocks MVP database"
}

function Configure-Wren {
    if (-not (Test-Path $WrenBin)) {
        throw "Wren CLI not found: $WrenBin"
    }
    & $WrenPython -c "import MySQLdb" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'Wren StarRocks support requires mysqlclient. Run: .\.venv-wren\python.exe -m pip install "wrenai[mysql]==0.12.0"'
    }
    $env:WREN_HOME = $WrenHome
    $env:PYTHONIOENCODING = "utf-8"
    & $WrenBin profile add starrocks_mvp --from-file $ConnectionFile
    Assert-CommandSucceeded "Creating the Wren StarRocks profile"

    Push-Location $WrenProject
    try {
        & $WrenBin context validate
        Assert-CommandSucceeded "Validating the StarRocks Wren project"
        & $WrenBin context build
        Assert-CommandSucceeded "Building the StarRocks Wren project"
        & $WrenBin dry-run --sql "SELECT COUNT(*) AS order_count FROM orders"
        Assert-CommandSucceeded "Dry-running the StarRocks Wren query"
    }
    finally {
        Pop-Location
    }
}

function Show-Status {
    docker compose -f $ComposeFile ps
    docker exec $ContainerName mysql -h 127.0.0.1 -P 9030 -u root -D data_agent_mvp -e "SELECT COUNT(*) AS customer_count FROM customers; SELECT COUNT(*) AS order_count FROM orders;"
}

switch ($Action) {
    "Up" {
        docker compose -f $ComposeFile up -d
        Assert-CommandSucceeded "Starting StarRocks"
        Wait-StarRocks
        Initialize-StarRocks
        Configure-Wren
        Show-Status
    }
    "Init" {
        Wait-StarRocks
        Initialize-StarRocks
        Configure-Wren
        Show-Status
    }
    "Status" {
        Show-Status
    }
    "Down" {
        docker compose -f $ComposeFile down
        Assert-CommandSucceeded "Stopping StarRocks"
    }
    "Reset" {
        docker compose -f $ComposeFile down --volumes
        Assert-CommandSucceeded "Resetting StarRocks"
        docker compose -f $ComposeFile up -d
        Assert-CommandSucceeded "Starting StarRocks"
        Wait-StarRocks
        Initialize-StarRocks
        Configure-Wren
        Show-Status
    }
}
