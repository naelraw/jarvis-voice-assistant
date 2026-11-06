# Connecte JARVIS a ton Google Agenda (lecture + ajout + suppression) via un petit script Google.
# Le code secret et l'adresse du script sont chiffres par Windows (DPAPI) pour ton compte uniquement.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Code secret aleatoire, insere dans le script Google
$bytes = New-Object byte[] 24
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = [Convert]::ToBase64String($bytes).Replace('+', 'A').Replace('/', 'B').TrimEnd('=')
$code = (Get-Content (Join-Path $here 'agenda_jarvis.gs') -Raw -Encoding UTF8).Replace('__TOKEN__', $token)
Set-Clipboard -Value $code

Write-Host ""
Write-Host "  === Connecter Google Agenda a JARVIS ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Le code du script est DEJA COPIE (presse-papiers). Une page Google Apps Script va s'ouvrir :"
Write-Host ""
Write-Host "   1. Connecte-toi avec le compte Google de ton agenda."
Write-Host "   2. Efface le code deja present (Ctrl+A puis Suppr) et COLLE le code (Ctrl+V)."
Write-Host "   3. Clique sur l'icone disquette (Enregistrer). Nom du projet : Jarvis Agenda."
Write-Host "   4. En haut a droite : 'Deployer' > 'Nouveau deploiement'."
Write-Host "      - Roue dentee 'Selectionner le type' : 'Application Web'"
Write-Host "      - Executer en tant que : 'Moi'"
Write-Host "      - Qui peut acceder : 'Tout le monde'  (protege par le code secret)"
Write-Host "   5. 'Deployer' > 'Autoriser l'acces' > choisis ton compte."
Write-Host "      Si Google affiche 'Application non validee' : 'Parametres avances' > 'Acceder a Jarvis Agenda'."
Write-Host "   6. Copie l'adresse 'Application Web' (elle finit par /exec)."
Write-Host ""
Read-Host "  Appuie sur Entree pour ouvrir Google Apps Script"
Start-Process "https://script.new"
Write-Host ""
$url = (Read-Host "  Colle ici l'adresse de l'application Web (finit par /exec)").Trim()

Write-Host ""
Write-Host "  Test de la connexion..." -ForegroundColor Cyan
$body = @{ token = $token; action = 'list'; start = (Get-Date).ToString('o'); end = (Get-Date).AddDays(7).ToString('o') } | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Uri $url -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 30
} catch {
    Write-Host "  Echec : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Verifie l'adresse (finit par /exec) et que l'acces est bien 'Tout le monde', puis relance."
    Read-Host "  Appuie sur Entree pour fermer"; exit 1
}
if (-not $r.ok) {
    Write-Host "  Le script repond mais refuse : $($r.error)" -ForegroundColor Red
    Write-Host "  As-tu bien colle le code copie par CE script (avec son code secret) ? Relance pour recommencer."
    Read-Host "  Appuie sur Entree pour fermer"; exit 1
}
Write-Host "  Connexion OK : $(@($r.events).Count) rendez-vous dans les 7 prochains jours." -ForegroundColor Green

$enc = [Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($token), $null, 'CurrentUser'))
$out = Join-Path $env:USERPROFILE '.openjarvis\jarvis_calendar.json'
@{ url = $url; token_dpapi = $enc } | ConvertTo-Json | Set-Content -Path $out -Encoding UTF8
$token = $null
Set-Clipboard -Value ' '
Write-Host ""
Write-Host "  C'est bon ! JARVIS peut lire, ajouter et supprimer tes rendez-vous." -ForegroundColor Green
Write-Host "  Essaie : 'Jarvis, ajoute dentiste mardi a 15h' ou 'qu'est-ce que j'ai demain ?'"
Write-Host ""
Read-Host "  Appuie sur Entree pour fermer"
