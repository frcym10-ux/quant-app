# スイング候補レポートの定期公開タスクを登録する（管理者権限不要）
# 平日 朝7:00（寄り前の選定用）と 夕方16:30（引け後の選定用）に実行
# 解除する場合:
#   Unregister-ScheduledTask -TaskName "SwingScan-Morning" -Confirm:$false
#   Unregister-ScheduledTask -TaskName "SwingScan-Evening" -Confirm:$false

$action = New-ScheduledTaskAction -Execute "H:\quant-app\tools\publish.bat"
$days = "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"

$tm = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 07:00
Register-ScheduledTask -TaskName "SwingScan-Morning" -Action $action -Trigger $tm -Force

$te = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 16:30
Register-ScheduledTask -TaskName "SwingScan-Evening" -Action $action -Trigger $te -Force

Write-Host "登録完了: SwingScan-Morning (平日7:00) / SwingScan-Evening (平日16:30)"
