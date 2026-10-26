# User Stories : Personas et changement de modèle

## [A5] Persona

**US-A5-01** En tant que collaborateur RH, je veux choisir parmi plusieurs personas métier (onboarding, RH senior, recrutement), afin que l'assistant adopte le ton, le rôle et les règles adaptés à ma tâche du moment.

Critères d'acceptation :

* `/personas` liste les personas disponibles avec leur nom et leur description
* `/persona <id|numéro|nom>` active le persona choisi et confirme le changement
* Le prompt système envoyé au modèle au tour suivant est celui du persona actif
* Un persona inconnu est refusé avec un message d'erreur, le persona actif reste inchangé

**US-A5-02** En tant que nouvel employé, je veux pouvoir changer de persona en cours de conversation (par exemple passer d'« Onboarding Buddy » à un autre profil), afin de ne pas perdre le fil de ce que j'ai déjà expliqué.

Critères d'acceptation :

* Changer de persona ne vide ni ne modifie l'historique de la conversation
* Le tour suivant reçoit tout l'historique précédent avec le nouveau prompt système
* Le persona actif est affiché au démarrage et lors de chaque changement

**US-A5-03** En tant que responsable RH ou développeur, je veux ajouter ou modifier un persona en déposant un fichier JSON dans le dossier `personas/`, afin de spécialiser l'assistant sans modifier le code.

Critères d'acceptation :

* Un fichier `personas/<id>.json` avec `name` et `system_prompt` est détecté au prochain lancement
* Un fichier invalide (JSON cassé, champ manquant) est ignoré avec un avertissement, sans empêcher le démarrage
* Un persona `default` existe toujours, construit à partir de `system_prompt.txt`
* Le persona de démarrage se règle par `--persona` ou `DEFAULT_PERSONA` dans le fichier de configuration

---

## Changement de modèle à chaud

**US-MD-01** En tant qu'utilisateur, je veux lister les modèles installés dans Ollama depuis le chatbot, afin de savoir lesquels je peux utiliser sans quitter l'application.

Critères d'acceptation :

* `/models` affiche les modèles installés, numérotés, avec le modèle actif marqué
* Le modèle configuré sans tag (ex. `llama3`) est reconnu comme actif même si Ollama le liste en `llama3:latest`
* Les modèles d'embedding sont signalés comme inutilisables pour le chat
* Si Ollama est injoignable, un message d'erreur clair s'affiche et la session continue

**US-MD-02** En tant qu'utilisateur, je veux changer de modèle en plein runtime, afin d'arbitrer entre vitesse et qualité de réponse (petit modèle pour itérer, gros modèle pour une question difficile) sans perdre ma conversation.

Critères d'acceptation :

* `/model <nom|numéro>` bascule le modèle utilisé pour les tours suivants
* L'historique de la conversation est conservé et renvoyé au nouveau modèle
* Le nom sans tag est accepté (`/model llama3` → `llama3:latest`)
* Le choix du modèle est indépendant du persona actif (changer l'un ne réinitialise pas l'autre)

**US-MD-03** En tant qu'utilisateur, je veux être prévenu clairement quand je choisis un modèle qui n'est pas installé, afin de savoir comment le récupérer plutôt que de tomber sur une erreur au message suivant.

Critères d'acceptation :

* Un modèle absent est refusé avec la commande `ollama pull <nom>` suggérée
* La liste des modèles installés est réaffichée pour aider au choix
* Le modèle actif reste inchangé après un choix invalide ou une erreur de connexion

---

## Commandes en session

**US-CMD-01** En tant qu'utilisateur, je veux une commande d'aide qui liste toutes les commandes disponibles, afin de découvrir les fonctionnalités sans lire la documentation.

Critères d'acceptation :

* `/help` liste `/new`, `/conversations`, `/personas`, `/persona`, `/models`, `/model`
* Une commande inconnue affiche un message renvoyant vers `/help` et n'est pas envoyée au modèle
