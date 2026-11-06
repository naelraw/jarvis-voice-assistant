# Tablette = 2e ecran automatique : au demarrage du PC (et a chaque fois qu'on la rebranche en USB), la tablette
# s'allume, se deverrouille (balayage seulement, jamais de code), active le reseau USB et lance Artemis sur le
# bureau du PC -> Apollo cree l'ecran virtuel, comme un vrai ecran.
# Lance cache par le raccourci "Jarvis - tablette ecran.lnk" du dossier Demarrage. Journal : ~\.openjarvis\tablette.log
$ErrorActionPreference = 'SilentlyContinue'
# Lance AU DEMARRAGE DU PC, avant meme l'ecran de connexion (tache "JARVIS - tablette", compte SYSTEM, creee par
# creer_tache_tablette.ps1) : la tablette est deja un 2e ecran quand on se connecte. Marche aussi lance a la main.
$home0 = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path          # ex. C:\Users\toi
$adb = Join-Path $home0 'OpenJarvis\outils\platform-tools\adb.exe'
$log = Join-Path $home0 '.openjarvis\tablette.log'
$state = 'C:\Program Files\Apollo\config\sunshine_state.json'
$apps = 'C:\Program Files\Apollo\config\apps.json'
function Log($m) { Add-Content -Path $log -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $m) -Encoding utf8 }
# compte SYSTEM : adb doit utiliser la cle de l'utilisateur (celle deja autorisee sur la tablette), sinon la tablette
# repond "unauthorized" et demande une nouvelle autorisation sur son ecran eteint (2026-10-18)
$env:USERPROFILE = $home0
$env:HOME = $home0
$env:ANDROID_USER_HOME = Join-Path $home0 '.android'
$env:ANDROID_SDK_HOME = $home0

# un seul exemplaire (tache SYSTEM et raccourci de session partagent le meme verrou)
try {
    $sec = New-Object System.Security.AccessControl.MutexSecurity
    $sec.AddAccessRule((New-Object System.Security.AccessControl.MutexAccessRule((New-Object System.Security.Principal.SecurityIdentifier('S-1-1-0')), 'FullControl', 'Allow')))
    $created = $false
    $me = New-Object System.Threading.Mutex($false, 'Global\JarvisTabletteAuto', [ref]$created, $sec)
    if (-not $me.WaitOne(0)) { exit 0 }
} catch { exit 0 }
if (-not (Test-Path $adb)) { Log "adb introuvable"; exit 1 }
Log ("surveillance lancee ({0})" -f [Security.Principal.WindowsIdentity]::GetCurrent().Name)
if ((& $adb devices) -match "`tunauthorized") { & $adb kill-server | Out-Null; Start-Sleep 1 }

$lastIp = Join-Path $home0 '.openjarvis\tablette_ip.txt'
function Focus { ((& $adb shell dumpsys window) -match 'mCurrentFocus=') | Select-Object -First 1 }

