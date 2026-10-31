# Scénario sensAI

**Sensai est l'assistant RH interne d'une entreprise : un salarié lui pose ses
questions sur ses droits (congés, télétravail, augmentations) et lui dicte ses
démarches avec ses propres mots, sans attendre le service RH.**

## Le besoin

Dans une entreprise de services numériques de Nantes, les salariés sont
souvent en mission chez des clients. Le service RH, très petit, répond sans
cesse aux mêmes questions : « Combien de jours pour mon mariage ? », « Puis-je
télétravailler ? », « Que dit l'accord sur les augmentations ? ».

Les réponses existent déjà dans des documents officiels, mais personne ne les
lit. Résultat : les salariés attendent, et les RH perdent du temps.

## Les utilisateurs

- **Sophie, 29 ans, consultante en mission** : elle veut une réponse fiable
  sans appeler les RH.
- **Marc, 41 ans, seul responsable RH pour 120 salariés** : il veut moins de
  questions répétitives et des demandes de congés déjà claires.

Marc a un compte **RH**, créé dans le terminal. Sophie a créé elle-même son
compte **Employé** depuis la page de connexion du web. Le rôle est fixé à la
création du compte et affiché dans le profil : c'est la base des droits que
Marc aura plus tard (voir les demandes de tout le monde).

## Pourquoi un assistant qui tourne en local

Les questions sont personnelles (mariage, décès, salaire). Le modèle, les
conversations et les documents RH restent donc sur la machine de
l'entreprise : le modèle tourne avec Ollama, tout est stocké dans une base
SQLite locale.

Ce choix a un coût : la réponse prend quelques secondes. Ce n'est pas gênant
ici, car Sophie pose une question ponctuelle et attend déjà bien plus
longtemps une réponse des RH.

### La seule chose qui sort : la recherche web

Pour une information que les documents n'ont pas (un barème mis à jour, une
loi récente), l'agent peut chercher sur le web. C'est la seule donnée qui
quitte la machine, et elle est contrôlée :

- la requête est écrite par le modèle, qui reçoit la consigne de chercher la
  règle générale (« congé mariage durée code du travail »), jamais la
  situation d'une personne ;
- avant l'envoi, le code retire de la requête les e-mails, numéros de
  téléphone, numéros de sécurité sociale, IBAN, numéros de carte, ainsi que
  l'identifiant, l'e-mail et le nom (celui de son profil) de l'utilisateur
  connecté
  (`back/Tools/privacy.py`). Une page dont l'adresse contient l'une de ces
  données n'est pas ouverte ;
- le modèle et l'utilisateur voient ce qui a été retiré, dans le panneau
  « Reasoning » de la réponse ;
- `AGENT_WEB_TOOLS=false` supprime les outils web : plus rien ne sort.

Limite assumée : un autre nom (celui d'un collègue, ou le sien s'il n'est pas
dans son profil) n'est pas détecté dans une requête web. La consigne donnée
au modèle est la seule protection dans ce cas.

### Ce que le chat refuse tout seul

Même sans recherche web, Sensai ne doit pas parler du salaire ou des
absences d'un autre salarié, ni jeter ses règles sur un « ignore tes
consignes ». Ce n'est pas laissé au modèle : le code refuse la question
avant l'appel, et retire de la réponse (et de l'historique) les e-mails,
téléphones, NIR, IBAN et numéros de carte. « Quel est mon salaire ? » et
« salaire de base » passent ; « Quel est le salaire de Marc ? » non.

## L'histoire de Sophie

1. **Elle se connecte** et retrouve sa conversation de la semaine dernière.
   Son profil (consultante en mission, réponses courtes, « cite toujours le
   document ») est déjà là : elle ne le répète pas, l'assistant en tient
   compte à chaque réponse, quel que soit le persona.
2. **Elle pose sa question** : « Je me marie en mars, j'ai droit à combien de
   jours ? » L'assistant répond à partir des documents RH indexés et cite le
   document entre crochets (`[loi_conge_mariage_pacs.md]`), pour qu'elle
   puisse vérifier.
3. **Elle continue la discussion** (congés, télétravail, accord d'entreprise).
   Même après de nombreux échanges, l'assistant se souvient de l'essentiel,
   comme son mariage en mars : les anciens messages sont résumés, les faits
   (dates, chiffres) sont gardés.
4. **Elle fait sa demande** : « Je pose du 3 au 7 novembre pour des
   vacances. » L'agent comprend la phrase, prépare la demande et
   **s'arrête** : il lui montre le type, les dates et le motif. Rien n'est
   enregistré tant qu'elle n'a pas confirmé (bouton Confirm, ou `/confirm`).
5. **La demande est enregistrée** à son nom, avec les dates et le motif
   affichés, et un numéro. Sophie la retrouve avec `/leaves`, et peut
   l'annuler en le disant (« annule mon congé du 3 novembre ») : là aussi,
   l'assistant montre la demande trouvée et attend sa confirmation.
6. **Marc retrouve la demande** dans la page « Leave requests », réservée
   aux comptes RH : le nom et l'e-mail de Sophie, le type, les dates, le
   motif et le statut, sans mail à relire. Il l'**approuve** ou la
   **refuse** d'un clic ; Sophie voit la décision avec `/leaves`.

## Où on en est

- **Faits :** connexion et historique des conversations, mémoire des longues
  discussions, profil de l'utilisateur ajouté à chaque réponse, réponses à
  partir des documents de l'entreprise (avec la source), demandes de congés
  confirmées (ou annulées) par le salarié, vue RH des demandes, recherche web
  protégée, guardrails sur le chat (salaire d'un collègue, données personnelles),
  interface web.
- **Pas encore :** Sophie n'est pas prévenue quand Marc décide : elle doit
  consulter `/leaves`.

Avant la présentation : préparer des captures d'écran de secours, au cas où le
modèle ne répondrait pas bien en direct.
