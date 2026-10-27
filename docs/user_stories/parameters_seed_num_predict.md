# User Stories : Options du modèle (seed et longueur de réponse)

## Seed : des réponses reproductibles

**US-SD-01** En tant que développeur ou animateur de démonstration, je veux fixer une graine (`seed`) pour que l'assistant redonne la même réponse à la même question, afin de présenter des démos sans mauvaise surprise et de comparer deux réglages sans que le hasard fausse la comparaison.

Critères d'acceptation :

* `/settings seed <nombre>` fixe la graine et confirme le changement (« seed set to 42 »)
* La graine est transmise à Ollama avec chaque réponse de la conversation, y compris les tours où le modèle utilise ses outils (recherche web...)
* La graine est un nombre entier de 0 à 2 147 483 647 ; `0` est une vraie valeur, pas un « non défini »
* La reproductibilité suppose les mêmes conditions : même modèle, même température, même conversation avant. L'aide du réglage le précise (`/settings seed`)

**US-SD-02** En tant qu'administrateur ou développeur, je veux définir la graine au démarrage, afin que l'assistant soit reproductible dès le lancement sans taper de commande.

Critères d'acceptation :

* `SEED` dans le fichier `.env` fixe la graine de départ
* L'option `--seed` en ligne de commande remplace la valeur du fichier de configuration
* Une valeur invalide affiche un avertissement et l'assistant démarre sans graine fixée (comportement par défaut du modèle)

**US-SD-03** En tant qu'utilisateur, je veux retirer la graine fixée, afin de retrouver des réponses naturellement variées.

Critères d'acceptation :

* `/settings seed default` (ou `auto`, `none`, `reset`) retire la graine
* Sans graine, rien n'est envoyé à Ollama pour ce réglage : le modèle utilise son propre comportement
* Sans réglage, l'assistant démarre sans graine fixée

---

## Num-predict : limiter la longueur des réponses

**US-NP-01** En tant qu'utilisateur, je veux limiter la longueur maximale des réponses de l'assistant, afin d'éviter les réponses interminables quand je veux quelque chose de court et de réduire le temps de génération.

Critères d'acceptation :

* `/settings num-predict <nombre>` fixe le nombre maximum de tokens d'une réponse et confirme le changement
* La valeur est un nombre entier de 1 à 32 768
* La limite est transmise à Ollama avec chaque réponse, y compris les tours où le modèle utilise ses outils
* L'aide du réglage (`/settings num-predict`) prévient qu'une valeur trop basse coupe la réponse en plein milieu d'une phrase
* Les alias `max-tokens` et `max-length` sont acceptés

**US-NP-02** En tant qu'administrateur ou développeur, je veux définir la longueur maximale au démarrage, afin d'adapter l'assistant à l'usage (réponses courtes en démo, longues pour des explications de règlement).

Critères d'acceptation :

* `NUM_PREDICT` dans le fichier `.env` fixe la limite de départ
* L'option `--num-predict` en ligne de commande remplace la valeur du fichier de configuration
* Une valeur invalide affiche un avertissement et l'assistant démarre avec la valeur par défaut du modèle

**US-NP-03** En tant qu'utilisateur, je veux retirer la limite de longueur, afin de laisser le modèle décider de la taille de ses réponses.

Critères d'acceptation :

* `/settings num-predict default` (ou `auto`, `none`, `reset`) retire la limite
* Sans limite, rien n'est envoyé à Ollama pour ce réglage
* Sans réglage, l'assistant démarre avec le comportement par défaut du modèle

---

## Commun aux deux réglages

**US-OP-01** En tant qu'utilisateur, je veux voir la valeur courante de chaque réglage et ce qu'il accepte, afin de savoir ce qui est actif sans consulter la configuration.

Critères d'acceptation :

* `/settings` liste tous les réglages avec leur valeur courante ; un réglage non défini s'affiche `model default`
* `/settings seed` et `/settings num-predict` (sans valeur) affichent la valeur courante, une courte explication et les valeurs acceptées
* Les noms sont acceptés sans tenir compte de la casse ni des `_` (`NUM_PREDICT` équivaut à `num-predict`)
* `/help` mentionne la commande `/settings` avec des exemples

**US-OP-02** En tant qu'utilisateur, je veux être averti clairement quand ma valeur est invalide, afin de ne jamais obtenir un réglage différent de celui que j'ai demandé.

Critères d'acceptation :

* Une valeur non numérique, négative, à virgule (`2.5`) ou hors des limites est refusée avec un message explicite
* La valeur n'est jamais corrigée automatiquement (pas d'arrondi ni de plafonnement)
* Le réglage précédent reste actif et le message le rappelle (« unchanged »)
* Le message rappelle les valeurs acceptées

**US-OP-04** En tant qu'utilisateur, je veux que le changement d'un réglage conserve ma conversation, afin de ne pas devoir recommencer.

Critères d'acceptation :

* `/settings` ne modifie ni l'historique, ni le modèle, ni le persona de la session
* Le changement s'applique dès la réponse suivante
* Changer de persona ou de modèle (`/persona`, `/model`) conserve les réglages `seed` et `num-predict`
