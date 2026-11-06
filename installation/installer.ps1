# Installe JARVIS sur ce PC : Python, modules, fichiers, raccourcis, demarrage avec Windows.
# Lance par "INSTALLER JARVIS.bat". Aucune cle ni mot de passe n'est copie : on les entre a la fin.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# Deux façons de l'utiliser : (1) depuis le dépôt cloné (ce dossier "installation" est dans le dépôt),
# (2) depuis un paquet zip fabriqué par fabriquer_paquet.ps1 (dossier "voice" à côté de ce script).
$repoMode = -not (Test-Path (Join-Path $here 'voice'))
$src = if ($repoMode) { Split-Path -Parent $here } else { $here }
$root = Join-Path $env:USERPROFILE 'OpenJarvis'
$voice = Join-Path $root 'voice'
$venv = Join-Path $root 'src\.venv'
$conf = Join-Path $env:USERPROFILE '.openjarvis'

function Step($t) { Write-Host ""; Write-Host "  >> $t" -ForegroundColor Cyan }

Write-Host ""
Write-Host "  ===  Installation de JARVIS  ===" -ForegroundColor Cyan
Write-Host "  Compte 5 a 15 minutes (selon la connexion). Ne ferme pas cette fenetre."

# 1. Python 3.13
Step "Python"
function Find-Python {
    foreach ($c in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        'C:\Program Files\Python313\python.exe')) {
        if (Test-Path $c) { return $c }
    }
    try { $p = & py -3.13 -c "import sys;print(sys.executable)" 2>$null; if ($p -and (Test-Path $p)) { return $p } } catch {}
    return $null
}
$py = Find-Python
if (-not $py) {
    Write-Host "  Installation de Python 3.13 (winget)..."
    winget install -e --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements
    $py = Find-Python
}
if (-not $py) {
    Write-Host "  Python n'a pas pu etre installe automatiquement." -ForegroundColor Red
    Write-Host "  Installe 'Python 3.13' depuis le Microsoft Store ou python.org, puis relance l'installation."
    Read-Host "  Entree pour fermer"; exit 1
}
Write-Host "  OK : $py"

# 2. Fichiers de JARVIS
Step "Fichiers de JARVIS -> $voice"
New-Item -ItemType Directory -Force $voice | Out-Null
if ($repoMode) {
    # depuis le dépôt : on copie les fichiers du programme (pas la doc, ni l'installateur, ni git)
    $skip = @('.git', '.github', 'docs', 'installation', '.gitignore', 'README.md', 'README.en.md', 'LICENSE',
              'CONTRIBUTING.md', 'SECURITY.md', 'requirements.txt', 'requirements-nvidia.txt')
    if ((Resolve-Path $src).Path -ne (Resolve-Path $voice).Path) {
        Get-ChildItem $src -Force | Where-Object { $_.Name -notin $skip } | Copy-Item -Destination $voice -Recurse -Force
    }
} else {
    Copy-Item (Join-Path $here 'voice\*') $voice -Recurse -Force
}
New-Item -ItemType Directory -Force $conf | Out-Null
foreach ($f in Get-ChildItem (Join-Path $here 'reglages') -File -ErrorAction SilentlyContinue) {
    $dest = Join-Path $conf $f.Name
    if (-not (Test-Path $dest)) { Copy-Item $f.FullName $dest }   # ne remplace pas des reglages deja presents
}

# 3. Environnement Python + modules
Step "Modules Python (le plus long)"
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
    New-Item -ItemType Directory -Force (Split-Path $venv) | Out-Null
    & $py -m venv $venv
}
$vpy = Join-Path $venv 'Scripts\python.exe'
$vpyw = Join-Path $venv 'Scripts\pythonw.exe'
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install --quiet -r (Join-Path $src 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    Write-Host "  L'installation des modules a echoue (connexion ?). Relance l'installation." -ForegroundColor Red
    Read-Host "  Entree pour fermer"; exit 1
}
# Carte NVIDIA : modules pour faire tourner la reconnaissance vocale sur la carte graphique (sinon inutiles, ~1 Go)
$nvidia = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'NVIDIA' }
$nvreq = Join-Path $src 'requirements-nvidia.txt'
if ($nvidia -and (Test-Path $nvreq)) {
    Write-Host "  Carte NVIDIA detectee ($($nvidia[0].Name)) : modules pour la carte graphique..."
    & $vpy -m pip install --quiet -r $nvreq
    if ($LASTEXITCODE -ne 0) { Write-Host "  (echec : la reconnaissance vocale tournera sur le processeur)" -ForegroundColor Yellow }
}

