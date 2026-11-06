# Ajoute une boite mail a JARVIS (perso, contact PC Radar, ...).
# Le mot de passe est chiffre par Windows (DPAPI) pour ton compte uniquement.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$accFile = Join-Path $env:USERPROFILE '.openjarvis\jarvis_mail_accounts.json'
$accounts = @()
# PowerShell 5.1 : ConvertFrom-Json renvoie la liste d'un bloc ; ForEach-Object la déroule (sinon elle est emballée
# une 2e fois et réenregistrée en {"value": [...], "Count": n}, ce qui cassait JARVIS) ; anciens fichiers abîmés réparés
if (Test-Path $accFile) {
  $accounts = @((Get-Content $accFile -Raw -Encoding UTF8 | ConvertFrom-Json) | ForEach-Object { $_ } |
    ForEach-Object { if ($_.PSObject.Properties.Name -contains 'value' -and -not $_.email) { $_.value } else { $_ } } |
    Where-Object { $_.email })
}

Write-Host ""
Write-Host "  === Ajouter une boite mail a JARVIS ===" -ForegroundColor Cyan
if ($accounts.Count) { Write-Host "  Deja configurees : $(($accounts | % { "$($_.label) ($($_.email))" }) -join ', ')" }
Write-Host ""
$email = (Read-Host "  Adresse mail a ajouter").Trim()
$label = (Read-Host "  Petit nom pour cette boite (ex : perso, pcradar)").Trim()
if (-not $label) { $label = ($email -split '@')[0] }
$domain = ($email -split '@')[1].ToLower()

# --- Serveurs : detection automatique des hebergeurs courants
$presets = [ordered]@{
    '1' = @{ name = 'Gmail / Google Workspace'; imap = 'imap.gmail.com';        smtp = 'smtp.gmail.com';        port = 465; sec = 'ssl' }
    '2' = @{ name = 'Outlook / Hotmail / Microsoft 365'; imap = 'outlook.office365.com'; smtp = 'smtp.office365.com'; port = 587; sec = 'starttls' }
    '3' = @{ name = 'OVH';                      imap = 'ssl0.ovh.net';          smtp = 'ssl0.ovh.net';          port = 465; sec = 'ssl' }
    '4' = @{ name = 'Hostinger';                imap = 'imap.hostinger.com';    smtp = 'smtp.hostinger.com';    port = 465; sec = 'ssl' }
    '5' = @{ name = 'IONOS';                    imap = 'imap.ionos.fr';         smtp = 'smtp.ionos.fr';         port = 465; sec = 'ssl' }
    '6' = @{ name = 'Zoho';                     imap = 'imap.zoho.eu';          smtp = 'smtp.zoho.eu';          port = 465; sec = 'ssl' }
    '7' = @{ name = "o2switch / cPanel (mail.$domain)"; imap = "mail.$domain"; smtp = "mail.$domain";      port = 465; sec = 'ssl' }
}
$auto = $null
if ($domain -eq 'gmail.com') { $auto = '1' }
elseif ($domain -match '^(outlook|hotmail|live|msn)\.') { $auto = '2' }
else {
    try {
        $mx = (Resolve-DnsName -Type MX $domain -ErrorAction Stop | ? { $_.NameExchange } | Select -First 1).NameExchange.ToLower()
        if ($mx -match 'google') { $auto = '1' } elseif ($mx -match 'outlook|protection\.outlook') { $auto = '2' }
        elseif ($mx -match 'ovh') { $auto = '3' } elseif ($mx -match 'hostinger') { $auto = '4' }
        elseif ($mx -match 'ionos|1and1|kundenserver') { $auto = '5' } elseif ($mx -match 'zoho') { $auto = '6' }
        elseif ($mx -match 'o2switch') { $auto = '7' }
        Write-Host "  Serveur mail detecte pour $domain : $mx"
    } catch {}
}
Write-Host ""
foreach ($k in $presets.Keys) { Write-Host ("  {0}. {1}" -f $k, $presets[$k].name) }
Write-Host "  8. Autre (je tape les serveurs moi-meme)"
$def = if ($auto) { $auto } else { '1' }
$c = Read-Host "  Hebergeur de cette boite (Entree = $def, $($presets[$def].name))"
if (-not $c) { $c = $def }
if ($c -eq '8') {
    $imapHost = Read-Host "  Serveur IMAP (ex : imap.monhebergeur.com)"
    $smtpHost = Read-Host "  Serveur SMTP (ex : smtp.monhebergeur.com)"
    $p = Read-Host "  Port SMTP (465 = SSL, 587 = STARTTLS ; Entree = 465)"
    $smtpPort = if ($p) { [int]$p } else { 465 }
    $sec = if ($smtpPort -eq 587) { 'starttls' } else { 'ssl' }
} else {
    $pr = $presets[$c]; $imapHost = $pr.imap; $smtpHost = $pr.smtp; $smtpPort = $pr.port; $sec = $pr.sec
}
if ($c -eq '1') {
    Write-Host ""
    Write-Host "  Pour Gmail/Google Workspace il faut un 'mot de passe d'application' (validation en 2 etapes activee)." -ForegroundColor Yellow
    Write-Host "  La page Google va s'ouvrir : connecte-toi bien avec $email, cree le mot de passe (nom : Jarvis)."
    Read-Host "  Appuie sur Entree pour ouvrir la page"
    Start-Process "https://myaccount.google.com/apppasswords"
} elseif ($c -eq '2') {
    Write-Host "  Pour Outlook, si la validation en 2 etapes est active, cree un mot de passe d'application sur account.microsoft.com/security." -ForegroundColor Yellow
}
$secure = Read-Host "  Mot de passe de la boite (ou mot de passe d'application)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if ($c -eq '1') { $plain = $plain -replace '\s', '' }
$enc = [Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($plain), $null, 'CurrentUser'))
$plain = $null

