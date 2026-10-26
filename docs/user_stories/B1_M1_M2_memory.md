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
