$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "frontend"
$pythonCommand = (Get-Command python).Source
$npmCommand = (Get-Command npm.cmd).Source

function Test-TcpPort {
    param([string]$HostName, [int]$Port)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $task = $client.ConnectAsync($HostName, $Port)
        if (-not $task.Wait(500)) { $client.Dispose(); return $false }
        $connected = $client.Connected
        $client.Dispose()
        return $connected
    } catch {
        return $false
    }
}

$backend = $null
if (Test-TcpPort "127.0.0.1" 8001) {
    Write-Host "EchoMerch backend already running on 127.0.0.1:8001"
} else {
    $backend = Start-Process -FilePath $pythonCommand `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8001" `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $projectRoot "backend-dev-server.out.log") `
        -RedirectStandardError (Join-Path $projectRoot "backend-dev-server.err.log") `
        -PassThru
}

$frontend = $null
if (Test-TcpPort "127.0.0.1" 9568) {
    Write-Host "EchoMerch frontend already running on 127.0.0.1:9568"
} else {
    $frontend = Start-Process -FilePath $npmCommand `
        -ArgumentList "run", "dev", "--", "--host", "0.0.0.0", "--port", "9568", "--strictPort" `
        -WorkingDirectory $frontendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $frontendRoot "dev-server.out.log") `
        -RedirectStandardError (Join-Path $frontendRoot "dev-server.err.log") `
        -PassThru
}

if ($backend) { Write-Host "EchoMerch backend PID: $($backend.Id) (0.0.0.0:8001)" }
if ($frontend) { Write-Host "EchoMerch frontend PID: $($frontend.Id) (0.0.0.0:9568)" }
Write-Host "EchoMerch ready: http://127.0.0.1:9568/"
