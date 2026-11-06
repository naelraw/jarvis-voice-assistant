# Configure l'API YouTube (gratuite) pour JARVIS : choix exact des videos, infos (titre, chaine, vues, date).
# La cle API est chiffree par Windows (DPAPI) pour ton compte uniquement.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Security
Write-Host ""
Write-Host "  === API YouTube pour JARVIS ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  La cle Gemini ne marche PAS pour YouTube : il faut une cle a part (gratuite, 100 recherches par jour)."
Write-Host ""
Write-Host "  Etapes (Google Cloud Console, une seule fois) :"
Write-Host "   1. Page 1 : cree un projet (bouton en haut > Nouveau projet > nom : JARVIS)."
Write-Host "   2. Page 2 : clique 'Activer' pour 'YouTube Data API v3'."
Write-Host "   3. Page 3 : 'Creer des identifiants' > 'Cle API', copie la cle (elle commence par AIza...)."
Write-Host ""
Read-Host "  Appuie sur Entree pour ouvrir la page 1"
Start-Process "https://console.cloud.google.com/projectcreate"
Read-Host "  Projet cree ? Entree pour la page 2"
Start-Process "https://console.cloud.google.com/apis/library/youtube.googleapis.com"
Read-Host "  API activee ? Entree pour la page 3"
Start-Process "https://console.cloud.google.com/apis/credentials"
Write-Host ""
$secure = Read-Host "  Colle ta cle API YouTube" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)) -replace '[^\x21-\x7E]', '' }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

Write-Host ""
Write-Host "  Verification de la cle..." -ForegroundColor Cyan
try {
    $r = Invoke-RestMethod -Uri "https://www.googleapis.com/youtube/v3/search?part=snippet&q=test&maxResults=1&type=video&key=$key"
} catch {
    $detail = $_.ErrorDetails.Message
    Write-Host "  La cle est refusee : $($_.Exception.Message)" -ForegroundColor Red
    if ($detail) { try { Write-Host "    $((($detail | ConvertFrom-Json).error).message)" -ForegroundColor Red } catch {} }
    Write-Host "  (verifie que 'YouTube Data API v3' est bien activee sur le projet de la cle)"
    $key = $null
    Read-Host "  Appuie sur Entree pour fermer"; exit 1
}
Write-Host "  Cle valide." -ForegroundColor Green

$enc = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($key), $null, 'CurrentUser')
$key = $null
$out = Join-Path $env:USERPROFILE '.openjarvis\jarvis_youtube.json'
@{ key_dpapi = [Convert]::ToBase64String($enc) } | ConvertTo-Json | Set-Content -Path $out -Encoding UTF8
Write-Host ""
Write-Host "  C'est bon ! JARVIS choisira mieux les videos et pourra te donner leurs infos." -ForegroundColor Green
Write-Host "  Relance JARVIS pour que ce soit pris en compte."
Write-Host ""
Read-Host "  Appuie sur Entree pour fermer"
