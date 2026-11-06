# Réseau, réveil à distance, arrêts inattendus

## Réveil d'un PC fixe (Wake-on-LAN)

- Outil `wake_pc(name)` + `send_magic_packet(mac, broadcast, remote=None)` (UDP 9 et 7, broadcast
  255.255.255.255 + adresse de diffusion de chaque réseau local). Les cibles sont dans `~/.openjarvis/jarvis_wake.json` :
  `{"pc fixe": {"mac": "AA:BB:CC:DD:EE:FF", "broadcast": "192.168.1.255"}}` (exemple : mets l'adresse MAC de TA carte réseau).
- **Sur le PC à réveiller** (c'est à toi de le faire, JARVIS ne modifie pas ces réglages) :
  - BIOS : « Wake on LAN » activé, « ErP » désactivé ;
  - Windows : Gestionnaire de périphériques > carte réseau > Avancé : « Réveil sur Magic Packet » activé ;
  - Windows : démarrage rapide désactivé ;
  - PC branché en **câble Ethernet** (le Wi-Fi ne réveille pas un PC éteint).
  - Vérification : `Get-NetAdapterAdvancedProperty -Name '<ta carte>'`.
- Le paquet magique ne marche que depuis le **même réseau** que le PC. Sur un partage de connexion de téléphone
  (réseau différent), ça ne passe pas.
- **Depuis l'extérieur** : il faut un appareil toujours allumé chez soi qui relaie le réveil. Exemples : une box qui
  propose le Wake-on-LAN (certaines box Free proposent un « Proxy Wake on LAN » ; l'accès à distance de la box est une
  décision de sécurité qui t'appartient), ou un petit serveur. JARVIS sait aussi viser un relais : ajouter
  `"remote": {"host": "<adresse publique>", "port": 9}` à la cible. Les mots de passe de relais ne sont pas gérés.
- Autre option : prise connectée + réglage BIOS « Restore on AC power loss = Power On ».
- Testé : format du paquet (102 octets). Un vrai réveil dépend de ton matériel : à essayer chez toi.

## Tailscale

Voir `telephone.md` (plusieurs PC). Un PC en veille n'est plus joignable par Tailscale : il faut le réveiller d'abord.

## Conflit de port (8765)

JARVIS écoute sur `127.0.0.1:8765`. Si un autre programme occupe ce port, JARVIS ne prend pas sa place : il affiche
une boîte de message Windows et écrit dans le journal. `/api/whoami` répond `{"app": "jarvis-assistant"}` : c'est
ainsi que JARVIS reconnaît qu'il est déjà lancé (et ne démarre pas deux fois). Pour vérifier qui répond :
`http://127.0.0.1:8765/api/whoami`.

## Arrêts silencieux : comment diagnostiquer

Si JARVIS disparaît sans message :

- `_install_crash_traces()` écrit les plantages dans `jarvis_crash.txt` (faulthandler, exceptions de threads, signaux)
  et note « Fin du processus JARVIS » / « Signal … reçu » dans le journal ; `_watchdog()` surveille la fenêtre.
- **Piège connu** : un programme lancé depuis certains outils dont l'application tourne dans un paquet MSIX (par
  exemple l'appli de bureau d'un assistant) est fermé par Windows quand cette application se met à jour. Lance JARVIS
  par un raccourci normal ou `explorer.exe`, pas depuis un outil de ce type.
- Regarde la fin du journal, `jarvis_crash.txt`, `/api/whoami`, et le journal des événements Windows.

## Connexion instable

- Partage de connexion d'un téléphone : coupures DNS (« getaddrinfo failed ») → Gemini Live indisponible. JARVIS
  l'explique à voix haute (`report_problem`, genre « réseau »).
- VPN : certains coupent la liaison avec Gemini Live. JARVIS a un délai de connexion de 12 s, ne renvoie pas
  automatiquement, et un chien de garde de 35 s. Une conversation coupée est marquée morte aussitôt
  (`LiveSession._mark_dead()`), une conversation figée depuis plus de 15 s est remplacée par la suivante
  (`start()`), et une conversation bloquée en « analyse » plus de 45 s est abandonnée (`watchdog()`).

## Tablette en écran secondaire par câble USB (optionnel, Android)

Pour utiliser une tablette Android comme second écran : Apollo (côté PC, basé sur Sunshine) + Artemis (côté
tablette, client Moonlight). Idée : `adb shell svc usb setFunctions rndis` fait que la tablette lance un réseau
sur le câble USB, joignable par Apollo.

- Scripts : `tablette_usb.ps1` (réactive le mode USB et affiche l'adresse du PC), `tablette_auto.ps1` (surveille la
  tablette toutes les 15 s et relance tout à chaque branchement), `creer_tache_tablette.ps1` (tâche planifiée
  au démarrage, droits administrateur demandés par Windows).
- ADB = « platform-tools » officiel de Google, à placer toi-même dans `%USERPROFILE%\OpenJarvis\outils\platform-tools`
  (non inclus dans ce dépôt).
- Le mode USB se perd au débranchement et au redémarrage ; le réseau doit autoriser le trafic local (le ping est
  bloqué par le pare-feu Windows sur un réseau « Public »). Cette fonction demande du matériel précis : c'est
  expérimental.
