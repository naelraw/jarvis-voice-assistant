# Services externes, clés et quotas

Règle : **n'utiliser que des services gratuits à gros quota**, avec un secours prévu quand ils tombent. Un modèle
Gemini qui renvoie 429 n'est plus appelé avant `_quota_reset()` (minuit en Californie ≈ 9 h en France) ;
`_COOLDOWN`, `_AGENT["bad"]`.

## Gemini (clé Google AI Studio, version gratuite)

| Modèle | Quota | Usage |
|---|---|---|
| `gemini-3.8-live` | illimité | voix + cerveau en direct (PC et téléphone) |
| `gemini-3.1-flash-live-preview` | — | secours de la conversation en direct |
| `gemini-3.5-flash-lite` | 500 / jour | cerveau classique, transcription de secours, secours de tout |
| `gemini-3.8-flash` | ~20 / jour | agent qui pilote les applis (`operate_app`) seulement ; secours Flash Lite |
| TTS (2.5 flash tts, 3.8 flash lite tts…) | 10 / jour | seulement l'aperçu des voix (mis en cache) |
| `gemini-3.5-transcribe` | 25 / jour | **pas utilisé** (Whisper local à la place) |
| `gemini-3.8-live-extended-thinking` | — | pas utilisé (plus lent) |
| `gemini-3.5-live-translate-preview` | — | idée : traduction en direct |

Pour lister les modèles disponibles sur ta clé, interroge l'API Google AI Studio (sans jamais afficher la clé).

## Autres services

| Service | Clé | Limite | Usage / secours |
|---|---|---|---|
| Groq | oui (`configurer_groq.ps1`) | 8 000 tokens/min | secours du cerveau classique ; modèle choisi dans la liste réelle (`GROQ_PREFER`) ; seulement `GROQ_TOOLS` ; ~1 s/réponse. Propose aussi whisper-large-v3-turbo (pas branché) |
| YouTube Data API v3 | oui (`configurer_youtube.ps1`) | 10 000 pts/jour (recherche = 100) | sans clé ou quota épuisé : lecture de la page de résultats |
| VirusTotal | oui (`configurer_virustotal.ps1`) | 4/min, 500/jour | empreinte SHA-256 seulement |
| ElevenLabs | oui (`configurer_elevenlabs.ps1`) | offre gratuite | voix du mode classique (réglage `tts`) |
| Deezer (API publique) | non | — | User-Agent de navigateur obligatoire |
| Wikipédia, BCE (Frankfurter), Google Actualités RSS, DuckDuckGo | non | raisonnable | faits vérifiables |
| TheSportsDB | clé publique « 3 » | version gratuite limitée | football |
| Open-Meteo, Nominatim, OSRM, Esri, CesiumJS | non | raisonnable | heure / globe / itinéraires |
| wttr.in | non | — | météo |
| Tailscale | compte (connexion par l'utilisateur) | gratuit | téléphone et accès entre appareils |

## Clés et secrets (`%USERPROFILE%\.openjarvis\`, jamais dans le dépôt)

Toutes chiffrées par Windows (DPAPI) : liées au PC et au compte Windows, impossibles à copier ; se ressaisissent
sur chaque PC avec le script correspondant. **Ne jamais afficher, journaliser ni demander une clé dans le chat**.

| Fichier | Script |
|---|---|
| `jarvis_gemini.json` | `configurer_gemini.ps1` |
| `jarvis_groq.json` | `configurer_groq.ps1` |
| `jarvis_youtube.json` | `configurer_youtube.ps1` |
| `jarvis_virustotal.json` | `configurer_virustotal.ps1` |
| `jarvis_elevenlabs.json` | `configurer_elevenlabs.ps1` |
| `jarvis_mail_accounts.json` (mots de passe d'application) | `configurer_mails.ps1` |
| `jarvis_pcradar.json` (code admin d'un site perso, optionnel : voir README) | `configurer_pcradar.ps1` |
| `jarvis_calendar.json` (script Google Agenda) | `configurer_agenda.ps1` |
| `jarvis_apis.json` (API ajoutées, `secret_dpapi`) | page « API » de JARVIS |
| `jarvis_mobile_key` (jumelage du téléphone) | créé au 1er lancement |
