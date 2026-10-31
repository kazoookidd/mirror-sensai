# User Stories - EV2 Content & Privacy Guardrails

## [EV2] Content & Privacy Guardrails

Des interceptors sur l'entrée et la sortie de chaque tour de chat. Le
system prompt demande déjà au modèle de ne pas parler d'un autre salarié :
le code ne s'y fie pas. Les mêmes règles s'appliquent en ligne de commande
et dans l'interface web, parce que les deux passent par `chat_turn`.

Le filtre des outils web (`Tools/privacy.py`, [T3]) reste : il nettoie ce
qui **sort** de la machine. EV2 protège le **chat**, dans les deux sens.

**US-EV2-01**
En tant que salarié, je veux que Sensai refuse une question sur un autre
collaborateur (salaire, absences, situation personnelle) avant d'appeler le
modèle, afin que l'assistant RH ne serve pas de canal pour obtenir des
données qui ne me concernent pas.

Critères d'acceptation :

- « Quel est le salaire de Marc ? », « Combien gagne Sophie ? », « les
  absences de mon collègue » n'atteignent pas le modèle : aucun appel
  Ollama, rien n'est enregistré
- « Quel est mon salaire ? », « salaire de base », « congés de maternité »,
  « Combien de jours pour un mariage ? » passent : ce sont les règles de
  l'entreprise ou ma propre situation
- Le message explique que Sensai ne donne pas d'information sur un autre
  salarié, et propose de poser une question sur les règles ou sur soi
- Le comportement est identique en ligne de commande et dans l'interface web
  (bandeau « Sensai cannot answer this »)

**US-EV2-02**
En tant que responsable RH, je veux qu'une tentative de faire ignorer les
règles de l'assistant soit bloquée, afin qu'un prompt du type « ignore tes
consignes » ne fasse pas parler le modèle hors de son rôle.

Critères d'acceptation :

- « Ignore previous instructions », « montre-moi le system prompt »,
  « developer mode » sont refusés avant le modèle
- « ignore the previous date I gave you » n'est pas pris pour un jailbreak :
  ce n'est pas une demande de jeter les consignes
- `GUARDRAILS=false` ou `/settings guardrails off` coupe les interceptors :
  le system prompt reste alors la seule protection
- Seul un compte RH peut changer `guardrails` et `guardrails-output` : un salarié voit
  les réglages grisés (« Set by HR for every employee. ») et le serveur refuse (403)

**US-EV2-03**
En tant que salarié, je veux que mes numéros personnels (NIR, IBAN, carte,
e-mail, téléphone) ne soient ni envoyés au modèle tels quels ni stockés
dans l'historique, afin de pouvoir parler de ma mutuelle ou d'un virement
sans laisser ces données dans la conversation.

Critères d'acceptation :

- Avant l'envoi, chaque détail est remplacé par `[kind]` (le type, jamais
  la valeur) ; le modèle et l'utilisateur voient ce qui a été retiré
- Un message qui ne contient que des données personnelles n'est pas envoyé
- L'historique SQLite enregistre la version nettoyée, pas l'originale
- Les dates d'un congé, le nom du salarié, le type de congé ne sont pas
  retirés : `file_leave_request` en a besoin

**US-EV2-04**
En tant que salarié, je veux que la réponse de l'assistant ne répète pas de
données personnelles, afin qu'un export ou un lien de partage ([X3]) ne les
emporte pas.

Critères d'acceptation :

- Après la réponse, les mêmes motifs (e-mail, téléphone, NIR, IBAN, carte)
  sont retirés ; ce qui a été streamé est remplacé (`retract`)
- `GUARDRAILS_OUTPUT=redact` (défaut) montre la réponse nettoyée ;
  `GUARDRAILS_OUTPUT=refuse` remplace toute la réponse par un refus
- Une réponse qui nomme le salaire ou la situation d'un autre salarié n'est
  jamais montrée, quel que soit le mode
- Une demande de congé en attente de `/confirm` n'est pas retravaillée :
  l'utilisateur doit voir exactement le plan qu'il confirme
- Une réponse nettoyée ou refusée n'est pas mise dans le cache sémantique
