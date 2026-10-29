# User Stories : interface web (X1)

## [X1] Discuter avec SENSAI depuis un navigateur

**US-X1-01** En tant que salarié qui n'utilise pas de terminal, je veux poser mes questions RH dans une page web et voir la réponse s'écrire au fur et à mesure, afin d'utiliser l'assistant aussi simplement qu'une messagerie.

Critères d'acceptation :

* L'interface s'ouvre sur `http://localhost:3000` avec Docker (`docker compose up --build`), ou sur `http://127.0.0.1:8000` avec `./start.sh --web`
* Je me connecte avec l'adresse e-mail ou l'identifiant de mon compte ; « Log out » me ramène à l'écran de connexion
* Entrée envoie le message, Maj+Entrée ajoute une ligne ; le bouton d'envoi reste désactivé tant que le champ est vide
* La réponse s'affiche mot par mot avec l'indicateur « Generating », puis le bouton de copie apparaît
* Le premier message crée une conversation nommée d'après la question ; elle est sauvegardée comme dans la CLI et je la retrouve dans History et dans la liste « Recent » de la barre latérale

**US-X1-02** En tant que responsable RH, je veux voir en direct la part du contexte utilisée par la conversation, afin de savoir quand il vaut mieux repartir sur une nouvelle conversation.

Critères d'acceptation :

* La jauge sous le champ de saisie affiche les tokens envoyés au modèle sur le budget `CONTEXT_TOKEN_BUDGET` (ex. « 1.1k / 4k »)
* Elle se met à jour à chaque échange
* Au-delà de 85 % elle passe en rouge ; si la limite bloque l'envoi, un bandeau propose « New chat »

---

## [X1] Changer de modèle et de réglages sans redémarrer

**US-X1-03** En tant qu'utilisateur, je veux changer le modèle Ollama et les options de génération depuis l'interface, afin de comparer les réponses sans relancer l'application.

Critères d'acceptation :

* Le menu du modèle liste les modèles installés dans Ollama (les modèles d'embedding sont exclus) et coche le modèle actif
* La température (0 à 2) et la longueur maximale se règlent dans Settings ; une valeur refusée affiche le même message d'erreur que `/settings` dans la CLI
* Le persona (Onboarding Buddy, Recruteur, RH Senior...) se choisit dans la barre latérale ou dans Settings, et `/persona` dans le chat met ce choix à jour
* Les changements s'appliquent à la réponse suivante et l'historique est conservé

**US-X1-04** En tant que salarié, je veux comprendre immédiatement pourquoi SENSAI ne répond pas, afin de corriger le problème sans perdre ma question.

Critères d'acceptation :

* Si Ollama est arrêté, le statut passe à « Ollama offline », un bandeau l'explique et le champ de saisie est désactivé jusqu'à ce que « Retry » retrouve le service
* Si le modèle choisi n'est pas installé, un bandeau donne la commande `ollama pull` et propose « Change model » ; ma question est renvoyée au nouveau modèle sans que je la retape
* Un échange qui échoue n'est pas enregistré dans l'historique

---

## [X1] Utiliser les commandes de la CLI dans le navigateur

**US-X1-05** En tant qu'utilisateur habitué à la CLI, je veux taper `/` dans le champ de saisie pour voir toutes les commandes et ce qu'elles font, afin de les utiliser sans connaître la liste par cœur.

Critères d'acceptation :

* `/` affiche la liste des commandes avec leur description ; la liste se filtre pendant la saisie (`/mo` ne garde que `/models` et `/model`)
* Flèches pour choisir, Entrée pour lancer, Tab pour compléter, Échap pour fermer
* La commande s'exécute avec le même code que la CLI et sa sortie s'affiche dans le fil, sans être enregistrée dans la conversation ni envoyée au modèle
* `/model` change aussi le modèle affiché dans l'interface ; `/new` ouvre une nouvelle conversation et `/conversations` ouvre History ; une commande inconnue affiche le même message que la CLI

---

## [X1] Retrouver ses échanges, sur ordinateur comme sur téléphone

**US-X1-06** En tant que manager, je veux retrouver, renommer ou supprimer mes conversations passées, afin de garder un historique clair de mes démarches RH.

Critères d'acceptation :

* History regroupe les conversations par « Today », « Yesterday », « Earlier this week » et « Older », avec le début de la dernière réponse
* La recherche filtre par titre et par contenu ; le tri peut être inversé
* Sur ordinateur, Rename et Delete apparaissent au survol, et aussi dans le menu « ⋯ » de chaque discussion récente de la barre latérale ; sur téléphone, en glissant la conversation vers la gauche
* Supprimer la discussion affichée (ou l'une de ses branches) ramène à une nouvelle discussion
* Une conversation d'un autre utilisateur n'est jamais accessible (réponse 404)

**US-X1-07** En tant que salarié en déplacement, je veux utiliser SENSAI sur mon téléphone ou ma tablette, en portrait comme en paysage, afin d'avoir la même aide RH partout.

Critères d'acceptation :

* À partir de 1024 px de large, une barre latérale à gauche donne accès à Chat, My files (employé) ou au groupe HR (Knowledge base, Leave requests), History (avec le modèle de la dernière réponse de chaque discussion), aux conversations récentes et au modèle ; un clic sur mon compte ouvre un menu (Profile, Settings, Log out) et Profile ou Settings s'ouvrent dans une fenêtre au-dessus de la page, fermée par Échap, ✕ ou un clic à côté
* Un compte RH porte un badge « HR » à côté de son nom (barre latérale) ou du logo (téléphone, tablette) ; Settings indique « HR account » ou « employee account »
* En dessous, une barre d'application en haut et une barre d'onglets en bas la remplacent ; « Log out » est dans Settings, carte Account
* Passer d'un onglet à l'autre fait glisser la page dans le sens de l'onglet ; sur téléphone, un glissement du doigt change d'onglet
* Aucune page ne défile horizontalement, du téléphone 360 px à l'écran 1440 px
* Le thème clair, sombre ou système est mémorisé sur l'appareil
