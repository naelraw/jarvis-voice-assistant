# Connecte JARVIS a l'admin de PC Radar (lecture des donnees, comme la page /admin).
# Le secret admin est chiffre par Windows (DPAPI) pour ton compte uniquement.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Security
Write-Host ""
Write-Host "  === PC Radar pour JARVIS ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  JARVIS lira les donnees de ton admin (visites, tickets, prix suspects, catalogue, releve des prix)"
Write-Host "  pour te faire un recap. Il utilise le meme 'secret admin' que ton extension Chrome PC Radar"
Write-Host "  (celui que tu tapes pour te connecter a pcradar.tech/admin)."
Write-Host ""
$site = Read-Host "  Adresse du site (Entree = https://pcradar.tech)"
if (-not $site) { $site = 'https://pcradar.tech' }
$site = $site.Trim().TrimEnd('/')
$secure = Read-Host "  Colle ton secret admin" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $secret = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)).Trim() }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

Write-Host ""
Write-Host "  Verification..." -ForegroundColor Cyan
try {
    $stats = Invoke-RestMethod -Uri "$site/api/admin/stats" -Headers @{ "X-Admin-Secret" = $secret } -TimeoutSec 20
    $today = if ($stats.jours) { $stats.jours[-1].visiteurs } else { '?' }
    Write-Host "  Connexion OK : $today visiteur(s) aujourd'hui sur PC Radar." -ForegroundColor Green
} catch {
    Write-Host "  Refuse : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Verifie le secret admin (le meme que dans l'extension) puis relance."
    $secret = $null
    Read-Host "  Appuie sur Entree pour fermer"; exit 1
}
$enc = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($secret), $null, 'CurrentUser')
$secret = $null
$out = Join-Path $env:USERPROFILE '.openjarvis\jarvis_pcradar.json'
@{ site = $site; secret_dpapi = [Convert]::ToBase64String($enc) } | ConvertTo-Json | Set-Content -Path $out -Encoding UTF8
Write-Host ""
Write-Host "  C'est bon ! JARVIS inclura PC Radar dans ton recap (double claquement ou 'Jarvis, quoi de neuf sur PC Radar ?')." -ForegroundColor Green
Write-Host ""
Read-Host "  Appuie sur Entree pour fermer"
