# User Stories : Recherche web (T3)

## [T3] Chercher une information à jour sur le web

**US-T3-01**
En tant que salarié, je veux que l'assistant aille chercher sur le web une
information que les documents RH n'ont pas (un barème mis à jour, une loi
récente), afin d'obtenir une réponse à jour avec la source pour la vérifier.

Critères d'acceptation :
- L'agent appelle `search_internet` de lui-même quand la question porte sur une information récente ou à vérifier ; aucune commande n'est nécessaire
- La réponse cite les adresses (URL) des résultats utilisés
- Le moteur (Brave, Tavily, Exa) se choisit avec `SEARCH_ENGINE` dans `.env` ou `/switch_search` à chaud, et le changement s'applique à l'appel suivant
- Une clé d'API manquante ou un moteur injoignable revient au modèle comme une erreur, qui répond sans inventer de source ; la conversation continue

**US-T3-02**
En tant que salarié, je veux que mes données personnelles ne partent jamais
vers un moteur de recherche, afin de pouvoir parler de ma situation (mariage,
santé, salaire) sans qu'elle sorte de l'entreprise.

Critères d'acceptation :
- Avant l'envoi, la requête est débarrassée des e-mails, numéros de téléphone, numéros de sécurité sociale, IBAN, numéros de carte, et de l'identifiant, de l'e-mail et du nom (profil [M1]) du compte connecté
- Une requête qui ne contient que des données personnelles n'est pas envoyée ; une page dont l'adresse en contient n'est pas ouverte
- Le modèle reçoit la liste de ce qui a été retiré (le type, jamais la valeur) et la requête réellement envoyée
- La consigne donnée au modèle lui demande de chercher la règle générale (« congé mariage durée code du travail »), jamais la situation d'une personne

**US-T3-03**
En tant que responsable RH soucieux de la confidentialité, je veux pouvoir
couper complètement l'accès au web, afin de garantir qu'aucune donnée ne
quitte la machine.

Critères d'acceptation :
- `AGENT_WEB_TOOLS=false` dans `.env` retire `search_internet` et `read_webpage` des outils proposés au modèle
- La consigne des outils ne parle alors plus de recherche web
- Les autres outils (demande de congés) fonctionnent toujours
