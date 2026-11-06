# Contribuer à JARVIS

Merci de t'y intéresser ! Le projet est petit et maintenu par une seule personne : une contribution, même minuscule,
fait vraiment une différence.

## Façons simples d'aider

- **Tester et signaler** : installe JARVIS, dis ce qui ne marche pas (version de Windows, carte graphique, micro,
  message d'erreur, extrait du journal `%USERPROFILE%\.openjarvis\jarvis_voice.log` **sans clé ni donnée perso**).
- **Documentation** : une étape d'installation floue, une faute, un exemple manquant. L'**anglais** manque
  (README traduit : oui ; docs : non).
- **Tests** : le projet a peu de tests automatiques (les scripts de test locaux ne sont pas encore publiés) :
  des tests simples sur les parties qui ne touchent ni le micro ni le réseau sont les bienvenus.
- **Idées d'outils** : une API gratuite utile (via la page « API »), une commande vocale qui manque.
- **Autres matériels** : cartes AMD / Intel, autres micros, écrans, autres téléphones.

## Avant de coder

1. Ouvre un **ticket** pour les changements importants (nouvelle fonction, refonte) : on se met d'accord avant que tu
   passes du temps dessus.
2. Fais un **fork**, crée une **branche**, change **une seule chose** par pull request.
3. Reste simple : le projet cible des utilisateurs non développeurs (messages clairs, en français).
4. Teste ton changement : lance JARVIS, vérifie que ça démarre (`python jarvis_voice.py --no-single`) et que ta
   fonction marche. Dis dans la pull request ce que tu as testé, et ce que tu n'as **pas** pu tester.
5. `python -m py_compile jarvis_voice.py` (et les autres `.py` touchés) doit passer.

## Règles du projet

- **Jamais de clé, mot de passe, adresse perso ou donnée privée** dans le code, les docs, les tickets ou les captures.
  Les secrets restent dans `%USERPROFILE%\.openjarvis\` (chiffrés par Windows).
- **Services gratuits d'abord** : une nouvelle dépendance payante doit rester facultative.
- **Actions sensibles** (mail, suppression, extinction, achat…) : toujours une confirmation.
- Les pull requests écrites avec l'aide d'une IA sont acceptées **si tu les as comprises et testées** et que tu le
  précises dans la description. Les changements générés en masse sans test seront fermés.
- Sois aimable : on est tous là pour apprendre.

## Style

- Python 3.13, noms et commentaires en français comme le reste du code.
- Garde les changements petits et lisibles ; ne reformate pas des fichiers entiers.
