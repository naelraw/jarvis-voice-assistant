# Cree la tache "JARVIS - tablette" : la tablette devient le 2e ecran DES L'ALLUMAGE DU PC (avant l'ecran de
# connexion). A lancer une fois ; Windows demande l'autorisation (administrateur). Pour l'enlever :
#   Unregister-ScheduledTask -TaskName 'JARVIS - tablette' -Confirm:$false
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
$script = Join-Path $PSScriptRoot 'tablette_auto.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName 'JARVIS - tablette' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'JARVIS - tablette'
Write-Host "Tache 'JARVIS - tablette' creee : la tablette s'allumera des le demarrage du PC." -ForegroundColor Green
Start-Sleep 3