# 4. Raccourcis : bureau + demarrage avec Windows
Step "Raccourcis"
$sh = New-Object -ComObject WScript.Shell
$desk = [Environment]::GetFolderPath('Desktop')
$startup = [Environment]::GetFolderPath('Startup')
$ico = Join-Path $voice 'jarvis.ico'
$ps = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
function Lnk($path, $target, $arguments, $icon) {
    $l = $sh.CreateShortcut($path); $l.TargetPath = $target; $l.Arguments = $arguments
    $l.WorkingDirectory = $voice; $l.IconLocation = $icon; $l.Save()
}
Lnk (Join-Path $desk 'Jarvis.lnk') $vpyw "`"$voice\jarvis_voice.py`"" "$ico,0"
Lnk (Join-Path $desk 'Calibrer le claquement de mains.lnk') $vpy "`"$voice\jarvis_clap.py`" --calibrate" "$ico,0"
Lnk (Join-Path $desk 'Tester le claquement de mains.lnk') $vpy "`"$voice\jarvis_clap.py`" --test" "$ico,0"
foreach ($c in @(
    @('Configurer Gemini (cerveau Jarvis)', 'configurer_gemini.ps1'),
    @('Ajouter une boite mail a Jarvis', 'configurer_mails.ps1'),
    @("Configurer l'agenda (Jarvis)", 'configurer_agenda.ps1'),
    @('Configurer ElevenLabs (voix Jarvis)', 'configurer_elevenlabs.ps1'),
    @('Configurer Groq (secours Jarvis)', 'configurer_groq.ps1'),
    @('Configurer YouTube (Jarvis)', 'configurer_youtube.ps1'),
    @('Configurer VirusTotal (Jarvis)', 'configurer_virustotal.ps1'))) {
    if (-not (Test-Path (Join-Path $voice $c[1]))) { continue }
    Lnk (Join-Path $desk "$($c[0]).lnk") $ps "-NoProfile -ExecutionPolicy Bypass -File `"$voice\$($c[1])`"" "$ico,0"
}
Lnk (Join-Path $startup 'Jarvis (arriere-plan).lnk') $vpyw "`"$voice\jarvis_voice.py`" --background" "$ico,0"
Lnk (Join-Path $startup 'Jarvis - claquement de mains.lnk') $vpyw "`"$voice\jarvis_clap.py`"" "$ico,0"

# 5. Cles et comptes (chiffres pour CE PC : il faut les entrer a nouveau)
Step "Connexions"
Write-Host "  Les cles ne voyagent pas d'un PC a l'autre (elles sont chiffrees par Windows) :"
Write-Host "  on configure maintenant la cle Gemini, indispensable. Le reste est facultatif."
& $ps -NoProfile -ExecutionPolicy Bypass -File (Join-Path $voice 'configurer_gemini.ps1')
foreach ($c in @(
    @('tes boites mail', 'configurer_mails.ps1'),
    @('Google Agenda', 'configurer_agenda.ps1'),
    @('ElevenLabs (voix du mode classique)', 'configurer_elevenlabs.ps1'),
    @('Groq (cerveau de secours, gratuit)', 'configurer_groq.ps1'),
    @('YouTube (recherche de videos)', 'configurer_youtube.ps1'),
    @('VirusTotal (verifier un fichier ou un lien)', 'configurer_virustotal.ps1'))) {
    if (-not (Test-Path (Join-Path $voice $c[1]))) { continue }
    $r = Read-Host "  Configurer $($c[0]) maintenant ? (o/n)"
    if ($r -match '^[oOyY]') { & $ps -NoProfile -ExecutionPolicy Bypass -File (Join-Path $voice $c[1]) }
}

# 6. Lancement
Step "Lancement"
Start-Process $vpyw -ArgumentList "`"$voice\jarvis_clap.py`"" -WorkingDirectory $voice
Start-Process $vpyw -ArgumentList "`"$voice\jarvis_voice.py`"" -WorkingDirectory $voice
Write-Host ""
Write-Host "  JARVIS est installe !" -ForegroundColor Green
Write-Host "  Le premier lancement telecharge la reconnaissance vocale (~500 Mo) : 1 a 3 minutes."
Write-Host "  Ensuite : 'OK Jarvis', double claquement de mains, ou Ctrl+Alt+J."
Write-Host "  Il demarre tout seul avec Windows. Pense a 'Calibrer le claquement de mains' sur le bureau."
Write-Host ""
Read-Host "  Entree pour fermer"
