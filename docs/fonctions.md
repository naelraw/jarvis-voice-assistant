# Fonctions (outils) de JARVIS

À lire avant d'ajouter ou modifier un outil. Recette d'ajout : voir CLAUDE.md §7.

## Où sont les outils

- `TOOLS_SPEC` (déclarations, `_tool(name, desc, props, required)`) + `TOOLS` (nom → fonction) dans
  jarvis_voice.py ; certains ajoutés plus loin (`TOOLS["x"] = x`) ou par `register_custom_apis()`.
- `LIVE_CONFIRM_TOOLS` : actions irréversibles → le modèle doit obtenir un « oui » oral puis passer
  `confirmed=true` (mail, suppression, extinction, tickets PC Radar, operate_app, steam, claude_code,
  whatsapp_message avec envoi, organize_folder…).
- `TOOL_DOING` / `_doing_label()` : texte « Je fais… » affiché sous la sphère. `_show_tool_result()` : panneau.
- `GROQ_TOOLS` : les ~21 outils proposés au secours Groq (sa limite de tokens refuse la liste complète).
- `_journal()` : chaque action est notée dans `jarvis_journal.jsonl` (outil `action_journal`).

## Principaux outils

- **Applis** : `open_application`, `close_application`, `open_website`, `_yield_to_opened` (l'appli ouverte passe
  devant JARVIS). `operate_app` : agent qui pilote une appli (UIAutomation en arrière-plan, sinon captures +
  Gemini `box_2d`) ; coûte du quota `gemini-3.8-flash` (~20/jour). `steam(action, game)`, Battle.net
  (`_watch_launch` : vérifie que le jeu démarre, sinon clique « Jouer », puis mode jeu).
- **Lancer un jeu : filet de sécurité** (2026-10-16) : Gemini Live a répondu « Je lance Call of Duty, bonne
  partie, je me tais » SANS appeler `launch_game` (rien ne se lançait, pas de mode jeu). Maintenant, à la fin de
  chaque tour, si la demande (`user_text` ou `turn_req`) contient un verbe de lancement + un jeu installé
  (`_game_in_request`, noms et `GAME_ALIASES`) et qu'aucun outil de jeu n'a été appelé (`turn_tools`), JARVIS
  appelle `launch_game` lui-même. Consigne aussi renforcée dans `system_prompt()`.
- **Mails** (`check_emails`, `send_email`, `reply_email`, `manage_emails`) : IMAP, un seul échange pour tous les
  en-têtes, boîtes lues en même temps (35 s → 6 s pour 10 mails). Piège : configurer_mails.ps1 (PowerShell 5.1)
  réemballait la liste en `{"value": [...], "Count": n}` → `KeyError: 'email'` à chaque réveil ; corrigé, et
  `mail_accounts()` remet à plat / ignore les entrées sans adresse.
- **PC Radar** : `pcradar_report`, `pcradar_ticket(_details)`, `pcradar_suspect`, `pcradar_stats_chart`,
  `price_watch`, `check_website` (pcradar.tech), surveillance `_check_pcradar` (60 s).
- **Claude Code** : `claude_code(task, project)` lance `~/.local/bin/claude.exe -p … --output-format stream-json
  --permission-mode acceptEdits` dans le dossier du projet (`jarvis_claude_projects.json`, projet « jarvis »
  inclus), suit les étapes, 20 min max, annonce le résultat. Ne pousse rien sur git, ne déploie rien.