$acc = [pscustomobject]@{ label = $label; email = $email; password_dpapi = $enc; imap_host = $imapHost; imap_port = 993
                          smtp_host = $smtpHost; smtp_port = $smtpPort; smtp_security = $sec }

Write-Host ""
Write-Host "  Test de connexion..." -ForegroundColor Cyan
$py = Join-Path $env:USERPROFILE 'OpenJarvis\src\.venv\Scripts\python.exe'
$tmp = Join-Path $env:TEMP 'jarvis_mail_test.json'
$acc | ConvertTo-Json | Set-Content $tmp -Encoding UTF8
& $py -I -c @"
import base64, json, ctypes, imaplib, smtplib, sys
from ctypes import wintypes
class B(ctypes.Structure): _fields_=[('n',wintypes.DWORD),('p',ctypes.POINTER(ctypes.c_char))]
a=json.load(open(sys.argv[1],encoding='utf-8-sig')); raw=base64.b64decode(a['password_dpapi'])
buf=ctypes.create_string_buffer(raw,len(raw)); i=B(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_char))); o=B()
ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(i),None,None,None,None,0,ctypes.byref(o))
pw=ctypes.string_at(o.p,o.n).decode()
try:
    m=imaplib.IMAP4_SSL(a['imap_host'],993,timeout=20); m.login(a['email'],pw); m.logout(); print('  IMAP (lecture) : OK')
except Exception as e: print('  IMAP (lecture) : ECHEC', e); sys.exit(1)
try:
    if a['smtp_security']=='starttls':
        s=smtplib.SMTP(a['smtp_host'],a['smtp_port'],timeout=20); s.starttls()
    else:
        s=smtplib.SMTP_SSL(a['smtp_host'],a['smtp_port'],timeout=20)
    s.login(a['email'],pw); s.quit(); print('  SMTP (envoi) : OK')
except Exception as e: print('  SMTP (envoi) : ECHEC', e); sys.exit(2)
"@ $tmp
$ok = $LASTEXITCODE
Remove-Item $tmp -ErrorAction SilentlyContinue
if ($ok -ne 0) {
    Write-Host "  La connexion a echoue : verifie l'adresse, le mot de passe et l'hebergeur, puis relance." -ForegroundColor Red
    Read-Host "  Appuie sur Entree pour fermer"; exit 1
}
$accounts = @($accounts | Where-Object { $_.email -ne $email }) + $acc
ConvertTo-Json -InputObject @($accounts) -Depth 3 | Set-Content $accFile -Encoding UTF8
Write-Host ""
Write-Host "  C'est bon ! JARVIS peut lire et envoyer depuis $email ($label)." -ForegroundColor Green
Write-Host "  Relance JARVIS pour qu'il prenne en compte la nouvelle boite."
Write-Host ""
Read-Host "  Appuie sur Entree pour fermer"
