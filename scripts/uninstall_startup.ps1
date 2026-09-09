$ErrorActionPreference = "Stop"

$taskName = "Copilot Usage Monitor"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($null -eq $task) {
    Write-Host "등록된 자동 시작 작업이 없습니다: $taskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host "자동 시작 작업을 제거했습니다: $taskName"
