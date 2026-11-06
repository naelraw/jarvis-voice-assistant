# Fenêtre et interface du PC

À lire avant de toucher à : `jarvis_window.py`, `index.html`, `show_jarvis_window`, le ws `/ws`, le style.

## La fenêtre

- `jarvis_window.py` : processus séparé, pywebview / WebView2, **sans cadre** (aucun bouton Windows), titre
  « JARVIS », icône JARVIS dans la barre des tâches (AppUserModelID `JARVIS.VoiceAssistant` + `WM_SETICON` jarvis.ico ;
  `creer_raccourci_jarvis.ps1` crée le raccourci du menu Démarrer avec la même identité). `--small` = ouverture
  discrète, `--screen` = écran choisi. Si pywebview manque : Edge en mode application (ancienne méthode, secours).
- Pourquoi pas Edge : une fenêtre `--app` hors plein écran garde TOUJOURS la barre d'Edge (même en retirant
  WS_CAPTION), et un plein écran F11 refuse d'être rapetissé.
- `_watchdog()` : la fenêtre se ferme seule 15-20 s après la disparition du serveur (sinon elle restait figée).
- Garde-fou « une seule ouverture à la fois » (`_OPENED_AT`, 15 s) : il bloquait la réouverture d'une fenêtre fermée
  juste après son ouverture (claquement 2 s après l'avoir fermée → brief dit SANS fenêtre, 2026-10-17). Il ne
  bloque plus si une fenêtre s'est connectée/déconnectée depuis (`STATE.last_client_change`), et il est remis à
  zéro à la fermeture.
- Côté serveur : `show_jarvis_window(manual)` (refuse en jeu sauf `manual`), `bring_jarvis_front`, `_force_front`
  (AttachThreadInput…), `_rescue_offscreen`, `open_window`. `window_command` : réduire, ⛶ = `_jarvis_size`
  grand (tout l'écran, barre des tâches comprise) ↔ petit (centrée, 2/3 de l'écran), fermer. La bande du haut
  (`#drag`, classe `pywebview-drag-region`) déplace la petite fenêtre ; double-clic = grand/petit.
- **Petit écran / tablette** (2026-10-16, PC gamer : tablette en écran secondaire, DISPLAY7 960×600 « points »
  à 200 %, sans EDID = écran virtuel) : canevas dessiné à `devicePixelRatio` (plafonné x2, `ctx.setTransform`) sinon
  la sphère était agrandie et floue ; sphère à 21 % de la place (au lieu de 17 %) quand elle fait moins de 650 px ;
  panneau de gauche réduit par défaut sous 1200 px de large (souvenir à part : `jarvis_side_petit`) ; horloge et
  bandeau plus discrets (`@media (max-width: 1100px), (max-height: 700px)`, placé en FIN de `<style>` pour passer
  après les règles `#clock`). Vérifié à 960×600 avec `test_interface_factice.py`.
- **Écran secondaire** : `jarvis_screen` = « secondaire » (défaut) ; `_monitors`, `_jarvis_monitor`,
  `_jarvis_size(mon)`. Portable : principal 1920×1080 (125 %), secondaire 1920×1200 (200 %) à gauche (x = -1920).
- **Fenêtre hors des écrans** (2026-10-17) : retrouvée à x = 4296 alors que les écrans s'arrêtaient à 3840 (après le
  passage de spacedesk à l'écran virtuel d'Apollo / changement d'échelle) → « elle disparaît et ne revient pas ».
  `jarvis_window._keep_on_screen()` vérifie toutes les 1,5 s qu'au moins 120×80 px sont sur un écran, sinon la
  replace au centre de l'écran choisi (`small_rect`).
- **Déplacement de la petite fenêtre** (2026-10-17) : la zone `pywebview-drag-region` déplaçait la fenêtre depuis la
  page à chaque mouvement → elle disparaissait pendant le glissé (écrans d'échelles différentes). Maintenant
  `jarvis_window.Api.start_drag()` (js_api) : `ReleaseCapture` + `WM_SYSCOMMAND SC_MOVE|HTCAPTION` = déplacement
  natif de Windows ; la page l'appelle au `mousedown` sur `#drag` (événement `pywebviewready`), double-clic =
  grand/petit. Sans js_api (ancienne fenêtre), la classe pywebview reste en secours.
- Pièges : fenêtre bloquée à -32000 (inclickable) → ne jamais `MoveWindow` une fenêtre réduite
  (`SetWindowPlacement`) ; l'overlay AMD (DVR) vole le premier plan → `_is_overlay`.

## index.html (relu à chaque requête : pas besoin de redémarrer)

- **Sphère « plexus » 3D** (points reliés, anneaux, réagit à la voix) + horloge. Couleurs selon l'état (orange =
  tâche en cours). Double-clic sur la sphère = pause / reprise. NE PAS changer la sphère sans demande.
- **Style HUD façon Iron Man** (menus et textes) : cadres fins + équerres lumineuses (`.hudbox`, `.cn1/.cn2`),
  majuscules espacées en Bahnschrift, chiffres en Cascadia Mono, règles graduées (`.ticks`), coins de l'écran
  (`#frame`), lignes de balayage, bandeau d'état en bas (`#hudbar` : état, micro, PC Radar, synchro ; `.opt`
  cachés sous 1500 px).
