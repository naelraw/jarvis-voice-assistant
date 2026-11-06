# Configure la voix ElevenLabs de JARVIS.
# La clé API est chiffrée par Windows (DPAPI) pour ton compte uniquement.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Security

function Show-ApiError($err) {
    $code = $null
    try { $code = [int]$err.Exception.Response.StatusCode } catch {}
    $detail = $err.ErrorDetails.Message
    Write-Host "  Erreur $code renvoyee par ElevenLabs :" -ForegroundColor Red
    if ($detail) {
        try {
            $d = ($detail | ConvertFrom-Json).detail
            $msg = if ($d.message) { $d.message } else { "$d" }
            Write-Host "    $msg  [$($d.status)]" -ForegroundColor Red
            if ("$($d.status) $msg" -match 'unusual|vpn|proxy') {
                Write-Host "    -> ElevenLabs bloque le forfait gratuit via VPN : coupe Proton VPN et relance." -ForegroundColor Yellow
            }
            if ("$($d.status) $msg" -match 'permission') {
                Write-Host "    -> Il manque un droit a la cle : coche 'Text to Speech' (acces) et 'Voices' (lecture)." -ForegroundColor Yellow
            }
        } catch { Write-Host "    $detail" -ForegroundColor Red }
    } else {
        Write-Host "    $($err.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "  === Voix ElevenLabs pour JARVIS ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Sur la page qui va s'ouvrir, clique 'Create API key'."
Write-Host "  2. Droits a donner : 'Text to Speech' = Access, 'Voices' = Read (le reste peut rester bloque)."
Write-Host "  3. Copie la cle (elle commence par sk_) et colle-la ici (clic droit pour coller)."
Write-Host "  Si tu utilises un VPN (Proton VPN...), coupe-le : le forfait gratuit est bloque via VPN."
Write-Host ""
Read-Host "  Appuie sur Entree pour ouvrir la page des cles API"
Start-Process "https://elevenlabs.io/app/settings/api-keys"
Write-Host ""
$secure = Read-Host "  Colle ta cle API ElevenLabs" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)) -replace '[^\x21-\x7E]', '' }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if (-not $key.StartsWith('sk_')) {
    Write-Host "  Attention : la cle ne commence pas par 'sk_' ($($key.Length) caracteres). Verifie que tu as copie la bonne." -ForegroundColor Yellow
}
$headers = @{ "xi-api-key" = $key }

