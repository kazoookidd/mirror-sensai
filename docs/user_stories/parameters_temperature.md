# User Stories : Température du modèle

## Réglage de la température

**US-TE-01** En tant qu'administrateur ou développeur, je veux définir la température de l'assistant au démarrage, afin d'adapter son style de réponse à l'usage (réponses précises et stables en contexte RH, plus créatives en démo ou en brainstorming).

Critères d'acceptation :

* `TEMPERATURE` dans le fichier `.env` fixe la température de départ
* L'option `--temperature` en ligne de commande remplace la valeur du fichier de configuration
* La valeur doit être comprise entre 0 (déterministe) et 2 (très créatif)
* La température choisie s'affiche dans la ligne de démarrage

**US-TE-02** En tant qu'utilisateur, je veux changer la température pendant la conversation avec `/temperature`, afin d'ajuster le ton des réponses sans relancer l'application ni perdre mon historique.

Critères d'acceptation :

* `/temperature <valeur>` applique la nouvelle valeur aux réponses suivantes
* L'historique de la conversation est conservé
* `/temperature` sans argument affiche la valeur courante, la plage acceptée et une explication courte (bas = précis et répétable, haut = créatif)
* `/help` mentionne la commande

**US-TE-03** En tant qu'utilisateur qui ne touche à rien, je veux que l'assistant garde le comportement par défaut du modèle, afin de ne pas être impacté par un réglage que je n'ai pas demandé.

Critères d'acceptation :

* Sans `TEMPERATURE` ni `--temperature`, aucune température n'est envoyée à Ollama : le modèle utilise sa valeur par défaut (souvent 0,8) et l'affichage indique `model default`
* `/temperature default` (ou `auto`, `none`, `reset`) revient à ce comportement
* Une température de `0` est bien envoyée au modèle et n'est pas confondue avec « non définie »

## Robustesse de la saisie

**US-TE-04** En tant qu'utilisateur, je veux être averti clairement quand ma valeur est invalide, afin de ne jamais obtenir une température différente de celle que j'ai demandée.

Critères d'acceptation :

* Une valeur non numérique ou hors de la plage 0 à 2 (y compris `nan` et `inf`) est refusée avec un message explicite
* La valeur n'est jamais corrigée automatiquement (pas d'arrondi ni de plafonnement)
* Avec `/temperature`, la température précédente reste active et le message la rappelle
* Au démarrage, une valeur invalide affiche un avertissement et l'assistant utilise la valeur par défaut du modèle

**US-TE-05** En tant qu'utilisateur francophone, je veux pouvoir saisir une température avec une virgule décimale, afin de ne pas être bloqué par le format.

Critères d'acceptation :

* `0,7` et `0.7` sont équivalents
* Les espaces autour de la valeur sont ignorés

## Cohérence avec les autres fonctions

**US-TE-07** En tant qu'utilisateur, je veux que le changement de persona ou de modèle conserve ma température, afin de ne pas devoir la redéfinir à chaque changement.

Critères d'acceptation :

* `/persona` et `/model` ne modifient pas la température de la session
* La température active est envoyée avec chaque tour de conversation
