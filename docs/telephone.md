# Téléphone (iPhone) et plusieurs appareils

À lire avant de toucher à : `mobile.html`, `PhoneLive`, les routes `/m` et `/api/m/*`, Tailscale.

## Principe

L'iPhone ouvre une appli web servie par le PC via **Tailscale Serve** (`https://<nom-du-pc>.<tailnet>.ts.net/m`).
Le téléphone ne fait que micro + haut-parleur : c'est le PC qui comprend, agit et parle (même voix, même cerveau).

## Flux en direct (PhoneLive / PHONE_LIVE)

Sous-classe de `LiveSession`. WebSocket `/api/m/ws` :
- 1er message `{key}` (clé de jumelage), puis le téléphone envoie son micro (PCM 16 kHz int16, morceaux de 100 ms)
  et reçoit la voix (PCM 24 kHz, jouée sans trou) + des messages JSON d'état (`paused`, `thinking`, `heard`, `sub`).
- Une file de son par téléphone (`outs`) : deux téléphones peuvent écouter le même JARVIS.
- Délai mesuré : ~1 s entre la fin de la phrase et le 1er son (l'ancienne méthode HTTP + TTS : ~5 s, et une
  voix différente quand le quota TTS lâchait → abandonnée).
- Pendant qu'il parle, seule une vraie voix (plus forte que l'écho de la sienne) peut le couper.
- Le micro du PC est ignoré pendant que le téléphone écoute / répond (sinon double réponse).

## Routes HTTP

