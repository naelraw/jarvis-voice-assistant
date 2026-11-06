# Permet a JARVIS d'ouvrir OBS (regle "en administrateur") au debut d'une partie, sans fenetre de confirmation.
# A lancer UNE fois : clic droit > "Executer avec PowerShell" ; Windows demande une seule fois l'autorisation.
# Cree la tache planifiee "JARVIS - OBS" (droits les plus eleves, uniquement pour ton compte, aucun declencheur :
# elle ne se lance que quand JARVIS la demande). Pour la retirer : Planificateur de taches > supprimer "JARVIS - OBS".
$ErrorActionPreference = 'Stop'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
$obs = Join-Path $env:ProgramFiles 'obs-studio\bin\64bit\obs64.exe'
if (-not (Test-Path $obs)) { Write-Host "OBS Studio introuvable ($obs)." -ForegroundColor Red; Read-Host "Entree pour fermer"; exit 1 }
$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $obs -Argument '--minimize-to-tray --disable-shutdown-check --disable-updater --startreplaybuffer' -WorkingDirectory (Split-Path $obs)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName 'JARVIS - OBS' -Action $action -Principal $principal -Settings $settings -Force | Out-Null
Write-Host ""
Write-Host "  C'est fait : JARVIS peut maintenant ouvrir OBS (en administrateur) au debut de tes parties." -ForegroundColor Green
Read-Host "  Entree pour fermer"
