# User Stories - A3 Human in the Loop

## [A3] Human in the Loop

Avant une action critique ou irréversible, l'agent s'interrompt, présente son
plan à l'utilisateur et ne poursuit qu'après une confirmation explicite.
Dans Sensai, l'action critique est l'enregistrement d'une demande de congés,
préparée par l'agent dans le chat.

**US-A3-01**
En tant que collaborateur, je veux que l'assistant me présente ce qu'il
s'apprête à faire avant d'enregistrer ma demande de congés, afin de ne pas
déposer par erreur des dates ou un type de congé que je n'ai pas voulus.

Critères d'acceptation :

- Quand je dis « je pose du 3 au 7 novembre » dans le chat, l'agent appelle
  l'outil `file_leave_request`, prépare la demande mais ne l'enregistre pas :
  il s'interrompt et affiche son plan (pour qui, type de congé, date de début,
  date de fin, motif)
- Le message indique clairement comment continuer (`/confirm` pour exécuter,
  `/cancel` pour abandonner) et précise que rien n'a encore été fait
- L'agent ne dit pas que la demande est déposée tant que je n'ai pas confirmé
- Le comportement est identique en ligne de commande et dans l'interface web

**US-A3-02**
En tant que collaborateur, je veux confirmer explicitement avant que l'action
soit exécutée, afin de garder la main sur ce qui est écrit à mon nom.

Critères d'acceptation :

- `/confirm` exécute l'action en attente et affiche le résultat (numéro de
  la demande enregistrée)
- Ce qui est enregistré est exactement ce qui a été affiché : le modèle n'est
  pas rappelé et rien n'est renvoyé par le client
- Un double `/confirm` n'exécute l'action qu'une seule fois
- En cas d'erreur d'exécution (base de données), l'action reste en attente :
  je peux réessayer avec `/confirm` sans reformuler ma demande

**US-A3-03**
En tant que collaborateur, je veux pouvoir abandonner ou corriger une demande
que l'assistant a mal comprise, afin de ne pas avoir à supprimer ensuite une
demande erronée.

Critères d'acceptation :

- `/cancel` abandonne l'action en attente : rien n'est enregistré
- Une nouvelle demande dans le chat remplace l'action en attente, et le
  nouveau plan est présenté
- Si l'outil ne peut pas préparer l'action (type de congé inconnu, dates
  invalides), l'erreur revient au modèle, rien n'est mis en attente, et une
  action déjà en attente reste intacte
- `/confirm` ou `/cancel` sans action en attente affichent un message
  explicite et ne font rien

**US-A3-04**
En tant que service RH, je veux qu'aucune demande ne soit écrite en base sans
l'accord explicite de la personne concernée, afin que la base ne contienne
que des demandes assumées par leurs auteurs.

Critères d'acceptation :

- Un outil de l'agent déclaré `critical` dans `tools.json` ne s'exécute jamais
  directement : il prépare l'action, et seul `/confirm` l'exécute
- Les champs de la demande viennent des arguments de l'outil (boucle ReAct),
  pas d'une extraction JSON séparée
- Si un outil critique est appelé directement (sans passer par la
  confirmation), l'appel est refusé ; un outil critique qui ne renvoie pas
  une action à confirmer est traité comme une erreur (échec « fermé »)
- Une fois une action en attente, l'agent n'enchaîne aucun autre appel d'outil
  ni appel au modèle dans le même tour
- Une action en attente appartient à la session de son utilisateur : un autre
  utilisateur ne peut ni la confirmer ni la voir
- Les réponses qui présentent un plan ne sont jamais conservées par le cache
  sémantique

**US-A3-05** En tant que salarié qui utilise l'interface web, je veux confirmer ou annuler une demande de congé d'un clic, afin de ne pas avoir à connaître les commandes `/confirm` et `/cancel`.

Critères d'acceptation :

- Quand l'agent prépare une demande, le chat affiche une carte « Leave request to confirm » avec le plan (type, dates, motif) et les boutons « Confirm » et « Cancel »
- « Confirm » enregistre la demande (« Leave request #… saved ») et la carte disparaît ; « Cancel » l'abandonne sans rien enregistrer
- Taper `/confirm` ou `/cancel` dans le composer a le même effet et fait aussi disparaître la carte
- Après un rechargement de la page, la carte d'une demande encore en attente est toujours là

**US-A3-06** En tant que collaborateur, je veux annuler une demande de congé en le disant dans le chat, afin de corriger une erreur sans passer par le service RH.

Critères d'acceptation :

- « Annule mon congé du 3 novembre » : l'agent appelle l'outil critique `cancel_leave_request` avec le premier jour du congé, et rien n'est annulé avant `/confirm`
- La demande est cherchée uniquement parmi mes demandes en attente : l'utilisateur vient de la session, jamais des arguments du modèle ; la demande d'un collègue n'est jamais trouvée
- Le plan affiche la demande trouvée (numéro, type, dates, motif) ; `/confirm` la passe au statut « cancelled », elle n'est jamais effacée
- Aucune demande ce jour-là, ou une date invalide : l'erreur revient au modèle, qui me demande de préciser ; un double `/confirm` ne change rien
- Une question (« Comment annuler un congé ? ») n'est pas prise pour une demande d'annulation

**US-A3-07** En tant que collaborateur, je veux que le type de congé préparé corresponde à ce que j'ai dit, afin de ne pas confirmer un « arrêt maladie » pour un deuil.

Critères d'acceptation :

- Le type est une liste fermée (`enum`) dans la définition de l'outil, chaque type avec quelques mots d'explication (`bereavement = décès d'un proche, deuil`)
- « Raison : deuil de proche » ou « décès de mon grand-père » donne `bereavement`
- Un type hors de la liste est refusé par l'outil et l'erreur revient au modèle
