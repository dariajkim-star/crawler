# 주간 리포트 작업을 콘솔 창 없는 런처로 교체한다.
# 관리자 권한 PowerShell에서 실행할 것. (현재 작업이 관리자 권한으로 등록돼 있어 일반 권한으로는 수정 불가)

$ErrorActionPreference = "Stop"
$wd  = "C:\Users\s0506\OneDrive\바탕 화면\GitHub_Projects\crawler"
$vbs = "$wd\scriptsun_weekly_hidden.vbs"

if (-not (Test-Path $vbs)) { throw "런처를 찾을 수 없습니다: $vbs" }

$action  = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`"" -WorkingDirectory $wd
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 09:00
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
             -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
             -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName "JobScope_Weekly_Report" -Action $action -Trigger $trigger -Settings $set -Force | Out-Null

$t = Get-ScheduledTask -TaskName "JobScope_Weekly_Report"
$i = Get-ScheduledTaskInfo -TaskName "JobScope_Weekly_Report"
Write-Host ""
Write-Host "교체 완료"
Write-Host ("  실행    : {0} {1}" -f $t.Actions[0].Execute, $t.Actions[0].Arguments)
Write-Host ("  다음실행: {0}" -f $i.NextRunTime)
Write-Host ("  놓치면 켤 때 실행: {0}" -f $t.Settings.StartWhenAvailable)
