# User Stories — Boucle de raisonnement ReAct (A1)

**US-A1-01**
En tant qu'employé RH, je veux que l'assistant cherche lui-même une information
qu'il ne connaît pas (web), puis me réponde en s'appuyant dessus, afin d'obtenir
une réponse à jour sans devoir faire la recherche moi-même.

Critères d'acceptation :
- Le modèle demande un outil via `message.tool_calls` d'Ollama ; l'agent l'exécute et lui renvoie le résultat jusqu'à ce qu'il réponde sans appel d'outil
- Si aucune recherche n'est nécessaire, il répond directement, sans appeler d'outil
- Si les outils ne donnent rien d'utile, il le dit au lieu d'inventer une source

**US-A1-02**
En tant que développeur, je veux que la boucle soit bornée et robuste face à un
petit modèle local, afin qu'un agent ne tourne jamais indéfiniment ni ne plante.

Critères d'acceptation :
- Nombre d'étapes maximum configurable (`AGENT_MAX_STEPS`), puis réponse forcée (sans outils) avec ce qui a été trouvé
- Un appel identique répété n'est pas ré-exécuté et arrête la boucle
- Un outil inconnu, mal appelé (argument manquant ou du mauvais type) ou en erreur est signalé au modèle, sans exception
- Les résultats d'outils trop longs sont tronqués ; un contexte trop grand force la réponse
- Un modèle sans support des outils donne l'explication d'Ollama au lieu d'un crash

**US-A1-03**
En tant qu'utilisateur, je veux pouvoir suivre ce que fait l'agent (pensées,
outils appelés, résultats), afin de comprendre et vérifier d'où vient la réponse.

Critères d'acceptation :
- Chaque pensée, action et observation est notifiée (affichage discret, optionnel)
- Le résultat indique les outils utilisés et le statut de fin (réponse, max étapes, répétition...)

**US-A1-04**
En tant que développeur, je veux ajouter un outil en le décrivant dans `tools.json`
et en fournissant sa fonction, afin d'étendre l'agent sans toucher à la boucle.

Critères d'acceptation :
- Les outils déclarés sont transmis tels quels au modèle (champ `tools`)
- Un outil déclaré sans fonction fait échouer le démarrage avec un message clair
- Le moteur de recherche choisi avec `/switch_search` est pris en compte immédiatement par l'agent

**US-A1-05**
En tant qu'employé RH non technique, je veux poser mes questions normalement et que
l'assistant décide seul s'il doit chercher sur le web, afin de ne rien avoir à
configurer ni à demander ("utilise la recherche").

Critères d'acceptation :
- Aucune commande n'est nécessaire : les outils font partie de chaque tour de conversation
- Une salutation, un remerciement ou une réponse courte ("ok", "merci") n'appelle aucun outil
- Une question qui n'exige pas d'outil coûte un seul appel au modèle, réponse affichée en streaming
- Quand un outil est utilisé, une ligne discrète l'indique ("Searching the web : ..."), désactivable
- Un modèle qui ne gère pas les outils fonctionne quand même, sans eux, avec une seule note discrète
- Seuls la question et la réponse finale sont enregistrées dans l'historique
