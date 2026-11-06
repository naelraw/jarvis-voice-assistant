# Configure Gemini (cerveau, ecoute et vision) pour JARVIS.
# La cle API est chiffree par Windows (DPAPI) pour ton compte uniquement.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Security
Write-Host ""
Write-Host "  === Gemini pour JARVIS ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Sur la page qui va s'ouvrir (Google AI Studio), clique 'Create API key'."
Write-Host "  2. Copie la cle (elle commence par AIza...) et colle-la ici (clic droit pour coller)."
Write-Host ""
Write-Host "  A savoir : avec la cle gratuite, Google peut utiliser tes echanges pour ameliorer ses modeles,"
Write-Host "  et le nombre de requetes par minute/jour est limite. Si la limite est atteinte,"
Write-Host "  JARVIS repasse tout seul sur le modele installe sur ton PC."
Write-Host ""
Read-Host "  Appuie sur Entree pour ouvrir Google AI Studio"
Start-Process "https://aistudio.google.com/apikey"
Write-Host ""
$secure = Read-Host "  Colle ta cle API Gemini" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)) -replace '[^\x21-\x7E]', '' }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

Write-Host ""
Write-Host "  Verification de la cle..." -ForegroundColor Cyan
try {
    $models = Invoke-RestMethod -Uri "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200" -Headers @{ "x-goog-api-key" = $key }
} catch {
    $detail = $_.ErrorDetails.Message
    Write-Host "  La cle est refusee : $($_.Exception.Message)" -ForegroundColor Red
    if ($detail) { try { Write-Host "    $((($detail | ConvertFrom-Json).error).message)" -ForegroundColor Red } catch { Write-Host "    $detail" } }
    $key = $null
    Read-Host "  Appuie sur Entree pour fermer"; exit 1
}
$flash = @($models.models | Where-Object { $_.name -match '^models/gemini-[\d.]+-flash(-lite)?$' } | ForEach-Object { $_.name -replace '^models/', '' })
Write-Host "  Cle valide. Modeles rapides disponibles : $($flash -join ', ')" -ForegroundColor Green

$enc = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($key), $null, 'CurrentUser')
$key = $null
$out = Join-Path $env:USERPROFILE '.openjarvis\jarvis_gemini.json'
@{ key_dpapi = [Convert]::ToBase64String($enc) } | ConvertTo-Json | Set-Content -Path $out -Encoding UTF8

$toml = Join-Path $env:USERPROFILE '.openjarvis\jarvis_voice.toml'
if (Test-Path $toml) {
    $txt = [IO.File]::ReadAllText($toml)
    if ($txt -notmatch '(?m)^llm\s*=') { $txt += "`r`nllm = `"auto`"                   # auto = Gemini si configure, sinon modele local`r`n" }
    $txt = $txt -replace '(?m)^llm\s*=\s*"[^"]*"', 'llm = "auto"'
    if ($txt -notmatch '(?m)^gemini_stt\s*=') { $txt += "gemini_stt = true              # Gemini transcrit tes demandes (rapide)`r`n" }
    [IO.File]::WriteAllText($toml, $txt, (New-Object Text.UTF8Encoding $false))
}
Write-Host ""
Write-Host "  C'est bon ! JARVIS utilisera Gemini pour comprendre, repondre et voir ton ecran." -ForegroundColor Green
Write-Host "  Relance JARVIS (Alt+F4 sur sa fenetre, puis double-clic sur l'icone Jarvis)."
Write-Host ""
Read-Host "  Appuie sur Entree pour fermer"
