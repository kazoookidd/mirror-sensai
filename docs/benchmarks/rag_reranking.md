# Banc d'essai : reclassement des extraits du RAG (R2)

Le RAG de base (R1) classe les extraits par similarité d'embeddings, puis garde ceux qui passent un
seuil. R2 ajoute un **reclassement** : les 10 extraits les plus proches par le sens sont notés une
deuxième fois, et c'est cette note finale qui passe le seuil. Ce document compare trois façons de
reclasser, mesurées le 31 octobre 2026 sur la même machine que les [autres bancs](embedding_models.md)
(Ryzen 7 8840HS, sans GPU).

**En bref :** le reclassement **hybride** (sens + mots-clés, poids 0,15) est gardé. Il ne coûte rien
(aucun appel au modèle) et il **écarte mieux les near-misses** : la marge entre la moins bonne bonne
réponse et la meilleure question hors sujet passe de 0,084 à 0,110 avec `bge-m3` (+31 %), et de 0,019
à 0,070 avec `nomic-embed-text`. Le reclassement par le LLM est écarté : il est **moins bon** et prend
**12 secondes** par question.

## Les méthodes comparées

- **Embeddings seuls** : le classement de R1, la similarité cosinus (`RAG_KEYWORD_WEIGHT=0`).
- **Hybride** : chaque candidat garde sa similarité, et gagne un score de mots-clés (BM25, écrit à
  la main dans [`back/rag/Keywords.py`](../../back/rag/Keywords.py), sans librairie) : les mots rares
  de la question présents dans l'extrait comptent, les accents, la casse et les mots courants
  (« le », « de », « pour »...) sont ignorés. Score final = `(1 - poids) x sens + poids x mots-clés`,
  le score BM25 étant ramené entre 0 et 1 par `s / (s + 5)`. Plusieurs poids sont mesurés.
- **LLM** : `qwen2.5:3b` reçoit la question et les 10 candidats, et répond les numéros des passages
  utiles du plus utile au moins utile. Mesuré ici seulement, Sensai ne l'utilise pas.

Le script [`back/benchmarks/Bench_rerank.py`](../../back/benchmarks/Bench_rerank.py) utilise le
pipeline du projet (`data/docs` indexé par `rag/Store.py`, 69 morceaux, recherche par
`rag/Retriever.py`) et les **22 questions RH et 6 questions hors sujet** de
[`Bench_embeddings.py`](../../back/benchmarks/Bench_embeddings.py).

Pour reproduire : `python back/benchmarks/Bench_rerank.py bge-m3 nomic-embed-text --chat-model qwen2.5:3b`.

## Les résultats

### bge-m3 (le modèle de Sensai)

| Méthode | Bon document en 1er | Dans les 3 premiers | MRR | Bon passage, score le plus bas | Hors sujet, score le plus haut | Marge | Temps (médiane) |
|---|---|---|---|---|---|---|---|
| Embeddings seuls | 22/22 | 22/22 | 1,00 | 0,538 | 0,454 | 0,084 | 57 ms |
| Hybride 0,1 | 22/22 | 22/22 | 1,00 | 0,557 | 0,453 | 0,105 | 57 ms |
| **Hybride 0,15** | 22/22 | 22/22 | 1,00 | 0,562 | 0,452 | **0,110** | 56 ms |
| Hybride 0,25 | 22/22 | 22/22 | 1,00 | 0,549 | 0,451 | 0,098 | 56 ms |
| Hybride 0,35 | 22/22 | 22/22 | 1,00 | 0,536 | 0,449 | 0,087 | 55 ms |
| LLM (qwen2.5:3b) | 20/22 | 22/22 | 0,95 | - | - | aucune question hors sujet ne garde de passage | 12 534 ms |

### nomic-embed-text (l'ancien modèle)

| Méthode | Bon document en 1er | Dans les 3 premiers | MRR | Bon passage, score le plus bas | Hors sujet, score le plus haut | Marge | Temps (médiane) |
|---|---|---|---|---|---|---|---|
| Embeddings seuls | 19/22 | 22/22 | 0,92 | 0,681 | 0,662 | 0,019 | 34 ms |
| Hybride 0,1 | 20/22 | 22/22 | 0,95 | 0,672 | 0,613 | 0,058 | 33 ms |
| Hybride 0,15 | 20/22 | 22/22 | 0,95 | 0,675 | 0,605 | 0,070 | 32 ms |
| Hybride 0,25 | 20/22 | 22/22 | 0,95 | 0,665 | 0,589 | 0,077 | 34 ms |
| Hybride 0,35 | 21/22 | 22/22 | 0,98 | 0,637 | 0,572 | 0,065 | 33 ms |
| LLM (qwen2.5:3b) | 17/22 | 22/22 | 0,87 | - | - | aucune question hors sujet ne garde de passage | 11 761 ms |

(Marge : score le plus bas d'un bon passage moins score le plus haut d'une question hors sujet.
Plus elle est grande, plus un seuil sépare sans erreur ce qui répond de ce qui ne répond pas.)

## Ce que ça veut dire

- **Le classement de `bge-m3` est déjà parfait** sur ces questions (22/22 en premier) : le
  reclassement ne peut rien y gagner. Son apport est ailleurs : il **éloigne les mauvaises
  réponses du seuil**. Un extrait hors sujet n'a presque jamais les mots rares de la question, donc
  sa note baisse ; un bon extrait les a, donc la sienne monte.
- **Avec un modèle d'embedding moins bon**, le reclassement corrige aussi l'ordre (`nomic-embed-text` :
  19 puis 20 questions sur 22 avec le bon document en premier) et multiplie la marge par 3,7.
- **Le poids 0,15** donne la meilleure marge avec `bge-m3`. Au-delà, les mots-clés prennent trop de
  place : un extrait qui répète les mots de la question sans y répondre remonte.
- **Le seuil reste à 0,50** : il tombe entre la moins bonne bonne réponse (0,562) et la meilleure
  question hors sujet (0,452), avec de la marge des deux côtés.
- **Le LLM a été envisagé et écarté** : il place moins souvent le bon document en premier (20/22 et
  17/22) et ajoute plus de **12 secondes** par question sur un portable sans GPU, avant même la
  réponse. Un petit modèle note mal des passages qu'il lit en vrac.

## Limites du banc

- 22 questions et 6 hors sujet, écrites à la main : une tendance, pas une précision fine.
- Un document est « trouvé » s'il figure parmi les extraits : le banc ne dit pas si c'est le meilleur
  passage du document.
- Le LLM est mesuré avec une seule consigne et à température 0 ; une autre consigne ou un plus gros
  modèle ferait peut-être mieux, mais resterait lent sur cette machine.
