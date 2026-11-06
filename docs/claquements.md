# Double claquement de mains (`jarvis_clap.py`)

Processus séparé, lancé avec Windows (dossier Démarrage). Il ouvre ou ramène JARVIS sur un double claquement.

## Détection

- Bloc de 16 ms ; un claquement = **montée brutale** (`clap_jump` x le niveau d'avant), **retombée rapide**
  (`clap_decay`, mesurée par rapport au pic des 3 premiers blocs : les micros « lents » culminent après la
  montée), niveau minimal (`clap_min_peak`), écart au bruit de fond (`clap_ratio`), aigus (`clap_hf`).
- Le détecteur décide ~110 ms après la montée (aigus = meilleur des 3 premiers blocs, un seul événement par
  claquement). Exactement 2 claquements, écart 0,12 à 1,2 s ; le 1er attend le 2e jusqu'à l'écart maximal.
  Seuls les claquements acceptés comptent dans la série (un bruit refusé entre les deux ne casse plus la paire).
- **Jeu ouvert mais en arrière-plan** (2026-10-16 : l'utilisateur sur le bureau avec un jeu ouvert derrière → claquements
  morts) : JARVIS écrit dans `jarvis_game_sleep` « jeu » (jeu au premier plan depuis < 5 s, `_game_in_front`) ou
  « fond » (`_note_game_front`, toutes les 3 s) ; le détecteur rouvre son micro sur « fond ». Un double claquement
  « fond » compte comme un appel à la main (`summon` : `bg_wake`), et JARVIS se rendort tout seul après ~12 s de
  retour dans le jeu (sans conversation en cours).
- **Jamais avec le jeu devant** (le son du jeu en produit de faux) ni en pause fenêtre ouverte, ni en heures de cours
  (fichier `jarvis_quiet`), ni micro coupé (fichier `jarvis_micmute`).
- **Paire ignorée si clavier ou souris utilisés depuis 1 s** avant le 1er claquement (`input_idle_seconds`,
  GetLastInputInfo). Pourquoi : avec les réglages du portable, la frappe et les clics captés par le micro
  au-dessus du clavier ouvraient JARVIS ~10 fois en 8 min ; rien dans le son ne les distingue.
- Case « Réveil par double claquement » (`clap_enabled`), prise en compte sans redémarrage.
- **Pause / reprise par double claquement** (2026-10-17) : fenêtre de JARVIS ouverte ET visible (pas réduite) →
  `summon(source="clap")` bascule la pause (`set_paused(..., announce=False)`, en silence) ; fenêtre réduite → la
  ramène ; fenêtre fermée → l'ouvre. Pas en jeu, pas en heures de cours. Réglage `clap_toggle_pause` (oui par défaut).
  Validé le 2026-10-17 (02:32 pause, 02:32 reprise). Petit son sans voix pour confirmer (`_chime` : « pause » = deux
  notes qui descendent, « wake » = qui montent) : en silence, l'utilisateur ne voyait pas que c'était pris. Ses claquements
  espacés de 3 à 7 s ne forment pas une paire (écart max 1,2 s).

## Réglages validés

- **Portable** (micro Intel Smart Sound, 2026-10-12) : un vrai claquement a 0 à 10 % d'aigus et s'étale sur 2-3
  blocs → `clap_hf` = 0 par défaut ; `clap_jump` 2,5 (le 2e claquement arrive sur l'écho du 1er) ; `clap_decay`
  0,7 (ses claquements retombent à 45-70 %, la voix > 80 %).
- **PC gamer** : casque G435 (dongle USB), claquements nets (aigus élevés, retombée 30-60 %). Vrais claquements :
  niveau 0,10 à 0,92, 26 à 450x le fond, aigus 74-100 %. 2026-10-17 : une vidéo TikTok l'a réveillé (« Oui ? »)
  avec deux sons à 0,066 / 0,040 et 9x / 6x → réglages de CE PC (jarvis_voice.toml) : `clap_min_peak` 0,08,
  `clap_ratio` 12, `clap_hf` 0,3 (sauvegarde `jarvis_voice.toml.avant-claquements`). Le portable garde les siens.
  Si de vrais claquements sont refusés : relancer le calibrage.
  Puis (02:35) l'utilisateur a lancé le calibrage → `clap_min_peak` 0,31, `clap_ratio` 27,5, `clap_jump` 3,5,
  `clap_decay` 0,45 ; `clap_hf` remis à 0 : ses vrais claquements au casque ont parfois 12 % d'aigus seulement
  (refusés), et les sons de vidéo étaient au contraire très aigus → l'aigu ne sert à rien ici.
  Le calibrage avait aussi remis `clap_jump` à 3,5 → chaque « clap-clap » ne comptait que pour UN claquement
  (le 2e arrive sur l'écho du 1er) : remis à 2,5, et le calibrage n'enregistre plus jamais plus de 2,5.
- Micro intégré préféré quand le micro par défaut est un casque Bluetooth (`pick_device(builtin_first=True)`) :
  les écouteurs étouffent le 1er claquement, et ouvrir leur micro dégrade la musique (mode main-libre).

## Calibrage (`jarvis_clap.py --calibrate`, raccourci du bureau)

Essaie des niveaux de plus en plus tolérants (`LEVELS`) et garde le premier qui reconnaît ≥ 3 claquements ;
affiche le micro utilisé, le son le plus fort, les raisons des refus. Si silence total : explique Confidentialité >
Micro (Windows) et le micro coupé ; si claquements filtrés : effets audio / réduction de bruit à couper.
Les réglages `clap_*` écrits par le calibrage sont conservés quand on enregistre les paramètres de JARVIS.

## Outils

`--test` (affiche ce qu'il détecte en direct), `--mic-level NOM`, `--list-mics`,
`enregistrer_claquements.py` (script de test, non publié) (enregistre 10 s avec le micro du détecteur et analyse),
`test_calib.py` (script de test, non publié) (claquements simulés : casque, portable doux, micro filtré). Journal :
`~/.openjarvis/jarvis_clap.log` (« CLAQUEMENT : niveau…, retombée… » / « son ignoré : … »).
