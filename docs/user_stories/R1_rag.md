# User Stories : RAG (réponses à partir des documents RH)

## [R1] Basic RAG : poser une question sur les documents

**US-RAG-01** En tant que salarié, je veux poser une question sur mes droits (congés, télétravail, jours fériés...) et obtenir une réponse tirée des documents RH de l'entreprise, afin d'avoir une information fiable sans chercher moi-même dans les textes.

Critères d'acceptation :

* La question est comparée aux documents indexés par similarité sémantique (embeddings `nomic-embed-text` via Ollama), pas par mots-clés : « Je me pacse, ai-je des jours de congé ? » retrouve `loi_conge_mariage_pacs.md`
* Au plus `RAG_TOP_K` extraits (3 par défaut) sont ajoutés au contexte du modèle, du plus pertinent au moins pertinent
* Chaque extrait est transmis avec sa source, et sa page pour un PDF (`[syd_accord_nao_2026.pdf, p. 4]`)
* Les extraits servent uniquement pour ce tour : seuls la question et la réponse sont sauvegardées dans l'historique

**US-RAG-02** En tant qu'utilisateur, je veux qu'une question sans rapport avec les documents RH ne fasse pas remonter d'extraits hors sujet, afin que la réponse ne soit pas polluée par des textes qui n'ont rien à voir.

Critères d'acceptation :

* Un extrait n'est retenu que si sa similarité avec la question atteint `RAG_MIN_SCORE` (0.70 par défaut)
* « Quelle est la recette de la pizza ? » n'ajoute aucun extrait au contexte
* Le seuil et le nombre d'extraits se règlent dans `.env` sans toucher au code ; une valeur invalide affiche un avertissement et la valeur par défaut est utilisée

---

## [R1] Basic RAG : alimenter et maintenir la base documentaire

**US-RAG-03** En tant que responsable RH, je veux indexer un dossier de documents (.txt, .md, .pdf) avec une seule commande, afin que l'assistant puisse s'appuyer sur nos textes à jour.

Critères d'acceptation :

* `/ingest` indexe `data/docs` ; `/ingest <dossier>` indexe un autre dossier
* La commande affiche un bilan : documents indexés, morceaux créés, documents inchangés, documents retirés
* Relancer `/ingest` ne recalcule que les fichiers ajoutés ou modifiés ; un fichier supprimé du dossier est retiré de l'index
* Un PDF protégé, scanné ou abîmé, ou un fichier illisible, produit un avertissement sans arrêter l'indexation des autres
* Un dossier inexistant affiche une erreur claire au lieu d'un faux succès
* Réservé aux comptes RH : un compte employé reçoit un message d'erreur et rien n'est indexé

**US-RAG-04** En tant qu'utilisateur, je veux que la recherche dans les documents ne bloque jamais la conversation, afin de toujours obtenir une réponse même quand le RAG ne peut pas aider.

Critères d'acceptation :

* L'interrupteur « HR documents » du champ de saisie (ou `/settings documents off`) répond sans les documents RH, et sans le cache sémantique ; rallumé, la recherche reprend
* Les extraits ajoutés tiennent toujours dans la place restante sous `CONTEXT_TOKEN_BUDGET` : le RAG ne déclenche jamais le blocage de la limite de tokens (il ajoute moins d'extraits, ou aucun)
* Si Ollama ne répond pas pour les embeddings, ou si rien n'est indexé, l'assistant répond sans extraits
* Si l'index a été construit avec un autre modèle d'embedding, un avertissement invite à relancer `/ingest` et l'assistant répond sans extraits

**US-RAG-05** En tant que responsable RH, je veux ajouter un nouvel accord à la base depuis l'interface web, afin que les salariés obtiennent des réponses à jour sans que personne ne passe par le terminal.

Critères d'acceptation :

* Dans Knowledge base (groupe HR de la barre latérale), « Import a document » ou un dépôt sur la zone en pointillés envoie un ou plusieurs fichiers `.txt`, `.md` ou `.pdf` (10 Mo au plus)
* Le fichier est enregistré dans `data/docs` puis indexé comme avec `/ingest` (découpage et embeddings sur la machine) ; il apparaît « Indexed » avec son nombre de morceaux
* Une question posée ensuite dans le chat peut s'appuyer sur ce document ; le cache sémantique est vidé, car ses réponses venaient des anciens documents
* Un nom qui sortirait du dossier, un format non pris en charge, un fichier vide, trop gros ou sans texte lisible (PDF scanné) est refusé avec un message clair, et rien n'est enregistré
* Si Ollama ne répond pas, le fichier est gardé « Not indexed » et le message l'indique
* Le menu « ⋯ » d'un document le renomme (sans recalculer ses embeddings, les réponses citent le nouveau nom) ou le supprime après confirmation (fichier et morceaux retirés, même si Ollama ne répond pas) ; le cache sémantique est vidé
* Un compte employé n'a pas Knowledge base dans sa barre latérale (l'adresse le renvoie vers My files) ; un import envoyé à la main est refusé par le serveur (403)

**US-RAG-06** En tant que salarié, je veux joindre mon contrat ou un courrier à une discussion, afin de poser des questions dessus sans le rendre visible aux autres ni l'ajouter à la base de l'entreprise.

Critères d'acceptation :

* Le trombone du champ de saisie joint un ou plusieurs fichiers `.txt`, `.md` ou `.pdf` (10 Mo au plus) ; ils s'affichent sous forme d'étiquettes au-dessus du champ et restent après un rechargement
* Joint avant le premier message, le fichier ouvre une nouvelle discussion à son nom
* Les réponses de cette discussion s'appuient sur le fichier (« Quel est mon préavis ? », « Résume le fichier joint ») ; une autre discussion, ou un autre compte, n'y a pas accès
* Le fichier n'entre pas dans la base commune ; supprimer la discussion le supprime ; une branche (X2) garde les fichiers de sa discussion
* Un fichier illisible (PDF scanné), un format non pris en charge ou Ollama indisponible affiche un message clair, et rien n'est gardé
* La page My files liste tous mes fichiers joints avec leur discussion (un clic l'ouvre), puis les documents RH en lecture seule
* Depuis My files, je supprime un fichier joint après confirmation : sa discussion ne s'en sert plus ; un autre compte ne peut pas le supprimer (404)
* Après un changement de modèle d'embedding, les fichiers déjà joints sont ré-encodés depuis leur texte à la question suivante : ils restent utilisables
