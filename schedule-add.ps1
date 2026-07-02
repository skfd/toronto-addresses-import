$taskName  = "kk-toronto-import"
$projectDir = $PSScriptRoot
$logFile    = "$projectDir\logs\scheduler.log"

if (-not (Test-Path "$projectDir\logs")) {
    New-Item -ItemType Directory -Path "$projectDir\logs" | Out-Null
}

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c cd /d `"$projectDir`" && python run.py update >> `"$logFile`" 2>&1"

# 12:30 (after ontario-address-changes' 12:00 run). run.py update pulls toronto
# through address-vault with wait=True, so if the noon run is still fetching the
# ~590 MB file this coalesces onto it instead of pulling a second copy cold.
$trigger  = New-ScheduledTaskTrigger -Daily -At "12:30"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force

Write-Host "Scheduled '$taskName' to run daily at 12:30 PM."
Write-Host "Log: $logFile"
