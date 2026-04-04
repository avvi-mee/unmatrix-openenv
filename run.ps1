# run.ps1 — Start Peer Review Arena locally and run smoke tests
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$env:PYTHONPATH = "."

Write-Host "Starting uvicorn server..." -ForegroundColor Cyan
$server = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "server.app:app",
    "--host", "0.0.0.0", "--port", "8000", "--workers", "1" `
    -PassThru -NoNewWindow

Write-Host "Waiting for server to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

try {
    # Health check
    Write-Host "`n--- Health Check ---" -ForegroundColor Green
    $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
    Write-Host ($health | ConvertTo-Json)

    # Reset agent A
    Write-Host "`n--- Reset Agent A ---" -ForegroundColor Green
    $resetA = Invoke-RestMethod -Uri "http://localhost:8000/reset" -Method Post `
        -ContentType "application/json" `
        -Body '{"episode_id":"smoke_test","task":"bug_hunt","agent_id":"A","seed":42}'
    Write-Host "Phase: $($resetA.observation.phase)"
    Write-Host "Task:  $($resetA.observation.task_name)"
    Write-Host "Files: $($resetA.observation.files_available -join ', ')"

    # Reset agent B
    Write-Host "`n--- Reset Agent B ---" -ForegroundColor Green
    $resetB = Invoke-RestMethod -Uri "http://localhost:8000/reset" -Method Post `
        -ContentType "application/json" `
        -Body '{"episode_id":"smoke_test","task":"bug_hunt","agent_id":"B","seed":42}'
    Write-Host "Phase: $($resetB.observation.phase)"

    # Get state
    Write-Host "`n--- State ---" -ForegroundColor Green
    $stateResp = Invoke-RestMethod -Uri "http://localhost:8000/state?episode_id=smoke_test&agent_id=A" -Method Get
    Write-Host ($stateResp | ConvertTo-Json)

    Write-Host "`nSmoke tests passed!" -ForegroundColor Green

} finally {
    Write-Host "`nStopping server..." -ForegroundColor Yellow
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
