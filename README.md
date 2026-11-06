# JARVIS — assistant vocal pour Windows

[English version](README.en.md)

JARVIS est un assistant vocal **mains libres** pour Windows, avec une **appli web pour téléphone** (testée sur iPhone).
Tu lui parles (« OK Jarvis »), il répond à voix haute et **agit sur ton PC** : ouvrir des applis, lancer un jeu,
lire et envoyer des mails, jouer de la musique, chercher sur internet, mettre un rappel, prendre une note…

Il est pensé **en français** et pour rester **gratuit** : il fonctionne avec une clé Gemini gratuite (Google AI
Studio), la reconnaissance vocale locale tourne sur ton PC (carte NVIDIA, ou processeur), et les autres services
sont facultatifs.

> **Statut : projet personnel, en développement actif, une seule personne.** Il marche tous les jours sur le PC de son
> auteur, mais n'a pas été essayé sur beaucoup de machines. Les retours (bugs, idées, matériel qui pose problème)
> sont très utiles : ouvre un ticket !

## Ce qu'il sait faire

- **Voix** : conversation en direct avec Gemini Live (PC et téléphone), reconnaissance de « OK Jarvis », détection
  d'un double claquement de mains, transcription locale avec Whisper (`faster-whisper`).
- **Appli sur PC** : applis et sites web, jeux (il se met en veille pendant une partie), clips de jeu avec OBS,
  mails (IMAP), agenda Google, rappels, minuteurs, notes, musique et YouTube, météo, actualités, Wikipédia,
  change, VirusTotal (envoie seulement l'empreinte d'un fichier, jamais le fichier).
- **Téléphone** : une appli web (PWA) servie par ton PC à travers [Tailscale](https://tailscale.com) (gratuit), avec
  boutons Pause / Micro / Clavier, et des **notes hors ligne** qui s'envoient quand le PC est de nouveau joignable.
- **Réveil du PC** à distance (Wake-on-LAN) via un relais allumé en permanence.
- **Connecteurs d'API** : une page pour brancher tes propres API (clés chiffrées, protection contre l'accès au
  réseau local).
- **Fenêtre Caméra** : suivi des mains (MediaPipe, téléchargé au premier usage) pour dessiner des formes 3D dans l'air.
- **Optionnel** : visionneuse 3D et impression 3D, tablette Android en second écran, pont vers un Copilote Roblox,
  intégration d'un site perso (`pcradar`, voir ci-dessous).

La liste détaillée est dans [`docs/fonctions.md`](docs/fonctions.md).

## Installation (Windows 10 / 11)

1. Récupère le dépôt (**Code → Download ZIP** puis extraire, ou `git clone`).
2. Ouvre le dossier `installation` et double-clique sur **`INSTALLER JARVIS.bat`**.
   Si Windows affiche « Windows a protégé votre ordinateur » : *Informations complémentaires → Exécuter quand même*
   (le script est lisible dans `installation/installer.ps1`).
3. Laisse faire (5 à 15 minutes) : Python 3.13 si besoin, les modules, les raccourcis, le démarrage avec Windows.
4. À la fin, colle ta **clé Gemini** (gratuite : <https://aistudio.google.com/apikey>). Le reste est facultatif.
5. Le premier lancement télécharge la reconnaissance vocale (~500 Mo).
6. Dans **Paramètres**, indique ton prénom (« Ton prénom »), puis dis **« OK Jarvis »**, double-claque dans tes mains,
   ou fais `Ctrl+Alt+J`.

Détails et dépannage : [`installation/LISEZ-MOI.txt`](installation/LISEZ-MOI.txt).

À la main (développeurs) :

```powershell
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
# carte NVIDIA seulement : .venv\Scripts\pip install -r requirements-nvidia.txt
.venv\Scripts\python jarvis_voice.py
```

## Ce qu'il faut savoir avant de l'utiliser

- **Windows uniquement** (il utilise des API Windows : DPAPI, UI Automation, fenêtres natives).
- **Interface et commandes en français.** Les fichiers de code et la documentation sont en français.
- **Vie privée** : pendant une conversation en direct, **l'audio est envoyé à Google (API Gemini)**. Les mails,
  l'agenda et les autres services ne sont lus que si tu les configures. Les clés d'API sont chiffrées par Windows
  (DPAPI) dans `%USERPROFILE%\.openjarvis\`, jamais dans le dépôt.
- **Actions sensibles** (envoyer un mail, éteindre le PC, supprimer…) : JARVIS demande une confirmation orale.
- Le serveur local écoute sur `127.0.0.1:8765`. L'accès depuis le téléphone passe par Tailscale et une clé de
  jumelage ; ne l'expose pas sur internet autrement.
- Limites gratuites : les quotas de Gemini, Groq, YouTube, etc. changent : voir
  [`docs/services-et-quotas.md`](docs/services-et-quotas.md).

## Intégrations facultatives de l'auteur

Le dépôt contient aussi des liens vers des projets personnels de l'auteur. Ils ne font rien tant qu'ils ne sont pas
configurés, et tu peux les ignorer :

- `pcradar` : récap et relevé de prix pour le site de l'auteur. Sert d'exemple pour brancher **ton propre site** (il
  faut un code admin côté site).
- Copilote Roblox : [`docs/roblox.md`](docs/roblox.md).
- Impression 3D (Ender 3), tablette-écran : voir `docs/`.

## Documentation

| Fichier | Contenu |
|---|---|
| [`docs/fonctions.md`](docs/fonctions.md) | tous les outils et comportements |
| [`docs/voix-et-micro.md`](docs/voix-et-micro.md) | reconnaissance vocale, micro, modèles |
| [`docs/claquements.md`](docs/claquements.md) | détection des claquements de mains |
| [`docs/telephone.md`](docs/telephone.md) | appli téléphone, Tailscale, notes hors ligne |
| [`docs/reseau-et-reveil.md`](docs/reseau-et-reveil.md) | Wake-on-LAN, réseau, arrêts inattendus |
| [`docs/fenetre-et-interface.md`](docs/fenetre-et-interface.md) | fenêtre, interface, tablette |
| [`docs/services-et-quotas.md`](docs/services-et-quotas.md) | services externes, clés, quotas |

## Contribuer

Les contributions sont les bienvenues, même petites (documentation, traduction, test, bug reproduit). Lis
[`CONTRIBUTING.md`](CONTRIBUTING.md). Pour une faille de sécurité : [`SECURITY.md`](SECURITY.md).

## Licence

[MIT](LICENSE). Les services tiers (Google Gemini, Groq, ElevenLabs, YouTube, etc.) ont leurs propres conditions
d'utilisation.
