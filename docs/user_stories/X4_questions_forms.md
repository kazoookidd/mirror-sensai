# User Stories : Questions et formulaires (X4)

## [X4] Répondre à l'assistant sans tout retaper

**US-X4-01**
En tant que salarié, je veux que « je veux poser un congé » m'ouvre directement un formulaire,
afin de donner le type et les dates en quelques clics au lieu d'un échange de questions en texte.

Critères d'acceptation :
- Une demande de congé sans aucune date (« je veux poser un congé », « je voudrais poser un congé maladie », « je veux poser 2 jours de RTT ») ouvre le formulaire sans appeler le modèle : la réponse est immédiate
- Le type est pré-rempli quand le message le nomme (maladie, deuil, mariage, télétravail, RTT ou vacances, sans solde)
- Une demande avec des dates (« je pose du 3 au 7 novembre ») reste préparée par l'agent et présentée à confirmer (A3)
- Dans le web, le formulaire est une carte dans le chat : un menu pour le type, des sélecteurs de date, un motif facultatif, « File the request » et « Cancel » ; il est toujours là après un rechargement

**US-X4-02**
En tant que salarié, je veux compléter une demande que l'assistant a mal comprise, afin de ne pas
recommencer la conversation.

Critères d'acceptation :
- Quand l'agent appelle `file_leave_request` avec un type inconnu, une date manquante ou une fin avant le début, l'outil renvoie le formulaire pré-rempli avec ce qui est valide, et le problème est indiqué sous le champ concerné
- « File the request » enregistre la demande aussitôt, avec exactement les valeurs affichées : remplir et envoyer le formulaire vaut confirmation (A3)
- Les valeurs sont vérifiées de nouveau par le serveur ; une erreur s'affiche sous le champ et rien n'est enregistré
- Seul le formulaire de ma session et de cette discussion est accepté (404 sinon) ; `/cancel` l'abandonne sans rien enregistrer

**US-X4-03**
En tant que salarié, je veux répondre d'un clic quand l'assistant me pose une question, afin de
continuer sans avoir à formuler ma réponse.

Critères d'acceptation :
- L'outil `ask_user` permet au modèle de poser une question courte, avec 2 à 6 choix ou une réponse libre ; l'agent s'arrête en attendant
- Dans le web, chaque choix est un bouton et un champ permet de répondre autrement ; la réponse part comme mon message suivant
- Dans le terminal, les choix sont numérotés : taper « 2 » choisit le deuxième
- La conversation garde la question et la réponse (« Answer: RTT »), et une réponse n'est jamais servie depuis le cache

**US-X4-04**
En tant qu'utilisateur de la CLI, je veux remplir le formulaire dans le terminal, afin d'avoir la
même aide qu'en web.

Critères d'acceptation :
- Après la réponse qui ouvre un formulaire, les champs sont demandés un par un ; Entrée garde la valeur pré-remplie, les choix sont numérotés
- Une valeur refusée est redemandée avec la raison ; `/cancel` abandonne
- `/form` reprend un formulaire interrompu ; `/confirm` ne remplit jamais un formulaire (il indique quoi faire)

**US-X4-05**
En tant que membre de l'équipe, je veux que le modèle puisse écrire un petit formulaire quand il a
besoin de plusieurs réponses, sans risque s'il le fait mal, afin de pouvoir l'essayer avec un modèle
plus grand.

Critères d'acceptation :
- `ask_form(title, fields)` est désactivé par défaut et activé par `AGENT_ASK_FORM=true`
- La description est vérifiée : 1 à 5 champs, chacun avec un libellé distinct et un type (texte, date, choix de 2 à 6 options) ; sinon l'erreur revient au modèle et rien n'est affiché
- Le formulaire ne fait que recueillir des réponses : elles reviennent au modèle comme mon message suivant, et rien n'est enregistré ni déclenché
- Le banc `back/benchmarks/Bench_forms.py` mesure s'il est utilisé à bon escient ; le résultat ([docs/benchmarks/forms.md](../benchmarks/forms.md)) justifie qu'il reste désactivé
