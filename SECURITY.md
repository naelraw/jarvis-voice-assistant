# Sécurité

## Signaler une faille

Merci de **ne pas ouvrir de ticket public** pour une faille de sécurité.

Utilise le signalement privé de GitHub : onglet **Security → Report a vulnerability** de ce dépôt. Décris ce que tu as
trouvé, comment le reproduire et l'effet possible. Je réponds dès que possible, à titre bénévole (projet personnel).

## Ce que JARVIS protège (et ses limites)

- Les clés d'API et mots de passe d'application sont **chiffrés par Windows (DPAPI)** dans
  `%USERPROFILE%\.openjarvis\` : liés à un PC et à un compte Windows.
- Le serveur local écoute sur `127.0.0.1:8765` seulement. L'accès depuis le téléphone passe par Tailscale et une clé
  de jumelage (en-tête `X-Jarvis-Key`) ; les routes sensibles vérifient aussi l'origine.
- Les connecteurs d'API refusent les adresses privées (protection contre l'accès au réseau local par un lien piégé).
- Les actions sensibles demandent une confirmation orale.

Limites : JARVIS agit avec **tes** droits sur ton PC. Pendant une conversation en direct, l'audio est envoyé à Google
(Gemini). Ne rends pas le serveur accessible depuis internet.

## Si tu as publié une clé par erreur

Révoque-la tout de suite chez le fournisseur (Google AI Studio, Groq, etc.), puis crée-en une nouvelle.
