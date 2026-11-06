# Configure VirusTotal (gratuit) pour JARVIS : verifier un fichier, un lien ou un domaine.
# La cle API est chiffree par Windows (DPAPI) pour ton compte uniquement.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Security
Write-Host ""
Write-Host "  === VirusTotal pour JARVIS ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Sur la page qui va s'ouvrir, cree un compte gratuit (ou connecte-toi)."
Write-Host "  2. Ouvre ton profil > 'API Key' et copie la cle (longue suite de lettres et chiffres)."
Write-Host ""
Write-Host "  A savoir : gratuit = 4 verifications par minute, 500 par jour. JARVIS n'envoie JAMAIS tes fichiers :"
Write-Host "  seulement leur empreinte (un code), donc rien de prive ne part."
Write-Host ""
Read-Host "  Appuie sur Entree pour ouvrir VirusTotal"
Start-Process "https://www.virustotal.com/gui/my-apikey"
Write-Host ""
$secure = Read-Host "  Colle ta cle API VirusTotal" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)) -replace '[^\x21-\x7E]', '' }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

Write-Host ""
Write-Host "  Verification de la cle..." -ForegroundColor Cyan
try {
    # fichier de test EICAR (inoffensif, connu de tous les antivirus)
    $r = Invoke-RestMethod -Uri "https://www.virustotal.com/api/v3/files/275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f" -Headers @{ "x-apikey" = $key }
} catch {
    Write-Host "  La cle est refusee : $($_.Exception.Message)" -ForegroundColor Red
    $key = $null
    Read-Host "  Appuie sur Entree pour fermer"; exit 1
}
Write-Host "  Cle valide." -ForegroundColor Green

$enc = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($key), $null, 'CurrentUser')
$key = $null
$out = Join-Path $env:USERPROFILE '.openjarvis\jarvis_virustotal.json'
@{ key_dpapi = [Convert]::ToBase64String($enc) } | ConvertTo-Json | Set-Content -Path $out -Encoding UTF8
Write-Host ""
Write-Host "  C'est bon ! Dis par exemple : 'Jarvis, ce fichier est sur ?'" -ForegroundColor Green
Write-Host "  Relance JARVIS pour que ce soit pris en compte."
Write-Host ""
Read-Host "  Appuie sur Entree pour fermer"