- **Panneau de gauche « Tableau de bord »** (fixe, réductible en barre d'icônes, souvenir `localStorage`
  `jarvis_side`) : onglets Agenda, Rappels, Notes, PC Radar, Mails, API ; pastille orange = à traiter. Un onglet
  ouvre une page (`#page`) : agenda 7 jours, rappels, notes (`/api/dashboard/note`), PC Radar (graphique 7 jours,
  `/api/dashboard/pcradar`), 10 derniers non lus par boîte. Données : `GET /api/dashboard` →
  `dashboard_payload()` ; agenda, PC Radar et mails relus toutes les 2 min au plus (`_DASH`, seulement quand la
  page interroge, jamais en jeu) ; la page interroge toutes les 45 s (pas en jeu) et ne se redessine que si ses
  données changent. Sphère et horloge se placent à droite du panneau (`sideW()`, `--sidew`).
- **3 boutons en bas** (`#controls`) : **Clavier** (ws `ask:<texte>` → `ask_typed()` : sort de la pause puis
  `dispatch()` ; Entrée envoie, Échap ferme), **Micro** (ws `mic_toggle` → `set_mic_muted()`, `STATE.mic_muted`
  gardé après redémarrage, fichier `jarvis_micmute` qui endort aussi les claquements ; bouton rouge + « MICRO
  COUPÉ » ; ne vaut QUE tant que JARVIS est allumé : rallumé tout seul quand la fenêtre se ferme ou au redémarrage,
  pour que « OK Jarvis » et les claquements puissent toujours le rouvrir — 2026-10-17), **Pause** (ws `toggle_pause` ; « Reprendre » quand en pause). `quit_jarvis()` existe sans bouton.
  Plus le bouton du mode d'écoute (« Sur « Jarvis » » / « Écoute tout », voir voix-et-micro.md).
- **Conversation sous la sphère** (`#chat`, 14 px, top 50 % + 27vmin, sans boîte) : seulement le dernier échange,
  sa phrase en orangé, la réponse en cyan, 3 lignes max. Alimentée en direct par les transcriptions de Gemini Live
  (`CHAT.stream/end`) et par `dispatch()`, envoyée par /ws (type « chat », réglage `show_chat`). S'efface 8 s
  après la dernière nouveauté (12 s si un message est resté « en cours ») et ne revient pas tant que son texte ne
  change pas (`chatGone`).
- **Panneau de tâche** (`_task_start/_task_step/_task_end`) : progression en direct d'une tâche (`operate_app`,
  Claude Code…). Petites fenêtres `show_on_screen` (même titre = remplacée, à droite du panneau).
- **Onglet Clips** (2026-10-16) : liste des vidéos de `~/Videos` (clips OBS) et du dossier AMD ReLive (`_clip_dirs`,
  `_clip_files`, 300 max, les plus récentes d'abord), lecteur + vignettes (`<video preload=metadata>`, `#t=1`),
  « Voir dans le dossier » (`/api/clips/show`), « Supprimer » en 2 clics → CORBEILLE (`clip_delete`,
  SHFileOperationW + FOF_ALLOWUNDO, jamais définitif). Routes `/api/clips`, `/api/clips/file` (lecture par morceaux,
  206), `/api/clips/delete`, jeton local ; un identifiant = chemin encodé, refusé hors des dossiers de clips (testé).
  Résumé `clips` dans `/api/dashboard`. Les clips OBS sont en HEVC : lus par WebView2 grâce au décodage de la carte.
  Piège : une `<video>` retirée de la page (changement de page, fermeture) continue de JOUER en fond →
  `stopClips()` (pause + src retirée) dans `openPage`, au `pagehide`, et pause quand la fenêtre est cachée ;
  pas de redessin automatique de la page Clips pendant qu'une vidéo joue.
- **Bouton Pause / double-clic sur la sphère** : en silence (`set_paused(..., announce=False)`) ; « Ok, je me mets en
  pause » seulement quand on le demande à l'oral (demandé le 2026-10-16).
- **Minuteurs** (`UIX["timers"]`, type « uix ») : anneau en haut à droite, ✕ = `timer_cancel:<id>`.
- **Globe 3D** (`UIX["globe"]` → `onGlobe()`) : CesiumJS 1.121 (jsdelivr, chargé au 1er usage) + imagerie Esri.
  Piège : une règle CSS `canvas {position: fixed}` agrandissait le canevas de Cesium → réservée à `#c`.
- **Paramètres** (⚙) : réglages, micro et sortie son, claquements, heures de cours, téléphone (QR), Claude Code…
  enregistrés par `POST /api/settings` (jeton local + Origin) dans jarvis_voice.toml.

## Tester l'interface

- `test_interface_factice.py` (script de test, non publié) : copie de l'interface avec de fausses données, servie à part, SANS
  micro. Adresses : `#demo` (messages + minuteurs), `#globe=route`, `#globe=tokyo`, `#boutons`.
- Une page d'essai servie à part : ajouter `?v=<heure>` (WebView2 garde sinon l'ancienne version en cache).
- Toujours vérifier la **console** du navigateur (aucune erreur). Un onglet `/` ouvert compte comme une fenêtre
  JARVIS (rouvre le micro) : le fermer après, et jamais pendant les heures de cours.

- **Allumage du PC** (2026-10-17) : `_boot_open()` (lancé en `--background`) ouvre JARVIS via `summon()` si le PC est
  allumé depuis moins de 10 min (pas à une simple relance), après avoir attendu le 2e écran (tablette) jusqu'à 2 min.
  Jamais en jeu, ni en heures de cours, ni si la fenêtre est déjà ouverte. Réglage `open_at_boot` (oui par défaut).
