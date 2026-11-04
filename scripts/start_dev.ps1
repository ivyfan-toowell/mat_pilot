$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskLogs = Join-Path $taskRoot 'data\runtime'
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
$taskServers = @()
foreach ($taskServer in @(
    @{ Name='api'; Port=8000; Args=@('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') },
    @{ Name='ui'; Port=8501; Args=@('-m','streamlit','run','ui/app.py','--server.address','127.0.0.1','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false') }
)) {
    $taskListener = Get-NetTCPConnection -LocalPort $taskServer.Port -State Listen -ErrorAction SilentlyContinue
    if ($taskListener) { throw "Port $($taskServer.Port) is already in use; existing process was preserved." }
    $taskProcess = Start-Process -FilePath $taskPython -WorkingDirectory $taskRoot -WindowStyle Hidden -ArgumentList $taskServer.Args -PassThru -RedirectStandardOutput (Join-Path $taskLogs "$($taskServer.Name).stdout.log") -RedirectStandardError (Join-Path $taskLogs "$($taskServer.Name).stderr.log")
    $taskServers += @{ name=$taskServer.Name; pid=$taskProcess.Id; port=$taskServer.Port; started_at=$taskProcess.StartTime.ToString('o') }
}
$taskServers | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskLogs 'servers.json') -Encoding utf8
Write-Output 'MatPilot starting: API http://127.0.0.1:8000 ; UI http://127.0.0.1:8501'
