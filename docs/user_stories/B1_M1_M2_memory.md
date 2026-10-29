# User Stories

## [B1] Functional CLI chatbot

**US-B1-01**
En tant qu'utilisateur, je veux voir la réponse de l'assistant s'afficher
progressivement au fur et à mesure qu'elle est générée, afin de ne pas
attendre dans le vide face à un écran figé.

Critères d'acceptation :

- Le texte apparaît mot par mot / chunk par chunk, pas d'un seul bloc
- Aucun délai perceptible entre la génération du modèle et l'affichage

**US-B1-02**
En tant qu'utilisateur, je veux que l'application me signale clairement
quand Ollama n'est pas disponible, afin de savoir immédiatement quoi
corriger plutôt que de me retrouver face à une erreur technique brute.

Critères d'acceptation :

- Message d'erreur explicite en cas d'échec de connexion
- Le programme ne plante pas, la session continue

---

## [M1] Session Persistence & Profiles

**US-M1-01**
En tant que collaborateur, je veux pouvoir fermer puis rouvrir
l'application sans perdre mon historique de conversation, afin de ne
pas avoir à tout réexpliquer à chaque connexion.

Critères d'acceptation :

- L'historique complet est sauvegardé en base à chaque message
- À la reconnexion, les messages précédents sont rechargés automatiquement

**US-M1-02**
En tant qu'utilisateur, je veux que mon compte soit protégé par un mot
de passe, afin que personne d'autre ne puisse accéder à mon historique
de conversations.

Critères d'acceptation :

- Le mot de passe est haché et salé avant stockage (jamais en clair)
- Une tentative de connexion avec le mauvais mot de passe est rejetée
- La saisie du mot de passe est masquée à l'écran

**US-M1-03**
En tant que nouvel utilisateur, je veux pouvoir créer mon compte
directement depuis l'invite de connexion la première fois que je me
connecte, afin de ne pas avoir besoin d'une étape d'inscription séparée.

Critères d'acceptation :

- Si l'identifiant saisi n'existe pas, l'application propose de créer un compte
- La création demande un email et une confirmation de mot de passe
- Les mots de passe non concordants bloquent la création du compte

**US-M1-04**
En tant que salariée, je veux décrire une fois qui je suis (poste, service,
langue et ton préférés, consignes personnelles), afin que l'assistant en
tienne compte à chaque réponse sans que je le répète.

Critères d'acceptation :

- Le profil est enregistré en base pour mon compte (table `profiles`) et retrouvé à chaque connexion, en CLI comme sur le web
- À chaque tour, il est ajouté au message système après le prompt du persona (`[profile]` puis `[instructions]`) ; un profil vide n'ajoute rien
- Changer de persona ou de modèle garde le profil ; une modification s'applique dès la réponse suivante, sans redémarrer
- Un autre compte ne voit jamais mon profil
- Le cache sémantique ne ressert pas une réponse obtenue avec un autre profil (le profil fait partie de son empreinte)

**US-M1-05**
En tant qu'utilisateur de la CLI, je veux consulter et modifier mon profil
avec une commande, afin de ne pas avoir à ouvrir l'interface web.

Critères d'acceptation :

- `/profile` affiche chaque champ (ou « (not set) »), la taille estimée du texte ajouté et la façon de le modifier
- `/profile <champ> <valeur>` enregistre un champ et garde les autres ; les noms français sont acceptés (`poste`, `service`, `langue`, `ton`)
- `/profile <champ> clear` vide un champ, `/profile clear` vide tout le profil
- Une valeur refusée (ton autre que `concise`/`detailed`, texte trop long) ou un champ inconnu affiche un message clair, et rien ne change
- Au démarrage, une ligne indique si un profil est utilisé ou comment en créer un

**US-M1-06**
En tant que salariée qui utilise le web, je veux remplir mon profil dans un
formulaire et voir exactement ce qui sera transmis au modèle, afin de garder
la main sur ce que l'assistant sait de moi.

Critères d'acceptation :

