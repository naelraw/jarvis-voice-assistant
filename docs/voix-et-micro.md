# Voix et micro : écoute, compréhension, conversation en direct

À lire avant de toucher à : `Ear`, `transcriber`, `LiveSession`, `BRAIN`/`MOUTH`, les seuils de volume, les modes
d'écoute, le choix du micro ou de la sortie son.

## Chaîne complète

1. **Ear** (micro du PC, sounddevice 16 kHz, trames de 30 ms) : détecte la voix, gère la coupure de parole
   (barge-in) et envoie l'audio soit à Gemini Live (conversation ouverte), soit au transcripteur.
2. **transcriber** (Whisper local) : guette « Jarvis » quand aucune conversation n'est ouverte.
   - `_whisper(name, threads)` : sur une carte NVIDIA si possible (`large-v3-turbo`, `int8_float16`, ~1 Go de
     mémoire vidéo, 0,7 à 1 s par phrase sur la RTX 3050 du portable). DLL CUDA fournies par les paquets
     `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` (`requirements-nvidia.txt`, `_cuda_dlls()`).
   - Carte AMD (PC gamer, RX 6650 XT, 2026-10-17) : **whisper.cpp compilé avec Vulkan**, `large-v3-turbo` q8_0
     (`~/.openjarvis/whisper/`), petit serveur local `whisper-server.exe` port 8767 (`_vk_start`, `_VkWhisper`).
     0,65-1,2 s par phrase (small sur le processeur : ~2,2 s). Arrêté pendant les jeux (`_vk_stop`), relancé à la
     fin. Compilation : `outils/whisper.cpp` (tag v1.9.5), SDK Vulkan LunarG + Build Tools VS 2022,
     `build_vk.cmd` (`-DGGML_VULKAN=1 -DBUILD_SHARED_LIBS=ON`). Réglage `whisper_vulkan` (oui par défaut).
   - Sans aucune carte utilisable : processeur, et `small` à la place d'un gros modèle (2 à 11 s sinon).
   - **En jeu** : « OK Jarvis » reste guetté par Vosk (local, minuscule) ; la demande qui suit est transcrite par
     **Groq** (`_groq_stt`, whisper-large-v3-turbo, gratuit) pour ne rien prendre au PC ; petit Whisper `base`
     sur le processeur seulement si Groq ne répond pas ou s'il n'y a pas de clé (`game_groq`).
   - Déchargé pendant les jeux (libère ~1,5 Go). `LOCAL_STT["fn"]` l'expose (téléphone en pause).
   - Piège : pip a échoué une fois (« fichier utilisé par un autre processus », antivirus) → `pip download -d`
     puis `pip install` des fichiers .whl.
3. **LiveSession / LIVE** : conversation vocale Gemini Live (`live_model` = `gemini-3.8-live`, voix `live_voice`
   = Charon, secours `gemini-3.1-flash-live-preview`). Ouverte au réveil, fermée après `live_idle_seconds`.
   Outils exécutés par `_run_tool` (thread-local `_LIVE_TL` : session, confirmed). `say()` = lui faire dire une
   phrase avec SA voix (annonces, pause, alertes). Hooks : `extra_prompt`, `_keep_open()`.
4. **BRAIN** : cerveau « classique » (texte) quand Live n'est pas disponible : Gemini → Groq → modèle local
   (qwen3, PAS installé). **MOUTH** : voix hors Live (redirige vers `LIVE.say`).

## Comprendre SA voix (et pas la pièce)

