# User Stories - T5 Structured Output

## [T5] Structured Output

**US-T5-01**
En tant que collaborateur, je veux écrire ma demande de congés en langage
naturel, afin de ne pas avoir à remplir un formulaire.

Critères d'acceptation :

- Une phrase comme « Je pose du 3 au 7 novembre pour des vacances » produit
  un JSON avec les champs `leave_type`, `start_date`, `end_date` et `reason`
- Les dates sont toujours au format AAAA-MM-JJ
- Le type de congé appartient à une liste fermée (`paid_leave`,
  `sick_leave`, `marriage`, `bereavement`, `remote_work`, `unpaid_leave`,
  `other`)

**US-T5-02**
En tant que collaborateur, je veux pouvoir dire « demain » ou « lundi
prochain », afin de formuler ma demande comme je le ferais à un collègue.

Critères d'acceptation :

- La date du jour est transmise au modèle pour résoudre les dates relatives
- Une demande d'un seul jour donne une `start_date` identique à la `end_date`
- La sortie est reproductible : la génération se fait à température 0

**US-T5-03**
En tant que service RH, je veux que seules des demandes valides soient
enregistrées, afin de pouvoir les filtrer et les compter sans lire du
texte libre.

Critères d'acceptation :

- Une demande valide est enregistrée en base (table `leave_requests`),
  liée à l'utilisateur
- Une réponse du modèle qui n'est pas du JSON, qui ne respecte pas le
  schéma (champ manquant, champ en trop, mauvais type, type de congé
  inconnu) ou qui contient une date impossible (ex : 2026-02-30) n'est
  jamais enregistrée
- Une demande qui se termine avant son début est refusée
- Il est impossible d'enregistrer une demande pour un utilisateur qui
  n'existe pas

**US-T5-04**
En tant qu'utilisateur, je veux que l'assistant se corrige lorsque sa
première réponse est invalide, afin de ne pas avoir à reformuler ma demande.

Critères d'acceptation :

- En cas de réponse invalide, le modèle est relancé avec sa réponse
  précédente et la liste précise de ses erreurs
- Jusqu'à 3 tentatives sont faites au total
- Après 3 échecs, un message d'erreur indique les erreurs restantes et rien
  n'est enregistré

**US-T5-05**
En tant qu'utilisateur, je veux un message clair quand la demande ne peut
pas être traitée, afin de savoir quoi corriger plutôt que de voir une erreur
technique.

Critères d'acceptation :

- Ollama indisponible : message explicite, le programme ne plante pas et
  n'insiste pas inutilement
- Entrée vide : refusée sans appeler le modèle
- Erreur HTTP ou réponse d'Ollama mal formée : message clair
- Le script se termine avec un code d'erreur non nul dans ces cas
