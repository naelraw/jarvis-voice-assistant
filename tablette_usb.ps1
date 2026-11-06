# Tablette Android reliee au PC PAR LE CABLE USB (reseau USB), pour Artemis / Apollo sans Wi-Fi.
# La Tab A (modele Wi-Fi) n'affiche pas "Modem USB" : on l'active par ADB (debogage USB active sur la tablette).
# A relancer apres avoir debranche la tablette ou l'avoir redemarree.
$ErrorActionPreference = 'SilentlyContinue'
$adb = Join-Path $env:USERPROFILE 'OpenJarvis\outils\platform-tools\adb.exe'
if (-not (Test-Path $adb)) { Write-Host "Outil ADB introuvable ($adb)." -ForegroundColor Red; Read-Host "Entree pour fermer"; exit 1 }
& $adb start-server | Out-Null
$dev = (& $adb devices) -match "`tdevice$"
if (-not $dev) {
    Write-Host "Tablette non trouvee : branche-la en USB, deverrouille-la et accepte 'Autoriser le debogage USB'." -ForegroundColor Yellow
    Read-Host "Entree pour fermer"; exit 1
}
& $adb shell svc usb setFunctions rndis | Out-Null
Write-Host "Reseau USB active, attente de l'adresse..."
$ip = $null
for ($i = 0; $i -lt 20 -and -not $ip; $i++) {
    Start-Sleep 1
    $nic = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'Remote NDIS' -and $_.Status -eq 'Up' } | Select-Object -First 1
    if ($nic) { $ip = (Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^169\.' }).IPAddress }
}
if ($ip) {
    Write-Host ""
    Write-Host "  C'est bon : la tablette est reliee par le cable." -ForegroundColor Green
    Write-Host "  Dans Artemis, coupe le Wi-Fi de la tablette ; si le PC n'apparait pas, ajoute-le avec '+' :"
    Write-Host "      $ip" -ForegroundColor Cyan
} else {
    Write-Host "Le reseau USB ne s'est pas active (rebranche le cable et relance)." -ForegroundColor Red
}
Read-Host "Entree pour fermer"
