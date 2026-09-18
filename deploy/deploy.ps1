param(
    [switch]$BuildOnly,
    [switch]$Pull
)

$ErrorActionPreference = "Stop"
$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $DeployDir ".env"
$ExampleFile = Join-Path $DeployDir ".env.example"

if (-not (Test-Path $EnvFile)) {
    Copy-Item $ExampleFile $EnvFile
    Write-Host "Created deploy/.env from deploy/.env.example. Review secrets before production use."
}

$compose = @("compose", "--env-file", $EnvFile, "-f", (Join-Path $DeployDir "docker-compose.yml"))

if ($Pull) {
    docker @compose pull
}

if ($BuildOnly) {
    docker @compose build
    exit 0
}

docker @compose up -d --build
docker @compose ps
