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

**US-RAG-04** En tant qu'utilisateur, je veux que la recherche dans les documents ne bloque jamais la conversation, afin de toujours obtenir une réponse même quand le RAG ne peut pas aider.

Critères d'acceptation :

* Les extraits ajoutés tiennent toujours dans la place restante sous `CONTEXT_TOKEN_BUDGET` : le RAG ne déclenche jamais le blocage de la limite de tokens (il ajoute moins d'extraits, ou aucun)
* Si Ollama ne répond pas pour les embeddings, ou si rien n'est indexé, l'assistant répond sans extraits
* Si l'index a été construit avec un autre modèle d'embedding, un avertissement invite à relancer `/ingest` et l'assistant répond sans extraits
