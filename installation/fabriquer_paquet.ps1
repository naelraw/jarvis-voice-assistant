# Fabrique le paquet d'installation de JARVIS (dossier + zip sur le bureau) a partir de ce depot.
# Utilisable sur n'importe quel PC : powershell -ExecutionPolicy Bypass -File installation\fabriquer_paquet.ps1
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$desk = [Environment]::GetFolderPath('Desktop')
$out = Join-Path $desk 'JARVIS-installation'
$conf = Join-Path $env:USERPROFILE '.openjarvis'

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $out 'voice'), (Join-Path $out 'reglages') | Out-Null

# installateur + listes de modules
foreach ($f in 'installer.ps1', 'INSTALLER JARVIS.bat', 'LISEZ-MOI.txt') { Copy-Item (Join-Path $repo "installation\$f") $out }
foreach ($f in 'requirements.txt', 'requirements-nvidia.txt') { Copy-Item (Join-Path $repo $f) $out }

# fichiers de JARVIS suivis par git (sans la doc, les tests ni l'installateur)
Push-Location $repo
$files = git ls-files | Where-Object { $_ -notmatch '^(docs|outils_test|installation)/' -and $_ -notin @('CLAUDE.md', 'JOURNAL.md', '.gitignore', 'LICENSE', 'README.md', 'README.en.md', 'CONTRIBUTING.md', 'SECURITY.md', 'requirements.txt', 'requirements-nvidia.txt') }
Pop-Location
foreach ($f in $files) {
    $dest = Join-Path (Join-Path $out 'voice') $f
    New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
    Copy-Item (Join-Path $repo $f) $dest
}

# reglages de CE PC (jamais les cles : elles sont chiffrees pour ce PC et se ressaisissent)
foreach ($f in 'jarvis_voice.toml', 'jarvis_modes.toml', 'jarvis_memory.json') {
    $src = Join-Path $conf $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $out 'reglages') }
}

$zip = "$out.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip
Write-Host "Paquet pret : $zip ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) Mo, $($files.Count) fichiers)"
