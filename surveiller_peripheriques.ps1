# Note pendant quelques minutes chaque périphérique qui se connecte ou se déconnecte.
param([int]$Minutes = 5, [string]$Out = "$env:USERPROFILE\.openjarvis\peripheriques.log")
"=== Surveillance démarrée $(Get-Date -Format 'dd/MM HH:mm:ss') pour $Minutes min ===" | Out-File $Out -Encoding utf8
$before = @{}
Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | ForEach-Object { $before[$_.InstanceId] = $_.FriendlyName }
$end = (Get-Date).AddMinutes($Minutes)
while ((Get-Date) -lt $end) {
    Start-Sleep -Milliseconds 700
    $now = @{}
    Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | ForEach-Object { $now[$_.InstanceId] = $_.FriendlyName }
    foreach ($id in $now.Keys) {
        if (-not $before.ContainsKey($id)) { "$(Get-Date -Format 'HH:mm:ss')  CONNECTÉ     $($now[$id])  [$id]" | Out-File $Out -Append -Encoding utf8 }
    }
    foreach ($id in $before.Keys) {
        if (-not $now.ContainsKey($id)) { "$(Get-Date -Format 'HH:mm:ss')  DÉCONNECTÉ   $($before[$id])  [$id]" | Out-File $Out -Append -Encoding utf8 }
    }
    $before = $now
}
"=== Fin $(Get-Date -Format 'HH:mm:ss') ===" | Out-File $Out -Append -Encoding utf8
