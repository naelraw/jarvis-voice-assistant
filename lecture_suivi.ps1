# Suivi en continu de la musique (lecteurs Windows : appli Deezer, navigateur, Spotify...) pour le lecteur de JARVIS.
# Une ligne JSON par seconde (la pochette est cherchée par JARVIS sur Deezer d'après le titre et l'artiste).
# Lancé par JARVIS seulement quand son lecteur est affiché, arrêté sinon.
param([string]$cmdFile = "$env:USERPROFILE\.openjarvis\lecteur_cmd.txt", [int]$parent = 0)
$ErrorActionPreference = "SilentlyContinue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $null = $task.Wait(4000); $task.Result }
$null = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
try { Add-Type -Path (Join-Path $PSScriptRoot "volume_appli.cs") } catch { }
function ExeOf($id) {  # nom du programme d'après l'identifiant du lecteur (pour son volume à lui)
  if ($id -match "Deezer") { "Deezer" } elseif ($id -match "Spotify") { "Spotify" } elseif ($id -match "chrome") { "chrome" }
  elseif ($id -match "msedge|MicrosoftEdge") { "msedge" } elseif ($id -match "firefox") { "firefox" } else { "" } }
$mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
while ($true) {
  if ($parent -and -not (Get-Process -Id $parent -ErrorAction SilentlyContinue)) { exit }  # JARVIS arrêté : on s'arrête aussi
  $best = $null; $bestScore = -1
  foreach ($s in $mgr.GetSessions()) {
    $st = "$($s.GetPlaybackInfo().PlaybackStatus)"
    $score = 0
    if ($st -eq "Playing") { $score += 10 }
    if ($s.SourceAppUserModelId -match "Deezer") { $score += 5 }
    if ($score -gt $bestScore) { $best = $s; $bestScore = $score }
  }
  $exe = ""
  if ($best) {
    $p = Await ($best.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
    $tl = $best.GetTimelineProperties()
    $st = "$($best.GetPlaybackInfo().PlaybackStatus)"
    $o = [ordered]@{
      app = "$($best.SourceAppUserModelId)"; status = $st; title = "$($p.Title)"; artist = "$($p.Artist)"; album = "$($p.AlbumTitle)"
      pos = [Math]::Round($tl.Position.TotalSeconds, 1); dur = [Math]::Round($tl.EndTime.TotalSeconds, 1)
      upd = $tl.LastUpdatedTime.ToUnixTimeMilliseconds()
      vol = -1; muted = $false
    }
    $exe = ExeOf $best.SourceAppUserModelId
    if ($exe) { try { $o.vol = [Jarvis.AppVolume]::Get($exe); $o.muted = [Jarvis.AppVolume]::Muted($exe) } catch { } }
  } else { $o = [ordered]@{ none = $true } }
  # mélangeur : volume général + chaque appli qui a un son ouvert
  try { $o.master = [Jarvis.AppVolume]::MasterState(); $o.mix = @([Jarvis.AppVolume]::List()) } catch { }
  ($o | ConvertTo-Json -Compress); [Console]::Out.Flush()
  # commandes du lecteur et du mélangeur de JARVIS (fichier déposé par JARVIS) : on les guette toutes les 100 ms
  for ($i = 0; $i -lt 10; $i++) {
    if (Test-Path $cmdFile) {
      $c = (Get-Content $cmdFile -Raw).Trim(); Remove-Item $cmdFile -Force
      $null = switch -Regex ($c) {
        '^toggle$' { if ($best) { Await ($best.TryTogglePlayPauseAsync()) ([bool]) } }
        '^next$' { if ($best) { Await ($best.TrySkipNextAsync()) ([bool]) } }
        '^prev$' { if ($best) { Await ($best.TrySkipPreviousAsync()) ([bool]) } }
        '^vol:(\d+)$' { if ($exe) { [Jarvis.AppVolume]::Set($exe, [int]$Matches[1]) } }
        '^mute$' { if ($exe) { [Jarvis.AppVolume]::ToggleMute($exe) } }
        '^seek:([\d.]+)$' { if ($best) { Await ($best.TryChangePlaybackPositionAsync([long]([double]$Matches[1] * 10000000))) ([bool]) } }
        '^appvol:([^:]+):(\d+)$' { [Jarvis.AppVolume]::Set($Matches[1], [int]$Matches[2]) }
        '^appmute:([^:]+)$' { [Jarvis.AppVolume]::ToggleMute($Matches[1]) }
        '^mastervol:(\d+)$' { [Jarvis.AppVolume]::MasterSet([int]$Matches[1]) }
        '^mastermute$' { [Jarvis.AppVolume]::MasterMute() }
      }
      Start-Sleep -Milliseconds 150
      break
    }
    Start-Sleep -Milliseconds 100
  }
}
