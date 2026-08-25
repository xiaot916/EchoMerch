$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "frontend"
$pythonCommand = (Get-Command python).Source
$npmCommand = (Get-Command npm.cmd).Source

$backend = Start-Process -FilePath $pythonCommand `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8001" `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $projectRoot "backend-dev-server.out.log") `
    -RedirectStandardError (Join-Path $projectRoot "backend-dev-server.err.log") `
    -PassThru

$frontend = Start-Process -FilePath $npmCommand `
    -ArgumentList "run", "dev", "--", "--host", "0.0.0.0", "--port", "5174", "--strictPort" `
    -WorkingDirectory $frontendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $frontendRoot "dev-server.out.log") `
    -RedirectStandardError (Join-Path $frontendRoot "dev-server.err.log") `
    -PassThru

Write-Host "EchoMerch backend PID: $($backend.Id) (0.0.0.0:8001)"
Write-Host "EchoMerch frontend PID: $($frontend.Id) (0.0.0.0:5174)"
