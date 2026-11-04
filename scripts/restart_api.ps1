$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskRuntime = Join-Path $taskRoot 'data\runtime'
$taskManifest = Join-Path $taskRuntime 'servers.json'
$taskEntries = @(Get-Content -Raw -LiteralPath $taskManifest | ConvertFrom-Json)
$taskEntry = $taskEntries | Where-Object { $_.name -eq 'api' }
if (-not $taskEntry) { throw 'No project API process record exists.' }
$taskProcess = Get-Process -Id $taskEntry.pid -ErrorAction SilentlyContinue
if ($taskProcess) {
    $taskExpectedTime = ([DateTime]$taskEntry.started_at).ToUniversalTime()
    if ($taskProcess.StartTime.ToUniversalTime() -ne $taskExpectedTime -or $taskProcess.Path -ne $taskPython) {
        throw 'Process identity changed; refusing to stop it.'
    }
    # A Windows venv launcher owns a base-Python child. Validate every child before stopping any.
    $taskHomeLine = Get-Content -LiteralPath (Join-Path $taskRoot '.venv\pyvenv.cfg') | Where-Object { $_ -match '^home\s*=' }
    $taskBasePython = [IO.Path]::GetFullPath((Join-Path (($taskHomeLine -split '=',2)[1].Trim()) 'python.exe'))
    $taskChildren = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($taskProcess.Id)" -ErrorAction Stop)
    $taskVerifiedChildren = @()
    foreach ($taskChild in $taskChildren) {
        $taskLiveChild = Get-Process -Id $taskChild.ProcessId -ErrorAction Stop
        if ($taskLiveChild.Path -ne $taskBasePython -or $taskLiveChild.StartTime -lt $taskProcess.StartTime -or $taskChild.CommandLine -notmatch '(?i)\s-m\s+uvicorn\s+app\.main:app\s+--host\s+127\.0\.0\.1\s+--port\s+8000\s*$') {
            throw 'Unexpected child process; refusing to stop the API process tree.'
        }
        $taskVerifiedChildren += $taskLiveChild
    }
    foreach ($taskChild in $taskVerifiedChildren) {
        Stop-Process -Id $taskChild.Id -ErrorAction Stop
        $taskChild.WaitForExit(10000) | Out-Null
    }
    if (-not $taskProcess.HasExited) { Stop-Process -Id $taskProcess.Id -ErrorAction Stop }
    $taskProcess.WaitForExit(10000) | Out-Null
}
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8000 is occupied by an untracked process; it was preserved. Stop it in its original terminal.'
}
$taskReplacement = Start-Process -FilePath $taskPython -WorkingDirectory $taskRoot -WindowStyle Hidden -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -PassThru -RedirectStandardOutput (Join-Path $taskRuntime 'api.stdout.log') -RedirectStandardError (Join-Path $taskRuntime 'api.stderr.log')
$taskEntry.pid = $taskReplacement.Id
$taskEntry.started_at = $taskReplacement.StartTime.ToString('o')
$taskEntries | ConvertTo-Json | Set-Content -LiteralPath $taskManifest -Encoding utf8
Write-Output 'MatPilot project API restarted; UI process preserved.'