- `/m` : la page (nom du PC injecté : `pc_label()` = réglage `pc_label` ou nom Windows), `/m/manifest.json`
  (nom de l'icône « JARVIS <nom du PC> », clé gardée dans `start_url`), `/m/icon.png`.
- `/api/m/autopair` : donne la clé si l'en-tête Tailscale `Tailscale-User-Login` = compte du propriétaire du PC.
- `/api/m/hello` : ouvre JARVIS sur le PC (jamais en jeu ni en heures de cours).
- `/api/m/voice` : en pause, vérifie « Jarvis, reprends » (transcription par Whisper local, `phone_transcribe`).
- `/api/m/poll` : tâche en cours sur le PC. `/api/m/pair` : QR code pour la page des paramètres.
- `mobile_push(text)` : dire un message sur le téléphone (alertes, résultats de tâches).

## Pause commune

`STATE.paused` est la seule vérité pour le PC et le téléphone. Sur le téléphone en pause, le micro reste ouvert
mais seules les phrases qui commencent par « Jarvis, reprends / reviens / tu peux reprendre » le réveillent.

## Fonctions du téléphone (2026-10-17)

- **Notifications même appli fermée** (Web Push) : `mobile_push()` → si l'appli n'est pas ouverte, `web_push()`
  (pywebpush 1.14.1). Clé VAPID dans `~/.openjarvis/jarvis_vapid.pem` (créée avec `cryptography` :
  `Vapid().generate_keys()` plante avec les versions récentes), abonnements dans `jarvis_push_subs.json` (404/410 =
  oubliés). Service worker servi à `/sw.js`. Le téléphone demande l'autorisation au 1er toucher (l'iPhone l'exige),
  puis `/api/m/vapid` + `/api/m/push_sub`. iPhone : seulement l'appli AJOUTÉE À L'ÉCRAN D'ACCUEIL, iOS 16.4+.
  `sub` VAPID = l'adresse https du PC (Apple refuse un mail).
- **« Montre-moi l'écran du PC »** : `phone_show_screen` → message ws `{"ev":"image","jpg":…}` (`_out(("json",…))`),
  affiché 20 s, un toucher ferme.
- **« Regarde ça »** : `phone_camera` → ws `{"ev":"camera"}`, appareil photo arrière, photo dans 4 s (ou au toucher),
  `POST /api/m/photo`, l'outil attend 45 s puis `gemini_vision`.
- **Présence à la maison** : `_phone_at_home()` = `tailscale ping` de l'iPhone ; chemin direct par une adresse privée
  ou par l'adresse publique de CE PC (même box) = maison ; relais DERP / injoignable = dehors. On lit le DERNIER
  pong (les premiers passent souvent par un relais). Cache 60 s.
- **Rappels « quand je rentre »** : `remind_when_home` → `jarvis_rappels_maison.json` ; `_home_loop` (2 min) arme
  le rappel dès que le téléphone est vu dehors, et l'envoie (notification + alerte si JARVIS allumé) au retour.
- **Réveil du PC depuis le téléphone** : `wake_pc` refuse si la demande vient du téléphone et qu'il n'est pas à la
  maison (demandé par l'utilisateur).
- **« Qu'est-ce que tu as fait aujourd'hui ? »** : `action_journal` renvoie aussi un résumé à dire.
- **« Dis Siri, Jarvis »** : raccourci iPhone (Raccourcis → + → « Ouvrir les URL » avec l'adresse `/m#k=…`,
  nommé « Jarvis »). Pas de code côté PC.
- **Boutons du téléphone** (seulement deux, voulu par l'utilisateur) : Pause/Reprendre (ws `{"cmd":"pause"}`), Micro (coupé = le téléphone
  envoie du silence). Les commandes ws `screen` et `text` (`phone_text`) existent encore côté PC, sans bouton ;
  boutons cachés tant que le téléphone n'est pas jumelé.
- **Actions sur l'iPhone** (`phone_open`) : appel `tel:`, SMS `sms:`, itinéraire `maps://`, applis (`PHONE_APPS`),
  liens, raccourcis (`shortcuts://run-shortcut`), rappel dans l'appli Rappels via le raccourci « Jarvis rappel »
  (à créer sur l'iPhone). ws `{"ev":"open"}` → bouton « Ouvrir » : iOS ne laisse pas une page ouvrir une appli
  sans toucher. Pas d'accès aux contacts de l'iPhone (il faut le numéro).

## Pièges iPhone

- L'appli de l'écran d'accueil n'a PAS la mémoire de Safari : clé gardée dans l'URL `#k=` + manifeste + jumelage
  automatique Tailscale.
- Le son exige parfois un toucher au lancement (le micro est ouvert d'abord : une page qui écoute a le droit de
  jouer du son). `navigator.audioSession.type = 'play-and-record'` : haut-parleur même en mode silencieux.
- Le micro est relancé automatiquement s'il est coupé (appel, autre son, retour dans l'appli).
- Écran gardé allumé tant que l'appli est ouverte (`navigator.wakeLock`, redemandé au retour dans l'appli).
- Chaque `getUserMedia` refait apparaître « Autoriser le micro ? » : la surveillance ne redemande le micro que si
  la piste est vraiment morte (son seulement suspendu → `ac.resume()`). Côté iPhone : Réglages → Apps → Safari →
  Microphone → Autoriser.

## Plusieurs PC

- Chaque PC a son JARVIS, son Tailscale (même compte) et sa page `/m` ; une icône par PC sur l'iPhone.
- Sur chaque PC : Tailscale connecté (par l'utilisateur), puis `tailscale serve --bg 8765` (fait par
  `mobile_link()` à l'ouverture de Paramètres → Téléphone). Activer d'abord MagicDNS + certificats HTTPS dans la
  console d'admin Tailscale (login.tailscale.com/admin/dns).
- Sur un PC où Tailscale est installé mais « Logged out », l'utilisateur doit se connecter lui-même.

## Tester

`test_phone_ws.py` (script de test, non publié) (simule un téléphone, mesure la latence), `test_two_phones.py`. Phrases de test :
synthèse vocale Windows (System.Speech, voix française, WAV 16 kHz mono). Ne JAMAIS sortir JARVIS de la pause
pour un test : un test a déjà capté la vraie voix de l'utilisateur.

## Icône de l'appli (une couleur par PC) — 2026-10-30

Deux PC = deux icônes JARVIS sur l'iPhone : pour ne pas les confondre, chaque PC a sa couleur. Réglage
`phone_icon` (défaut `bleu`) à choisir dans Paramètres → « Icône sur le téléphone » (8 pastilles). `PHONE_ICONS`
(bleu, violet, rose, rouge, orange, jaune, vert, argent) : le logo `logo_1024.png` est recoloré par décalage de teinte
(`phone_icon_png()`, PIL/HSV ; cache dans `~/.openjarvis/jarvis_icons`). Routes : `/m/icon.png` (icône choisie, ou
`?s=<id>&size=96` pour un aperçu), `GET /api/m/icons`, `POST /api/m/icon` (jeton + Origin). Le manifeste garde le nom
« JARVIS <nom du PC> ». iOS GARDE l'ancienne image : après un changement, supprimer l'icône du téléphone, rescanner
le QR code et « Ajouter à l'écran d'accueil ». Ne pas oublier : à chaque PC sa couleur.

## Bouton « Clavier » (2026-10-31, demandé par l'utilisateur)

Un 3e bouton sur le téléphone (Pause, Micro, **Clavier**, Clips) ouvre une zone de saisie au-dessus du clavier de l'iPhone
(placée avec `visualViewport`, la page n'est pas redimensionnée par iOS). Envoi = ws `{"cmd":"text","text":…}` →
`phone_text()` (déjà là) → conversation du téléphone : il répond comme à une phrase dite (voix + sous-titre). Ce qui est
écrit s'affiche en « ✎ … » (pas de transcription pour du texte). Garde-fous côté page : message vide ignoré ; en PAUSE
rien n'est envoyé et un message dit de toucher « Reprendre » (le PC ignore de toute façon le texte en pause, et la
pause : voir la correction du 2026-10-31 ci-dessous) ;
pas de liaison → « Pas connecté au PC ». La zone se ferme après l'envoi ou avec Échap ; la barre est cachée pendant la
saisie. Pas de redémarrage de JARVIS pour une modification de `mobile.html` (relue à chaque ouverture) ; l'appli de
l'écran d'accueil doit être rouverte pour voir le bouton.

### Correction du bouton Clavier (2026-10-31, « le bouton d'envoi ne marche pas »)

Causes : (1) en pause, le message d'erreur s'affichait dans le sous-titre du milieu, CACHÉ par le clavier → le bouton
semblait mort ; (2) sur iPhone, toucher le bouton fait perdre le focus au champ, le clavier se ferme, la zone saute
(`visualViewport`) et le toucher est perdu. Corrections : envoi sur `pointerdown`/`touchstart` avec `preventDefault`
(le focus reste), `click` et Entrée en secours (pas de double envoi : le champ est vidé au 1er envoi) ; messages d'état
DANS la zone (`#kbs`) ; bouton grisé tant que le champ est vide ; bouton ✕ pour fermer. Côté PC, `phone_text()` LÈVE LA
PAUSE (comme `ask_typed` du clavier du PC : écrire = vouloir une réponse), sauf si JARVIS est éteint pour un jeu
(`STATE.game_silence`). Design : pilule vitrée, bouton rond dégradé cyan avec flèche, zone qui glisse en place.

## Notes hors ligne et vitesse du téléphone (2026-10-31)

**Notes sans le PC** (niveau 1 du « JARVIS qui marche PC éteint » ; le niveau 2 = JARVIS léger sur un petit serveur gratuit : idée, pas commencée).
Bouton « Notes » (5e du bas) : feuille plein écran avec zone de texte, « Dicter » (mémo vocal) et la liste des notes avec
leur état (en attente / envoyée / refusée). Tout est gardé SUR LE TÉLÉPHONE (IndexedDB `jarvis_notes`) puis envoyé au PC dès
qu'il répond (liaison ws ouverte, événement `online`, toutes les 20 s, ouverture du panneau) : `POST /api/m/note`
(en-tête `X-Jarvis-Key`) `{id, t, kind: text|audio, text | wav}`. Serveur : `save_phone_note()` → fichier markdown dans
`Documents\Notes Jarvis` (même dossier et format que `start_note`, onglet Notes du tableau de bord) ; un mémo vocal
(WAV 16 kHz mono, jusqu'à 5 min, pris sur le micro déjà ouvert de la page, rien n'est envoyé au PC pendant l'enregistrement)
est transcrit par Whisper (`phone_transcribe`). Idempotent : `jarvis_phone_notes.json` (id → fichier), le téléphone peut
renvoyer. Codes : 200 ok / doublon, 422 refus définitif (note vide, audio illisible, id invalide), 503 « réessaie »
(Whisper en échec), 403 jumelage à refaire. Les plus anciennes partent d'abord ; l'audio est effacé du téléphone après
envoi ; on garde les 30 dernières notes envoyées. `wavB64()` fait maintenant une MOYENNE par bloc (plus de repliement).
**Page ouverte PC éteint** : `/sw.js` garde `/m`, son manifeste et l'icône (`CACHE jarvis-m-v1`) ; réseau d'abord mais 3,5 s
au plus (fini la page blanche interminable quand le PC est éteint), sinon la copie gardée. Le service worker est enregistré
dès l'ouverture (avant : seulement si les notifications étaient acceptées). Pas testé sur iPhone (seulement dans Chrome :
cache + arrêt du serveur) ; iOS peut effacer ces données si l'appli n'est pas ouverte pendant des semaines.

**Vitesse** : mesurée sur le PC avec un téléphone simulé (envoi → 1er son) : conversation fermée 2,5 à 3,7 s, ouverte 0,6
à 0,9 s. Avant, la conversation du téléphone se fermait après `live_idle_seconds` = 10 s de silence, donc presque chaque
message tapé repartait « à froid ». Maintenant `PhoneLive._idle_limit()` = `phone_idle_seconds` (défaut 120 s) et le
bouton Clavier envoie `{"cmd":"warm"}` : `PhoneLive.warm()` ouvre la conversation pendant la frappe. Mesuré après correction :
0,6 s après 14 s de silence (avant 3,3 s) ; 0,9 s après 2 min avec « warm » (2,7 s sans).
Piège de redémarrage : après avoir tué l'ancien JARVIS, ATTENDRE sa disparition (+3 s) avant de relancer ; sinon le nouveau
trouve le mutex d'instance unique, attend 90 s une réponse qui ne vient pas et quitte SANS RIEN ÉCRIRE dans le journal.

### Ajustement (2026-10-31) : le bouton Notes n'existe que PC injoignable

Bouton « Notes » = secours hors ligne seulement. `applyBar()` : PC joignable → Pause, Micro, Clavier, Clips (pas de Notes) ;
PC injoignable (`pcDown` : liaison fermée, ou pas de liaison 5 s après l'ouverture ; remis à faux dès que la liaison
s'ouvre) → seul Notes reste, et le texte d'état dit « pc injoignable · tu peux prendre des notes ». La feuille de notes
ouverte reste ouverte si le PC revient. PC joignable : on demande à l'IA (voix ou clavier) → outils `add_note(text, title)`
(« mets ça en note », note immédiate dans `Documents\Notes Jarvis`, pied de page « Note prise avec JARVIS ») et
`read_notes(query, count)` (relit les dernières notes ou celles qui contiennent des mots) ; `start_note` (dictée longue
jusqu'à « fin de la note ») reste. Piège de test : naviguer vers la MÊME adresse (même `#k=`) ne recharge pas la page.

### État final des notes du téléphone (2026-10-31) : plus de bouton « Notes »

Demande de l'utilisateur : parler ou écrire à JARVIS PAREIL qu'il soit joignable ou non, et que ce soit envoyé quand le PC revient.
- **Pas de bouton Notes.** PC joignable : Pause, Micro, Clavier, Clips ; on parle ou on écrit à JARVIS (« mets ça en note » →
  `add_note`, « lis mes notes » → `read_notes`). PC injoignable (`isOff()` = `pcDown && !wsOk`) : Pause et Clips se cachent,
  il reste Micro et Clavier, et ils créent des NOTES : le clavier (`noteOffline`) garde le texte, le Micro enregistre un mémo
  vocal (`memoToggle`, 5 min max, « Arrêter · 0:07 »). Tout est gardé dans IndexedDB et part au PC au retour (`syncNotes`,
  `POST /api/m/note`) ; sans IA hors ligne, c'est tout ce qui est possible : un vrai JARVIS PC éteint = niveau 2 (petit serveur).
- **Pastille d'état en haut à gauche** (`#pcs`) : vert « PC connecté » (liaison ws ouverte), orange « PC injoignable »,
  gris clignotant « connexion au PC… ». Mise à jour par `applyBar()` (ouverture/fermeture de la liaison, `checkPc()`).
- `#pend` (« 📝 N notes en attente d'envoi », sous l'horloge) n'apparaît que s'il reste des notes à envoyer ; un toucher ouvre
  la liste (relire / supprimer). Le panneau « Notes » n'est plus qu'une liste, sans bouton dans la barre.
- **Détection « PC éteint »** fiable : `checkPc()` fait une vraie requête `/api/whoami` (4 s) au lieu de se fier à la liaison
  en direct, parfois lente en 4G ; le mode notes ne démarre que si elle échoue aussi.
- **Serveur** : `_NOTE_CMD_RE` retire la formule en tête d'une note du téléphone (« mets ça en note : », « note que »,
  « n'oublie pas de noter », « Jarvis, mets ça en note, »…) sans toucher à « Note pour plus tard… » ni à « Notre… ».
  Vérifié : 12 phrases, et 9 contrôles sur le vrai serveur (texte, mémo vocal transcrit, doublon, vide, audio illisible, clé).