# --- Liste des voix (si la clé a le droit de les lire), sinon voix par défaut
$voices = @()
Write-Host ""
Write-Host "  Recuperation de tes voix..." -ForegroundColor Cyan
try {
    $voices = @((Invoke-RestMethod -Uri "https://api.elevenlabs.io/v1/voices" -Headers $headers).voices |
        ForEach-Object { [pscustomobject]@{ name = $_.name; voice_id = $_.voice_id
            desc = ((@($_.labels.gender, $_.labels.accent, $_.labels.description) | Where-Object { $_ }) -join ', ') +
                $(if ($_.category -and $_.category -notin @('premade', 'generated', 'cloned')) { ' - VOIX DE BIBLIOTHEQUE : abonnement payant requis' } else { '' }) } })
} catch {
    Show-ApiError $_
    Write-Host "  Je continue avec les voix par defaut d'ElevenLabs." -ForegroundColor Yellow
}
if ($voices.Count -eq 0) {
    $voices = @(
        [pscustomobject]@{ name = 'George';    voice_id = 'JBFqnCBsd6RMkjVDRZzb'; desc = 'homme, chaleureux, pose' },
        [pscustomobject]@{ name = 'Brian';     voice_id = 'nPczCjzI2devNBz1zQrb'; desc = 'homme, grave' },
        [pscustomobject]@{ name = 'Daniel';    voice_id = 'onwK4e9ZLuTAKqWW03F9'; desc = 'homme, presentateur' },
        [pscustomobject]@{ name = 'Charlotte'; voice_id = 'XB0fDUnXU5powFXDhCwa'; desc = 'femme' },
        [pscustomobject]@{ name = 'Alice';     voice_id = 'Xb7hH8MSUJpSbSDYk0k2'; desc = 'femme, claire' }
    )
}
# --- Choix : on écoute chaque voix en français avant de la garder
Add-Type -AssemblyName PresentationCore
$e = [char]0xE9; $ee = [char]0xE8
$sample = "Bonjour Na$([char]0xEB)l. Je suis Jarvis, ton assistant personnel. Tous les syst$($ee)mes sont op$($e)rationnels : que puis-je faire pour toi aujourd'hui ?"
$voice = $null
while (-not $voice) {
    Write-Host ""
    for ($i = 0; $i -lt $voices.Count; $i++) {
        Write-Host ("  {0,2}. {1}  ({2})" -f ($i + 1), $voices[$i].name, $voices[$i].desc)
    }
    Write-Host ""
    $choice = Read-Host "  Numero de la voix a ecouter (Entree = 5, George)"
    if (-not $choice) { $choice = 5 }
    $cand = $voices[[int]$choice - 1]
    Write-Host "  Ecoute de $($cand.name) en francais..." -ForegroundColor Cyan
    $body = @{ text = $sample; model_id = "eleven_flash_v2_5"; language_code = "fr" } | ConvertTo-Json
    $tmp = Join-Path $env:TEMP ("jarvis_eleven_{0}.mp3" -f (Get-Random))
    try {
        Invoke-WebRequest -UseBasicParsing -Method Post -Uri "https://api.elevenlabs.io/v1/text-to-speech/$($cand.voice_id)" `
            -Headers $headers -ContentType "application/json; charset=utf-8" `
            -Body ([Text.Encoding]::UTF8.GetBytes($body)) -OutFile $tmp
    } catch {
        Show-ApiError $_
        Write-Host "  Choisis une autre voix." -ForegroundColor Yellow
        continue
    }
    $player = New-Object System.Windows.Media.MediaPlayer
    $player.Open([Uri]$tmp)
    Start-Sleep -Milliseconds 400
    $player.Play()
    for ($w = 0; $w -lt 40 -and -not $player.NaturalDuration.HasTimeSpan; $w++) { Start-Sleep -Milliseconds 100 }
    $len = if ($player.NaturalDuration.HasTimeSpan) { $player.NaturalDuration.TimeSpan.TotalSeconds } else { 8 }
    Start-Sleep -Seconds ([Math]::Ceiling($len) + 0.5)
    $player.Close()
    Remove-Item $tmp -ErrorAction SilentlyContinue
    $keep = Read-Host "  Garder cette voix pour JARVIS ? (o = oui / Entree = en essayer une autre)"
    if ($keep -match '^[oOyY]') { $voice = $cand }
}
Write-Host "  Voix choisie : $($voice.name)" -ForegroundColor Green

$enc = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($key), $null, 'CurrentUser')
$key = $null
$out = Join-Path $env:USERPROFILE '.openjarvis\jarvis_elevenlabs.json'
@{
    key_dpapi  = [Convert]::ToBase64String($enc)
    voice_id   = $voice.voice_id
    voice_name = $voice.name
    model_id   = 'eleven_flash_v2_5'   # le plus rapide (~75 ms), multilingue
} | ConvertTo-Json | Set-Content -Path $out -Encoding UTF8

$toml = Join-Path $env:USERPROFILE '.openjarvis\jarvis_voice.toml'
if (Test-Path $toml) {
    $txt = [IO.File]::ReadAllText($toml)
    $txt = $txt -replace '(?m)^tts\s*=\s*"[^"]*"', 'tts = "elevenlabs"'
    [IO.File]::WriteAllText($toml, $txt, (New-Object Text.UTF8Encoding $false))
}
Write-Host ""
Write-Host "  C'est bon ! JARVIS parlera avec la voix $($voice.name)." -ForegroundColor Green
Write-Host "  Relance JARVIS (ferme sa fenetre ou Alt+F4, puis double-clique sur l'icone Jarvis)."
Write-Host ""
Read-Host "  Appuie sur Entree pour fermer"
