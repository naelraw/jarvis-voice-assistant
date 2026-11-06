# Configure Groq (secours gratuit quand Gemini ne repond pas) pour JARVIS.
# La cle API est chiffree par Windows (DPAPI) pour ton compte uniquement.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Security
Write-Host ""
Write-Host "  === Groq pour JARVIS (secours) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Sur la page qui va s'ouvrir (console Groq), connecte-toi puis clique 'Create API Key'."
Write-Host "  2. Copie la cle (elle commence par gsk_...) et colle-la ici (clic droit pour coller)."
Write-Host ""
Write-Host "  A savoir : la cle gratuite a un nombre de requetes limite. JARVIS ne s'en sert que si Gemini"
Write-Host "  ne repond pas (quota atteint, panne)."
Write-Host ""
Read-Host "  Appuie sur Entree pour ouvrir la console Groq"
Start-Process "https://console.groq.com/keys"
Write-Host ""
$secure = Read-Host "  Colle ta cle API Groq" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)) -replace '[^\x21-\x7E]', '' }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

Write-Host ""
Write-Host "  Verification de la cle..." -ForegroundColor Cyan
try {
    $models = Invoke-RestMethod -Uri "https://api.groq.com/openai/v1/models" -Headers @{ "Authorization" = "Bearer $key" }
} catch {
    Write-Host "  La cle est refusee : $($_.Exception.Message)" -ForegroundColor Red
    $key = $null
    Read-Host "  Appuie sur Entree pour fermer"; exit 1
}
$ids = @($models.data | ForEach-Object { $_.id })
# JARVIS choisit seul le meilleur modele de discussion disponible (GROQ_PREFER dans jarvis_voice.py)
$chat = @('openai/gpt-oss-120b', 'qwen/qwen3.8-27b', 'openai/gpt-oss-20b') | Where-Object { $ids -contains $_ }
Write-Host ("  Cle valide. Discussion : {0} ; voix : {1}" -f $(if ($chat) { $chat[0] } else { 'choisi par JARVIS' }), $(if ($ids -contains 'whisper-large-v3-turbo') { 'whisper-large-v3-turbo' } else { 'absent' })) -ForegroundColor Green

$enc = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($key), $null, 'CurrentUser')
$key = $null
$out = Join-Path $env:USERPROFILE '.openjarvis\jarvis_groq.json'
@{ key_dpapi = [Convert]::ToBase64String($enc) } | ConvertTo-Json | Set-Content -Path $out -Encoding UTF8
Write-Host ""
Write-Host "  C'est bon ! Si Gemini ne repond pas, JARVIS passera par Groq." -ForegroundColor Green
Write-Host "  Relance JARVIS (bouton Pause puis fermer la fenetre, ou redemarre le PC)."
Write-Host ""
Read-Host "  Appuie sur Entree pour fermer"