- **Volume de sa voix appris PAR MICRO** (`voice_levels_mic` dans jarvis_state.json, `_use_mic_levels()` à
  l'ouverture du micro, `_note_voice_level`). Pourquoi : appris sur le micro du PC (~0,15), il faisait prendre la
  voix des écouteurs CMF (~0,03) pour du bruit → des mots partaient en silence vers Gemini. Avant d'être gardé
  dans l'état, le filtre repartait de zéro à chaque redémarrage et laissait tout passer.
- **Gain Live** adapté à ce volume (0,2 / volume, entre 1 et 8 ; un x5 fixe saturait le micro du PC), écrêtage
  doux (tanh), 1,2 s de marge après la voix (`live_hold`), 1,1 s de silence avant que Gemini réponde
  (`live_silence_ms`) pour les phrases hésitantes.
- **Voix de fond** (portable) : sa voix ~0,10-0,13, conversations / télé de la pièce ~0,01-0,03. Filtre
  `STATE.user_levels`, seuil = 45 % de sa médiane, pour Gemini Live et Whisper.
- **Vidéo / télé presque aussi forte que lui** (0,06-0,08 contre 0,11) : Gemini entendait « Shalom », « de la
  voluntad »… et la vidéo lui coupait la parole. Filtre `voice_filter` (0,6 de sa voix, réglable), couper la
  parole demande ≥ 90 % de sa voix. Le vrai remède reste un micro près de la bouche (casque G435 + dongle USB).
- Pendant qu'il parle, il faut au moins 0,03 de volume pour le couper tant que sa voix n'est pas apprise.
- S'il n'est pas sûr d'avoir compris une action, il fait répéter au lieu de deviner (`LIVE_PROMPT`).
- **Gemini invente des mots sur du bruit pur** (une note → « appelle papa ») ; Whisper aussi (`HALLUCINATIONS`).

## Deux modes d'écoute

Bouton « Sur « Jarvis » » / « Écoute tout » (`#btnAll`, ws `listen_all_toggle`, `set_listen_all()`,
`STATE.listen_all`, envoyé dans le ws `all`, jamais gardé après un redémarrage).
- **Mode de base** : il ne réagit que si la phrase commence par « Jarvis » / « OK Jarvis ». La fenêtre JARVIS au
  premier plan ne compte PAS comme conversation (`in_conv`, `_keep_open`, `ui_state`). Conversation Live fermée
  après `live_idle_seconds` = 10 s de silence.
- **Écoute tout** : conversation Live gardée ouverte (`LISTEN_ALL_PROMPT`), `in_conv` toujours vrai, « ÉCOUTE
  CONTINUE » dans la barre du bas. Tout part chez Gemini : ne pas le laisser en permanence.
- Reprise (claquement, bouton, « Jarvis, reprends ») : PAS de suite de conversation, il faut redire « Jarvis ».
  Suite de conversation sans « Jarvis » : il faut au moins 85 % du volume de SA voix (`follow_voice_filter`), sinon
  une vidéo presque aussi forte recevait une réponse (2026-10-17).
- Après une ANNONCE (nouveau mail, rappel, « pendant ce temps… »), la conversation reste ouverte `announce_reply_seconds` (15 s)
  pour que tu répondes SANS redire « Jarvis » (`announce_reply`, `_REPLY_AFTER`, `LiveSession._after_turn`) ; pas après la pause,
  en jeu, ni pour les annonces de pause / reprise. Dire « Jarvis » pendant qu'il parle le coupe (`_kws_hit`, Vosk libre).
- Changer de mode ne coupe plus sa phrase (2026-10-17) : vers « Écoute tout », la conversation déjà ouverte est
  juste gardée ouverte (le message de mode n'est envoyé que si aucune conversation n'est ouverte) ; vers le mode de
  base, la conversation se ferme APRÈS sa réponse en cours (`close_after_reply`, 60 s max).

## Détails de Gemini Live (ne pas casser)

- **Texte en pleine conversation** : `send_realtime_input(text=...)` (les modèles 3.x ignorent
  `send_client_content` après le début) ; le 1er message garde `send_client_content`. Un texte arrivé pendant
  l'ouverture attend dans `LIVE._pending`.
- **Audio proactif GARDÉ** : sans lui, le moindre bruit du micro des écouteurs coupait ses phrases. Ne JAMAIS
  écrire `proactive_audio=False` : gemini-3.8-live refuse (erreur 1007) ; il faut omettre l'option.
- **Micro fermé pendant une conversation** (bouton micro, heures de cours, jeu) : l'oreille envoie du SILENCE en
  continu à Gemini. Sans aucun son reçu, Gemini coupait ses réponses en pleine phrase et la liaison tombait.
- « Réponse inachevée : » dans le journal = conversation fermée avant la fin d'une réponse.
- Pas de « répète mot pour mot » ni « exactement ta voix » dans les consignes : ça changeait son timbre.

## Problèmes dits et affichés

`report_problem()` → `explain_problem()` traduit l'erreur en clair (genres : net, slow, quota, key, config, cut,
mic_missing, mic_dead, other), ouvre une fenêtre « Problème : … » (ce qui se passe / que faire / détail) et le
DIT. Si Gemini est en cause : `MOUTH.say(direct=True)` avec la voix Windows hors ligne (Hortense, `_sapi_say`,
System.Speech → WAV). Même genre pas répété avant 90 s. Branché sur : Live indisponible / coupé, réponse
inachevée, cerveau classique (`BrainDown`), micro introuvable, micro qui n'envoie que des zéros 5 s.

## Choix du micro et de la sortie son

- Paramètres → « Micro de JARVIS » (`mic_device`, lu par `Ear` via `_mic_index`, noms MME tronqués à 31 car.) et
  « Micro des claquements » (`clap_device`). Vide = automatique. Boutons « Tester » (3 s via
  `jarvis_clap.py --mic-level NOM [--clap]`, processus à part : la liste des micros y est relue à neuf),
  « Calibrer », « Test en direct ». Liste : `--list-mics`.
- Micro par défaut muet (2 ouvertures sans son) → `Ear` passe seul sur le micro intégré (`fallback`), sauf si un
  micro a été choisi. Écouteurs Bluetooth rangés = micro qui n'envoie RIEN (sd.rec attend sans fin → toujours un
  flux avec rappel et délai).
- « Sortie son de JARVIS » (`out_device`, `_out_index`) + bouton « Tester le son » (`test_out`).
- **Piège** : PortAudio garde la liste des périphériques du démarrage. Après déconnexion / reconnexion des
  écouteurs, JARVIS parlait dans l'ancienne connexion (aucun son). `_audio_watch` surveille les sorties Windows
  (waveOut, toutes les 3 s) et relit la liste dès qu'elle change.
- **Écouteurs CMF Buds Pro 2 (portable)** : leur MICRO n'envoie aucun son et l'ouvrir les fait basculer en « kit
  main-libre » (son coupé). Ne jamais ouvrir leur micro, même pour un test. Leur SORTIE marche (sortie par défaut).
  Le haut-parleur Realtek du portable est coupé dans Windows (à l'utilisateur de le réactiver).