- **Musique** : `play_music(query, service)`, service par défaut `music_service` = deezer (comptes payants de
  l'utilisateur). Deezer : recherche publique api.deezer.com (morceau / album / playlist / artiste, `_music_kind`)
  puis deezer.com/fr/<type>/<id>?autoplay=true. Amazon Music : pas d'API → titre exact via Deezer puis DuckDuckGo
  `site:music.amazon.fr` → page avec `?do=play`. `_ensure_playing` vérifie via `lecture_en_cours.ps1` (sessions
  multimédias Windows) et appuie sur espace dans l'onglet Deezer / Amazon (jamais ailleurs). YouTube Music reste
  disponible. Piège : l'API Deezer renvoie « 403 Access Denied » sans User-Agent de navigateur → 2 essais dans
  `_deezer_find`, sinon page de recherche.
- **YouTube** : `youtube_search`, `play_youtube` ; clé YouTube Data API v3 (la clé Gemini est refusée).
- **Sources fiables sans clé** : `wikipedia` (fr/en), `convert_currency` (BCE / Frankfurter), `news_headlines`
  (Google Actualités RSS), `web_search` (DuckDuckGo, repli Wikipédia / Actualités). `LIVE_PROMPT` impose de
  vérifier tout fait par un outil. Piège : Wikimédia renvoie 403 sans contact dans le User-Agent (`_UA` = URL du
  site, jamais l'e-mail).
- **VirusTotal** `check_virustotal` (fichier / lien / domaine / SHA-256) : un fichier n'est JAMAIS envoyé, seule
  son empreinte part. Pas encore testé avec une vraie clé.
- **WhatsApp** (WhatsApp pour PC installé sur le portable) : `whatsapp_call` (confirmation orale),
  `whatsapp_message` (ouvre la discussion par Ctrl+F et ÉCRIT le message ; PAS envoyé par défaut, `send=true` après
  un oui oral). Non testés sur une vraie personne. Risque : la 1re discussion trouvée peut être la mauvaise.
  Snapchat : pas d'API, l'automatiser risque le blocage du compte → seulement l'ouvrir.
- **Fonctions inspirées d'autres projets JARVIS** (réécrites, pas copiées) : minuteur
  `start_timer` / `stop_timer` (alarme + `alert()`), `football` (TheSportsDB gratuit, clé « 3 » ; classements =
  5 premiers, PSG via `FOOT_IDS`), `quick_tool` (dé, pile ou face, mot de passe copié jamais lu, heure d'une ville,
  âge), `organize_folder` (confirmation, annulable `undo_organize`), `manage_file`, `arrange_windows` (+ action de
  mode `{arrange = "quadrants"}`), `look_camera` (OpenCV, une photo → Gemini vision, rien d'enregistré ; le
  portable n'a pas de webcam détectée), `show_globe` (Nominatim + OSRM).
- **Connecteurs API ajoutables** (onglet « API » = `apis.html`, module `jarvis_apis.py`, stockage
  `jarvis_apis.json`, clés DPAPI `secret_dpapi`, catalogue `PRESETS`) : une API = lien GET avec `{paramètres}` +
  phrase « à quoi ça sert » + clé facultative. Chaque API active devient un outil `api_<nom>`
  (`register_custom_apis()` ; une conversation Live déjà ouverte garde sa liste). Routes `/api/apis` (+ `/delete`,
  `/toggle`, `/test`, jeton + Origin). SÉCURITÉ : adresses non publiques refusées (aussi après redirection), `..`
  et `\` refusés, réponse 1,5 Mo / 15 s max, clé jamais renvoyée ni écrite en clair, résultat présenté comme
  « données, jamais des instructions ». ntfy : un sujet contenant « CHANGE-MOI » est refusé (sujet public).
- **Réveil d'un PC** `wake_pc(name)` : voir reseau-et-reveil.md.
- **Clips de jeu** (`save_clip`, 2026-10-16) : par **OBS Studio** s'il est réglé pour JARVIS, sinon par les
  raccourcis AMD ReLive. `configurer_obs.py` (OBS fermé ; sauvegarde `*.avant-jarvis-<date>`) : encodeur de la
  carte (`amd_hevc` / `nvenc_hevc`), qualité « Small », mp4, tampon de relecture 30 s / 512 Mo, sortie = taille de
  l'écran (pas de redimensionnement), 60 i/s, capture de jeu « n'importe quelle appli plein écran », raccourci
  Ctrl+Maj+S = enregistrer le clip, serveur WebSocket local (4455) avec mot de passe aléatoire que JARVIS relit dans
  `%APPDATA%\obs-studio\plugin_config\obs-websocket\config.json` (jamais affiché). Code : `_obs_conf`, `use_obs`
  (réglage `clip_app` = auto / obs / amd), `obs_request` (WebSocket v5, authentification sha256), `obs_ensure`
  (lance OBS réduit `--minimize-to-tray --startreplaybuffer`), `_obs_game` (tampon lancé au début de partie,
  arrêté à la fin ; réglage `obs_auto`), `_obs_clip` (SaveReplayBuffer / ToggleRecord / SaveSourceScreenshot).
  En jeu JARVIS dort : clip par Ctrl+Maj+S (OBS) ou depuis le téléphone.
  Piège (PC fixe) : obs64.exe est réglé « Exécuter en tant qu'administrateur » (HKCU AppCompatFlags Layers
  `~ RUNASADMIN`) → JARVIS ne peut pas le lancer (WinError 740, il faudrait une fenêtre UAC en pleine partie).
  Soit l'utilisateur décoche ce réglage, soit il ouvre OBS lui-même : le WebSocket marche quand même avec un OBS élevé.
  Solution retenue : `creer_tache_obs.ps1` (raccourci bureau « Autoriser JARVIS a ouvrir OBS », lancé une fois par
  l'utilisateur avec UAC) crée la tâche planifiée « JARVIS - OBS » (droits élevés, sans déclencheur) ; `obs_ensure` fait
  `schtasks /run /tn "JARVIS - OBS"`, et seulement sinon un lancement direct. Instant Replay AMD à couper (double
  encodage et saccades : enregistrement du bureau 1080p60 30 Mb/s qui tournait en permanence).
- **Consignes permanentes** (2026-10-17) : `~/.openjarvis/jarvis_consignes.json`, TOUJOURS dans `system_prompt()`
  (« CONSIGNES PERMANENTES… »), contrairement aux souvenirs (`remember`, des faits). Outils `add_rule`, `list_rules`,
  `remove_rule`. Consigne par défaut (`DEFAULT_RULES`) : ce qu'il ne peut pas faire → `note_missing_skill`.
- **Liste « À ajouter à JARVIS »** : `note_missing_skill(request, why)` ajoute `- [ ] date — demande (pourquoi)` à
  `Documents\Notes Jarvis\A ajouter a JARVIS.md` (visible dans l'onglet Notes, doublons ignorés). Filet de sécurité
  dans la conversation en direct : une réponse « je ne peux pas… » sans appel de l'outil est notée quand même.
  Claude Code lit cette liste en début de session (CLAUDE.md §6).
- **Divers** : notes (Documents\Notes Jarvis), rappels, agenda (Google Agenda via script Apps Script, `agenda`,
  `add_event`), météo (wttr.in ; idée : Open-Meteo), `save_clip` (AMD ReLive Ctrl+Shift+S), `game_boost`,
  `jarvis_selftest`, `add_routine`, `read_selection`, `search_file_contents`, `set_live_voice`, `pause_jarvis`,
  `show_on_screen`, `hide_jarvis`, `remember`.

## Comportements transversaux

- **Pause** : `set_paused(on, announce)` (persistée) ; `pause_jarvis()` attend la fin de la phrase ; plusieurs
  actions puis la pause → `_pause_after_actions(sess)` attend que tout soit fini.
- **« OK Jarvis » en jeu** (2026-10-16) : pendant le sommeil de jeu, `Ear._game_listen()` ouvre le micro pour le
  SEUL détecteur local `GATE.model` (openWakeWord « hey_jarvis », seuil `game_wake_threshold` 0,25, ~8 % d'un cœur ;
  réglage `game_wake`, condition `_game_wake_ok()`). Rien n'est envoyé avant la détection ; ensuite ~2 s avant +
  la suite (jusqu'à 0,7 s de silence, 3 s max) → `_game_command()` : `phone_transcribe` (Gemini Flash Lite, Whisper
  étant déchargé), exige « Jarvis » dans la phrase, puis clip / capture / enregistrement (`save_clip`) ou
  « reprends » (comme Ctrl+Alt+J). Réponse `LIVE.say` très courte (« Clip enregistré. »), consigne spéciale en jeu.
  Test : `_tests/test_game_wake.py` (phrases de synthèse : 2 détections sur 2, phrases de partie ignorées).
  Limite : le détecteur est entraîné sur l'anglais ; « Jarvis » prononcé à la française score plus bas.
  1re vraie partie (2026-10-16 22:18) : 1 seule détection en 16 min (0,31) et transcription VIDE en 11 s → rien.
  Corrigé : seuil 0,15 ; « presque entendu » (0,06 à seuil) noté dans le journal pour régler sur sa voix ;
  voix remise à niveau avant transcription ; transcription limitée à `game_cmd_timeout` (4 s) ; le détecteur
  ayant déjà reconnu « Jarvis », une phrase vide / lente / sans « Jarvis » = CLIP (un clip ne coûte rien) ;
  capture, enregistrement et « reprends » restent reconnus.
  REVU le même soir à la demande de l'utilisateur (« pas de clip automatique si je demande autre chose ») : plus de clip
  par défaut. Transcription en jeu SUR LE PC : `_game_stt` (Whisper « base » int8 2 threads, ~150 Mo, chargé au 1er
  « OK Jarvis » de la partie, libéré par `_wake_from_game_sleep` ; ~0,9 s par phrase, 7 s la 1re fois), secours
  Gemini. Sans « Jarvis » dans la phrase → ignorée ; rien après « Jarvis » → « Je n'ai pas compris » ; clip /
  capture / enregistrement / reprends → action ; toute autre demande → `LIVE.start("[En pleine partie : …] …",
  announce=True)` (outils disponibles, réponse courte, la conversation se referme).
- **« OK Jarvis » en jeu : Vosk** (2026-10-16 23:00, remplace openWakeWord, gardé en secours `_game_listen_oww`) :
  openWakeWord (anglais) donnait 0,08 sur son « Jarvis » à la française et jusqu'à 0,34 sur ses discussions ; sa
  dictée écrit « OK Jarvis clip » → « OK, j'arrive skip ». `Ear._game_listen` = `KaldiRecognizer` Vosk avec la
  grammaire `GAME_WORDS` (ok, jarvis, j'arrive, clip, capture, écran, enregistre, reprends… + « [unk] » ;
  `json.dumps(..., ensure_ascii=False)` OBLIGATOIRE sinon « écran » est ignoré ; pas de « clips » à côté de « clip »,
  ça divise la confiance). Modèle `vosk-model-small-fr-0.22` (~40 Mo, alphacephei.com) dans `~/.openjarvis/vosk`,
  téléchargé au besoin par `_vosk_model()`. `_game_heard` : « jarvis » (conf ≥ `game_jarvis_conf` 0,6) ou
  « j'arrive » SUIVI de « clip » (« ok j'arrive » seul = vraie phrase de partie, ignorée) ; puis reprends / capture /
  clip / enregistre / « [unk] » = demande libre (`_game_do` → Whisper base → `LIVE.start`) ; « Jarvis » seul → la
  phrase suivante (5 s) est la commande. Test : `test_vosk_listen.py` (script de test, non publié) (7/8, les 3 phrases de partie
  ignorées). Coût mesuré en partie : ~5 % d'un cœur, 0,07 s par phrase.
  VALIDÉ en vraie partie le 2026-10-16 à 23:05 : « jarvis(1.00) clip(1.00) », clips dans Vidéos. Défaut corrigé :
  l'annonce « Clip enregistré » (`LIVE.say` en jeu) faisait rappeler `save_clip` par Gemini → 2 clips ; en jeu
  `say()` pose `no_tools_until` (15 s) et `_run_tool` refuse alors tout outil ; une vraie demande remet à 0.
  Confirmation non entendue (Gemini rappelait l'outil au lieu de parler) → les réponses fixes du mode jeu
  (`GAME_PHRASES` : « Clip enregistré. », « Capture faite. », « Le clip a échoué. », « Enregistrement lancé/arrêté. »,
  « Je n'ai pas compris. », « Je suis là. ») sont enregistrées UNE fois avec la voix de JARVIS (`mobile_tts`, Gemini
  TTS) dans `~/.openjarvis/phrases/*_<voix>.wav` (`_prepare_phrases`, au début de chaque partie si besoin) et
  [REVU : l'utilisateur « c'est pas du tout la voix de Jarvis » : la synthèse TTS, même voix Charon, sonne autrement →
  enregistrement par la conversation en direct elle-même (`_record_live_phrase`, gemini-3.8-live, sans outils,
  consigne « [Annonce] … », 3 essais, la plus courte gardée), fichiers `*_live_<voix>.wav`] et
  rejouées instantanément sur le PC (`_say_quick`, `sd.play` sur la sortie choisie) ; secours : `LIVE.say`.
  Marche quel que soit l'état de la fenêtre du jeu (plein écran, fenêtré, réduit) : le jeu est repéré par son
  processus, et l'état de la fenêtre de JARVIS n'entre pas en compte.
- **Mode jeu** : `_game_sleep_loop` (GAME_DIR_HINTS, psutil, premier plan) → micro fermé, Whisper déchargé,
  fichier `jarvis_game_sleep`, fenêtre jamais ouverte (et réduite si elle l'était : plus aucun dessin pendant la partie), claquements ignorés ; Ctrl+Alt+J rallume jusqu'à la fin de
  la partie. Mode « jeu » de jarvis_modes.toml : ferme aussi Claude et Edge, ouvre Discord, et ne lance PLUS un jeu fixe
  (2026-10-17 : « faut pas qu'il me lance un jeu à chaque fois ») : `activate_mode(name, game)` ; sans `game`, aucun
  jeu lancé et la réponse demande au modèle de demander lequel (liste des jeux installés), puis `launch_game`.
  Optimisation réelle au début de chaque partie (`game_boost`) : alimentation performance maximale, applis de fond
  en priorité basse, jeu en priorité « supérieure à la normale », mémoire inutilisée des applis de fond rendue
  (`_trim_background_memory`, EmptyWorkingSet, rien n'est fermé ; 0,74 Go mesuré) ; tout est remis à la fin. **Faux jeu** : la capture Win+Maj+S
  (voile plein écran, SnippingTool.exe ouvert) laissait JARVIS éteint → `FULLSCREEN_NOT_GAMES` exclut les voiles
  Windows et la fenêtre de JARVIS ; une appli seulement « plein écran » ne compte plus après `FULLSCREEN_GRACE`
  (20 s). Symptôme : « Jeu en cours (plein écran) » dans le journal sans jeu lancé.
- **Heures de cours** (`quiet_hours` : `{days=[0..6], start, end, label}`, 0 = lundi ; section des paramètres
  seulement) : `_quiet_loop` (20 s) remplit `STATE.quiet` et le fichier `jarvis_quiet` ; fenêtre fermée (sauf
  conversation ou tâche), micro fermé, `summon` ignore clap/voice, l'iPhone n'ouvre plus la fenêtre, claquements
  coupés. Ctrl+Alt+J ouvre quand même. Alertes et rappels gardés pour plus tard.
- **Récap de démarrage éclair** : `_brief_refresh` prépare d'avance (démarrage puis toutes les 10 min) les mails
  non lus des 36 dernières heures et les chiffres PC Radar (`_BRIEF`) ; `briefing_prompt()` → 2-3 phrases sans
  outil. Météo seulement si `briefing_weather` (false par défaut). `_brief_accounts()` : toutes les boîtes si
  aucune choisie n'existe sur ce PC.
- **Alertes** (mails, tickets, prix, site) : gardées quand la fenêtre est fermée / en pause / en jeu, dites à la
  réouverture ; envoyées aussi au téléphone (`mobile_push`).

## Ajouts du 2026-10-19 (outils vocaux)

- `etat_systeme` : « état du système » vérifie micro, tablette, clés, OBS, Tailscale, disque (`health_report()`, aussi
  `/api/health` et `test_demarrage.py` (script de test, non publié) qui relit le dernier démarrage dans les journaux).
- `clip_to_phone` : le dernier clip en lien sur le téléphone (`/m/clip`, notification ou bouton « Regarder »). Les clips
  OBS portent le nom du jeu (« Clip Call Of Duty 2026-… »).
- `ambiance` : musique selon l'ambiance (`AMBIANCES`, surchargeable par `ambiances` dans le toml).
- `remind_at_boot` : rappel dit au prochain bonjour du démarrage (`jarvis_rappels_demarrage.json`).
- `webcam_look` / `webcam_live` : la WEBCAM du PC (nuroum V15AF, OpenCV/DirectShow) ; photo + Gemini vision, ou vidéo en
  direct dans la conversation Live (`send_realtime_input(video=...)`, 1 image/s, 768 px, 10 min max, `webcam_fps`,
  `webcam_minutes`, `webcam_index`) ; la conversation reste ouverte (`_keep_open`), coupée par la pause, le jeu, le
  micro coupé ou « arrête la caméra ». La caméra de la TABLETTE n'est plus utilisée (retirée le 2026-10-19).
- Routine du soir (`evening_time`, 22:30, `evening_routine`), mode nuit (`night_start/night_end/night_gain`,
  `night_silent_greeting`), sauvegarde quotidienne des réglages SANS clés dans `Documents\Sauvegardes JARVIS`
  (`backup_settings`, 14 gardées), surveillance de Whisper GPU (`_vk_watch`).
- Notifications téléphone : lien (`url`) et boutons « Reporter 1 h » pour les rappels (Android/ordinateur ; l'iPhone
  n'affiche que le toucher). Tablette : écran d'accueil (météo, prochain rendez-vous, PC Radar) et glisser pour changer de vue.

## Fenêtre Caméra (2026-10-19)

- `camera3d.js` (servi à `/camera3d.js`) : fenêtre flottante de la page, ouverte par la voix (`camera_window` : vue / atelier /
  onglets / fermer ; `forme_3d` : cube, pyramide, sphère, anneau, cylindre, octaèdre ; `webcam_live` l'ouvre aussi). Le serveur
  envoie `UIX["cam"]` dans le message ws `uix` ; `CAM3D.state()` l'applique.
- Suivi des mains : MediaPipe HandLandmarker (version `MP_VERSION`), téléchargé UNE fois dans `~/.openjarvis/vendor/mediapipe`
  (`ensure_vendor`, pas dans le dépôt) et servi en local (`/vendor/mediapipe/…`). Pincer pouce + index = saisir (déplacer ; la
  taille suit l'éloignement de la main ; le roulis tourne la forme), deux mains = agrandir / tourner, index pointé 0,7 s sur un
  bouton = créer. Souris = main virtuelle (clic = pincer).
  v3 : un seul onglet, ATELIER 3D, en plein écran par défaut (⤡ pour réduire) : pincer DANS LE VIDE et dessiner (rond = sphère, carré = cube, rectangle allongé = cylindre, triangle = pyramide, losange = octaèdre, 2 tours = anneau ; `recognize()` compte les coins sur le tracé rééchantillonné, test : `node test_formes.js (script de test, non publié)`), lancer une forme, corbeille. L'onglet « Écran » (souris au doigt, `/api/pc/ws`) a été retiré à la demande. Lissage filtre 1€, une détection par image caméra. L'onglet « Caméra » du panneau de gauche ouvre / ferme la fenêtre.
ecognize()), lancer une forme, corbeille. ÉCRAN : l'écran principal en calque (/api/pc/ws, JPEG mss) ; paume ouverte 1,2 s = armer la VRAIE souris, index = pointeur, pincer = clic, pouce+majeur = clic droit, deux doigts = défilement, poing 1,2 s / Échap = désarmer. Lissage filtre 1€, une détection par image caméra.
- La page tient la webcam (une seule appli à la fois) ; en direct elle envoie 1 image/s (vidéo + formes) à `/api/cam/frame`
  → `_cam_forward` → Gemini Live. `jarvis_window.py` autorise la caméra de `http://127.0.0.1` sans demande
  (`PermissionRequested`, posé depuis le fil de la fenêtre : CoreWebView2 ne se touche que par `Invoke`).
- Coupée par : fermeture, pause, micro coupé, jeu, 10 min. Tests : `window.CAM3D._fake` (mains simulées) + `CAM3D.tick()`.