function Start-Tablette {
    # rapide (2026-10-17, "c'est super long") : ecran allume tout de suite, reseau USB garde s'il est deja actif
    # (le relancer change l'adresse et Windows reidentifie le reseau), aucune attente fixe : on verifie chaque seconde
    $t0 = Get-Date
    & $adb shell input keyevent KEYCODE_WAKEUP | Out-Null
    & $adb shell wm dismiss-keyguard | Out-Null          # balayage ; avec un code, la tablette reste verrouillee
    if ((Focus) -match 'com\.limelight\.noir/com\.limelight\.Game') { Log "flux deja en cours"; return }
    if ((& $adb shell getprop sys.usb.config) -notmatch 'rndis') {
        & $adb shell svc usb setFunctions rndis | Out-Null   # reseau par le cable (la Tab A n'a pas "Modem USB")
        Start-Sleep 2
        & $adb wait-for-device
    }
    $st = Get-Content $state -Raw | ConvertFrom-Json; $uid = if ($st.root.uniqueid) { $st.root.uniqueid } else { $st.uniqueid }
    $app = (Get-Content $apps -Raw | ConvertFrom-Json).apps | Where-Object { $_.name -eq 'Desktop' } | Select-Object -First 1
    # l'appli est lancee TOUT DE SUITE, pendant que Windows prepare le reseau USB : elle retrouve le PC seule des que
    # le reseau arrive (teste : 8 s en tout). Mais Windows met parfois 40 s a activer ce reseau (2026-10-19) : Artemis
    # abandonne alors ("l'ordinateur est hors ligne"). On surveille donc le reseau et on relance Artemis des qu'il est
    # pret ; l'adresse n'est redonnee (detour plus lent) qu'en dernier secours.
    $launch = { & $adb shell am start -n com.limelight.noir/com.limelight.ShortcutTrampoline --es UUID $uid --es AppName Desktop --es AppUUID $app.uuid | Out-Null }
    # demarrage du PC : JARVIS d'abord (sa fenetre de chargement), la tablette ensuite -> la premiere image sur la
    # tablette est JARVIS, pas le bureau (2026-10-19). 60 s max, puis on n'attend plus.
    if (((Get-Date) - $boot).TotalMinutes -lt 3) {
        for ($w = 0; $w -lt 120; $w++) {
            if (Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match 'jarvis_window' }) {
                Log ("fenetre JARVIS ouverte ({0:n0} s) : connexion de la tablette" -f ((Get-Date) - $t0).TotalSeconds)
                Start-Sleep -Milliseconds 1500   # le temps qu'elle s'affiche
                break
            }
            Start-Sleep -Milliseconds 500
        }
    }
    & $launch
    $netT = $null; $relaunch = 0; $launchedBeforeNet = $false
    for ($k = 0; $k -lt 240; $k++) {
        $f = Focus
        if ($f -match 'com\.limelight\.noir/com\.limelight\.Game') {
            Log ("Artemis lance (bureau du PC), direct, {0:n0} s en tout" -f ((Get-Date) - $t0).TotalSeconds)
            return
        }
        if (-not $netT) {
            $nic = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'Remote NDIS' -and $_.Status -eq 'Up' } | Select-Object -First 1
            if ($nic -and (Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^169\.' })) {
                $launchedBeforeNet = ($k -gt 1)
                $netT = Get-Date
                Log ("reseau USB pret ({0:n0} s)" -f ((Get-Date) - $t0).TotalSeconds)
            }
        }
        # reseau pret et Artemis a abandonne ("Erreur de connexion"), ou toujours pas d'image : relance. Lance AVANT le
        # reseau, Artemis reste bloque sur "Etablissement de la connexion" (13:07, 2026-10-19 : 12 s perdues) -> 3 s
        # suffisent quand il attendait deja ; 12 s s'il a ete (re)lance apres l'arrivee du reseau
        $waited = if ($netT) { ((Get-Date) - $netT).TotalSeconds } else { 0 }
        $limit = if ($relaunch -eq 0 -and $launchedBeforeNet) { 3 } else { 12 }
        if ($netT -and $relaunch -lt 3 -and (($f -match 'Erreur' -and $waited -gt 1) -or $waited -gt $limit)) {
            $relaunch++
            Log "Artemis relance (reseau pret, essai $relaunch)"
            & $adb shell am force-stop com.limelight.noir | Out-Null
            & $adb shell input keyevent KEYCODE_WAKEUP | Out-Null
            & $launch
            $netT = Get-Date
        }
        if ($relaunch -ge 3) { break }
        Start-Sleep -Milliseconds 500
    }
    Log "Artemis pas connecte tout seul : adresse du PC redonnee"
    for ($i = 0; $i -lt 120; $i++) {   # reseau USB + Apollo prets (jusqu'a 2 min au demarrage du PC)
        $nic = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'Remote NDIS' -and $_.Status -eq 'Up' } | Select-Object -First 1
        $ip = if ($nic) { (Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^169\.' }).IPAddress }
        $apollo = Get-NetTCPConnection -LocalPort 47989 -State Listen
        if ($ip -and $apollo) { break }
        Start-Sleep 1
    }
    Log ("reseau USB : {0} ; Apollo : {1} ({2:n0} s)" -f $(if ($ip) { $ip } else { 'pas pret' }), $(if ($apollo) { 'pret' } else { 'pas pret' }), ((Get-Date) - $t0).TotalSeconds)
    $known = $false
    for ($try = 1; $try -le 4; $try++) {
        & $adb shell input keyevent KEYCODE_WAKEUP | Out-Null
        & $adb shell wm dismiss-keyguard | Out-Null
        if ($try -gt 1) { & $adb shell am force-stop com.limelight.noir | Out-Null }   # ferme un "Erreur de connexion"
        # l'adresse du PC sur le reseau USB change a chaque branchement : on la redonne a Artemis seulement si elle a
        # change (meme PC, deja appaire : il met juste l'adresse a jour)
        if ($ip -and (-not $known -or $try -gt 1)) {
            & $adb shell am start -a android.intent.action.VIEW -d "art://$ip" | Out-Null
            for ($k = 0; $k -lt 8 -and -not ((Focus) -match 'AddComputerManually'); $k++) { Start-Sleep -Milliseconds 500 }
            Start-Sleep 2
        }
        & $adb shell am start -n com.limelight.noir/com.limelight.ShortcutTrampoline --es UUID $uid --es AppName Desktop --es AppUUID $app.uuid | Out-Null
        for ($k = 0; $k -lt 20; $k++) {
            Start-Sleep 1
            if ((Focus) -match 'com\.limelight\.noir/com\.limelight\.Game') {
                if ($ip) { Set-Content $lastIp $ip -Encoding ascii }
                Log ("Artemis lance (bureau du PC), essai {0}, {1:n0} s en tout" -f $try, ((Get-Date) - $t0).TotalSeconds)
                return
            }
        }
        Log "Artemis pas connecte (essai $try, ecran : $((Focus).Trim())), nouvel essai"
        $known = $false
    }
    Log "abandon : Artemis ne se connecte pas"
}

$was = $false
$boot = Get-Date
$stuck = 0
while ($true) {
    $now = [bool]((& $adb devices) -match "`tdevice$")
    if ($now -and -not $was) {
        Log "tablette branchee"
        Start-Tablette
    }
    # tablette bien branchee (Windows la voit) mais adb ne la liste plus : le serveur adb s'est bloque (2026-10-19,
    # apres un changement de mode USB) -> relance du serveur
    if (-not $now -and (Get-PnpDevice -PresentOnly -FriendlyName 'ADB Interface' -ErrorAction SilentlyContinue)) {
        $stuck++
        if ($stuck -ge 4) { Log "adb bloque : serveur relance"; & $adb kill-server | Out-Null; $stuck = 0 }
    } else { $stuck = 0 }
    $was = $now
    Start-Sleep $(if (((Get-Date) - $boot).TotalMinutes -lt 3) { 1 } else { 3 })
}