- La page Profile (et l'onglet Profile du menu du compte) affiche le profil enregistré ; « Save » n'est actif que si quelque chose a changé
- L'aperçu « Injected context » montre le texte exact envoyé au modèle et sa taille estimée
- Un enregistrement réussi affiche « Saved » et le profil tel que le serveur l'a gardé ; un refus affiche la raison et garde la saisie
- Les mêmes contrôles que la CLI s'appliquent (une seule fonction côté serveur)
- Le nom du profil est retiré des recherches web, comme l'identifiant du compte (voir T3)

**US-M1-07**
En tant que nouvel employé, je veux créer mon compte moi-même depuis la page de
connexion du web, afin d'utiliser l'assistant sans attendre que le service RH
me crée un accès.

Critères d'acceptation :

- « Create an employee account » sur la page de connexion ouvre un formulaire : identifiant, e-mail, mot de passe et confirmation
- Le compte créé est toujours un compte Employé, même si le client envoie un autre rôle ; je suis connecté aussitôt
- L'identifiant fait 3 à 40 caractères (lettres, chiffres, `.`, `_`, `-`, sans `@`), l'e-mail est valide, le mot de passe fait au moins 8 caractères ; les deux mots de passe doivent être identiques
- Un identifiant ou un e-mail déjà utilisé est refusé avec un message clair, et rien n'est créé
- Je peux ensuite me connecter avec mon identifiant ou mon e-mail, sur le web comme dans la CLI

**US-M1-08**
En tant que responsable RH, je veux que chaque compte ait un rôle (RH ou
Employé) fixé à sa création, afin de pouvoir ensuite donner des droits
différents aux RH et aux salariés.

Critères d'acceptation :

- Un compte créé dans la CLI est un compte RH ; un compte créé sur le web est un compte Employé
- Les comptes qui existaient avant l'ajout des rôles (tous créés dans la CLI) deviennent des comptes RH, sans perte de données
- Le rôle est affiché en lecture seule dans le profil (`/profile` et page Profile) ; ni `/profile` ni le formulaire web ne peuvent le modifier
- Le serveur connaît le rôle de chaque session (`/api/me`), base des futurs droits

**US-M1-09**
En tant que responsable RH, je veux voir toutes les demandes de congés des
salariés au même endroit, afin de ne plus chercher les demandes dans mes mails.

Critères d'acceptation :

- Une page « Leave requests » liste les demandes de tous les salariés : identifiant et e-mail, type en clair, période, motif, date de dépôt, statut (en attente, annulée)
- Recherche par salarié, e-mail ou motif, et filtres par type et par statut ; un tableau sur ordinateur, des cartes sur téléphone
- Dans la CLI, `/leaves all` affiche la même liste
- La page n'apparaît dans la navigation que pour un compte RH ; un compte employé reçoit un refus (403 sur le web, message dans la CLI) même s'il appelle la route lui-même
- Le RH approuve ou refuse chaque demande (voir US-M1-10)

**US-M1-10**
En tant que responsable RH, je veux approuver ou refuser une demande de congé
depuis la liste, afin de traiter les demandes sans quitter Sensai.

Critères d'acceptation :

- Dans la page « Leave requests », le statut de chaque demande est un menu : Pending, Approved, Refused ; le choix est enregistré aussitôt, avec qui a décidé et quand (« by marc » sous le statut)
- Revenir à « Pending » annule une décision prise par erreur
- Une demande annulée par le salarié est définitive : un simple badge, et le serveur refuse d'en décider (409)
- Dans la CLI, `/leaves approve 3`, `/leaves refuse 3` et `/leaves pending 3` font la même chose
- Seul un compte RH peut décider : un compte employé est refusé (403 sur le web, message dans la CLI), même en appelant la route lui-même
- Le salarié voit la décision dans `/leaves` ; l'agent ne peut plus annuler une demande déjà approuvée ou refusée

---

## [M2] Token Budgeting & Semantic Compression

**US-M2-01**
En tant qu'utilisateur ayant une conversation très longue, je veux que
le contexte envoyé au modèle reste borné en taille, afin de ne pas
dépasser la fenêtre de contexte ou subir des réponses de plus en plus
lentes.

Critères d'acceptation :

- Au-delà d'un seuil configurable de tokens estimés, une compression
  se déclenche automatiquement
- Les derniers messages (fenêtre glissante) restent toujours intacts,
  non résumés
- La conversation continue sans interruption visible pour l'utilisateur

**US-M2-02**
En tant que membre de l'équipe projet, je veux que les faits importants
mentionnés tôt dans une conversation restent accessibles même après
compression, afin que l'assistant ne perde pas d'informations critiques
au fil du temps.

Critères d'acceptation :

- Un script de test dédié vérifie le taux de rétention de faits connus
  après compression forcée
- Le taux de rétention est mesuré et affiché (ex: 4/4 faits retrouvés)

**US-M2-03**
En tant que développeur de l'équipe, je veux pouvoir mesurer l'efficacité
de la compression (ratio, tokens économisés, temps passé), afin de
pouvoir démontrer objectivement ce compromis en soutenance.

Critères d'acceptation :

- Chaque événement de compression est loggé (tokens avant/après, ratio,
  nombre de messages compressés, durée)
- Des statistiques agrégées sont consultables par conversation

**US-M2-04**
En tant qu'utilisateur, je veux que l'application continue de fonctionner
même si la compression échoue (ex: Ollama indisponible pendant le
résumé), afin de ne jamais perdre ma conversation à cause d'un problème
technique secondaire.

Critères d'acceptation :

- En cas d'échec de l'appel de résumé, l'application bascule sur les
  derniers messages bruts sans planter
- Aucune donnée n'est perdue en base de données dans ce cas

---

## [M1 - extension] Multi-conversations par utilisateur

**US-MC-01**
En tant qu'utilisateur, je veux pouvoir avoir plusieurs conversations
distinctes et indépendantes, afin de séparer des sujets différents
(ex: une conversation sur l'onboarding, une autre sur un projet
spécifique) sans qu'ils se mélangent dans le contexte envoyé au modèle.

Critères d'acceptation :

- Chaque conversation a son propre historique, isolé des autres
- Les messages d'une conversation n'apparaissent jamais dans le contexte
  d'une autre conversation du même utilisateur
- Chaque conversation a son propre état de compression (résumé indépendant)

**US-MC-02**
En tant qu'utilisateur, je veux voir la liste de mes conversations
existantes au lancement de l'application, triées par activité récente,
afin de retrouver facilement celle que je veux reprendre.

Critères d'acceptation :

- La liste affiche le titre et la date de dernière mise à jour de
  chaque conversation
- La conversation la plus récemment utilisée apparaît en premier
- L'utilisateur peut choisir une conversation existante ou en créer une
  nouvelle depuis cet écran

**US-MC-03**
En tant qu'utilisateur, je veux pouvoir démarrer une nouvelle conversation
ou changer de conversation sans avoir à redémarrer l'application, afin de
fluidifier mon usage au quotidien.

Critères d'acceptation :

- La commande `/new` crée une nouvelle conversation et y bascule immédiatement
- La commande `/conversations` affiche la liste et permet de changer de
  conversation active, en conservant la session ouverte
