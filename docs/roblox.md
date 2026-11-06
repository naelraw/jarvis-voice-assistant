# Pont optionnel vers un Copilote Roblox

> **Optionnel et réservé à un cas précis.** Cette fonction relie JARVIS à un outil séparé (« roblox-ia », un panneau
> de chat dans Roblox Studio relié à un serveur OpenCode local). Cet outil **n'est pas inclus** dans ce dépôt. Sans lui,
> les outils `roblox_*` répondent que le serveur du Copilote ne démarre pas, et rien d'autre ne change.
> Le code cherche l'outil dans `~/roblox-ia`.

À lire avant de toucher à : `jarvis_roblox.py`, les outils `roblox_*` de `jarvis_voice.py`.

## Ce que le Copilote doit fournir

- Un serveur **OpenCode** local (`127.0.0.1:4096`, authentification Basic avec un mot de passe local).
- Roblox Studio avec son serveur MCP actif, ouvert en mode **Edit**.
- Optionnel : un petit pont (`127.0.0.1:4098`, même API) qui lance Claude Code (`claude -p`) avec le MCP de Studio.

## Le lien avec JARVIS

`jarvis_roblox.py` fait ce que ferait le panneau : `POST /api/session` → `/agent` → `/model` → `/prompt`, puis suit
`GET /api/session/active` et `GET /api/session/<id>/message`. Outils vocaux (aussi depuis le téléphone) :

| Outil | Rôle |
|---|---|
| `roblox_copilote(demande, modele)` | construit dans Studio ; modèle par défaut gratuit, puis autres modèles gratuits ; un modèle PAYANT demande une confirmation |
| `roblox_claude(demande)` | pareil par le pont Claude ; SEULEMENT sur demande explicite ; confirmation orale |
| `roblox_statut()` | Studio ouvert ? serveur en marche ? travaux en cours |
| `roblox_arreter()` | interrompt les travaux en cours |

Le travail est lancé en arrière-plan (`_roblox_watch` : fenêtre « Tâche · Copilote Roblox », 25 min max) ; JARVIS annonce
la fin avec le résumé de l'IA, ou l'échec (si « limite gratuite » : propose de réessayer avec un autre modèle).

## Précautions

- Ne jamais réinstaller le plugin pendant qu'un travail tourne : le lien MCP tombe.
- Studio doit être ouvert en mode **Edit** avec le MCP actif ; ne pas toucher à la place pendant un travail.
- Les limites gratuites des fournisseurs de modèles existent et changent : voir `services-et-quotas.md`.
- Aucune clé ne passe par JARVIS ni par le journal.
- Claude via le pont : exige que `claude` soit connecté (`claude` puis `/login` dans un terminal).

## Tests

Parcours complet testé avec un FAUX serveur HTTP (création de conversation, agent, modèle, message, suivi,
annonce, cas « limite atteinte », serveur absent) : aucun crédit dépensé, rien dans la place. Une vraie construction
n'est pas couverte par les tests automatiques (elle coûte du quota et modifie la place).
