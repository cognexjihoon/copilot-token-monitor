$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$mainScript = Join-Path $projectRoot "main.py"
$taskName = "Copilot Usage Monitor"

if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw "가상 환경을 찾을 수 없습니다: $pythonExecutable`n먼저 README.md의 설치 절차를 실행하세요."
}

if (-not (Test-Path -LiteralPath $mainScript -PathType Leaf)) {
    throw "실행 파일을 찾을 수 없습니다: $mainScript"
}

$action = New-ScheduledTaskAction `
    -Execute $pythonExecutable `
    -Argument "`"$mainScript`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "자동 시작 작업을 등록했습니다: $taskName"
Write-Host "다음 로그온부터 $mainScript 를 실행합니다."
