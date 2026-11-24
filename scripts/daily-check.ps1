<#
  The 7 AM daily review (read and suggest only).

  powershell -File scripts\daily-check.ps1            run it once now
  powershell -File scripts\daily-check.ps1 -Install   every day at 07:00 (or -At 08:30)
  powershell -File scripts\daily-check.ps1 -Uninstall
  powershell -File scripts\daily-check.ps1 -Status

  The headless run can never change the account: the Apply tool's write tools are disallowed on the
  command line, and nothing is on "allow" for apply_change anyway (it is "ask", and nobody is there).
#>
param([switch]$Install, [switch]$Uninstall, [switch]$Status, [string]$At = "07:00")

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$TaskName = "CaughtLeads Ads daily review"
$LogDir = Join-Path $Repo "log"

if ($Install) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -WorkingDirectory $Repo
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
        -Principal $principal -Force | Out-Null
    Write-Output "Installed: '$TaskName' runs every day at $At (read and suggest only)."
    exit 0
}
if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed: '$TaskName'."
    exit 0
}
if ($Status) {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) { Write-Output "On: '$TaskName' ($($t.State)). Next run: $((Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime)" }
    else { Write-Output "Off: the daily check is not installed." }
    exit 0
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "daily-review.log"
Set-Location $Repo
"$(Get-Date -Format s)  start" | Out-File -Append -Encoding utf8 $Log
$readTools = "Read,Write,Glob,Grep,Task,Bash(uv run --no-project --quiet python tools/inbox.py:*)," +
             "mcp__google-ads__search_search,mcp__google-ads__metadata_get_resource_metadata," +
             "mcp__google-ads__customers_list_accessible_customers,mcp__apply__preview_change"
$blocked = "mcp__apply__apply_change,mcp__apply__pause_campaigns,mcp__apply__undo_change"
& claude -p "/daily-review" --allowedTools $readTools --disallowedTools $blocked 2>&1 |
    Out-File -Append -Encoding utf8 $Log
"$(Get-Date -Format s)  end exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 $Log
exit $LASTEXITCODE
