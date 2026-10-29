# Banc d'essai : modèles d'embedding

Les embeddings servent deux fois dans Sensai : retrouver les bons passages des documents RH
(RAG, R1) et reconnaître une question déjà posée (cache sémantique, A6). Ce document compare
`nomic-embed-text` (le modèle actuel) et `bge-m3` (multilingue), mesurés le 29 octobre 2026
sur la même machine que les [modèles de chat](chat_models.md) (Ryzen 7 8840HS, sans GPU).

**En bref :** les deux trouvent le bon document pour toutes les questions, mais `bge-m3` le met
plus souvent en premier et **sépare beaucoup mieux une bonne réponse d'une question hors sujet**.
Avec `nomic-embed-text`, le seuil actuel (0,70) prive déjà 5 questions sur 22 de leurs extraits.
Changer de modèle demande de changer les seuils : rien n'a été changé pour l'instant.

## La méthode

Le script [`back/benchmarks/Bench_embeddings.py`](../../back/benchmarks/Bench_embeddings.py)
utilise **le pipeline du projet** : `data/docs` (8 documents, dont l'accord NAO en PDF) est
découpé et indexé par `rag/Store.py` (69 morceaux), puis chaque question est cherchée par
`rag/Retriever.py`, exactement comme dans le chat.

- **22 questions RH** dont on connaît le document source (mariage, décès, congés payés, jours
  fériés, télétravail, règlement intérieur, mutuelle, accord NAO).
- **6 questions hors sujet** (pizza, football, météo...) : leur meilleur score montre jusqu'où
  monte une mauvaise correspondance, pour choisir `RAG_MIN_SCORE`.
- **10 paires de questions** pour le cache : 5 qui veulent dire la même chose, 5 proches mais
  différentes (« jours pour un mariage » / « jours pour un décès »), comparées comme le fait le
  cache, pour choisir `CACHE_SIMILARITY`.

`rag/Embeddings.py` ajoute les préfixes `search_document:` / `search_query:`, prévus pour
`nomic-embed-text`. `bge-m3` a été mesuré tel que le projet l'appellerait (avec les préfixes)
et sans les préfixes.

Pour reproduire : `python back/benchmarks/Bench_embeddings.py nomic-embed-text bge-m3 bge-m3:noprefix`.

## Les résultats

### Retrouver le bon document (RAG)

| Modèle | Taille | Indexation (69 morceaux) | Bon document en 1er | Bon document dans les 3 premiers | MRR | Recherche (médiane) |
|---|---|---|---|---|---|---|
| nomic-embed-text | 274 Mo | 17,8 s | 19/22 | **22/22** | 0,92 | 18 ms |
| **bge-m3** | 1,2 Go | 37,8 s | **22/22** | **22/22** | **1,00** | 37 ms |
| bge-m3 sans préfixes | 1,2 Go | 34,0 s | 21/22 | **22/22** | 0,98 | 32 ms |

(MRR : 1 si le bon document est toujours premier, 0,5 s'il est deuxième...)

### Séparer une bonne réponse d'une question hors sujet (`RAG_MIN_SCORE`)

| Modèle | Bon passage : min / médiane | Hors sujet, meilleur score : médiane / max | Écart (min bon − max hors sujet) | Gardés à 0,70 : bons / hors sujet |
|---|---|---|---|---|
| nomic-embed-text | 0,681 / 0,759 | 0,644 / 0,662 | **0,019** | 17/22 / 0/6 |
| **bge-m3** | 0,538 / 0,671 | 0,358 / 0,454 | **0,084** | 5/22 / 0/6 |
| bge-m3 sans préfixes | 0,505 / 0,704 | 0,330 / 0,485 | 0,020 | 11/22 / 0/6 |

### Reconnaître une question déjà posée (`CACHE_SIMILARITY`)

| Modèle | Même sens : min / médiane | Sens différent : médiane / max | Servis à 0,92 : même sens / sens différent |
|---|---|---|---|
| nomic-embed-text | 0,772 / 0,780 | **0,817 / 0,832** | 0/5 / 0/5 |
| **bge-m3** | 0,764 / 0,829 | 0,730 / 0,779 | 1/5 / 0/5 |

(Le cache embarque la question brute, sans préfixe : les deux variantes de `bge-m3` sont identiques ici.)

## Ce que ça veut dire

- **Avec nomic-embed-text, le seuil 0,70 est trop haut et l'écart est fragile.** 5 questions sur
  22 n'ont aucun extrait alors que le bon document est trouvé (score 0,68-0,70), et la marge
  entre la pire bonne réponse et la meilleure question hors sujet n'est que de 0,02. Baisser le
  seuil ferait vite entrer du hors-sujet.
- **bge-m3 sépare nettement mieux** (marge de 0,08) et met le bon document premier à chaque
  fois. Ses scores sont plus bas en général : avec le seuil actuel de 0,70, il ne garderait que
  5 questions sur 22. Il faudrait passer `RAG_MIN_SCORE` vers **0,50**.
- **Les préfixes de nomic aident bge-m3** sur ces documents (marge 0,084 contre 0,020 sans) :
  si on change de modèle, inutile de toucher au code de `rag/Embeddings.py`.
- **Cache : nomic-embed-text ne sait pas distinguer.** Deux questions *différentes* sur le même
  thème obtiennent un score plus élevé (0,82) que deux formulations de la *même* question (0,78).
  Le seuil de 0,92 évite les fausses réponses, mais le cache ne sert presque jamais une
  reformulation. Avec bge-m3, l'ordre est le bon (même sens 0,83 en médiane, sens différent
  0,78 au plus) : un seuil vers **0,80** servirait la plupart des reformulations sans fausse
  réponse sur ces paires.
- **Coût** : bge-m3 pèse 1,2 Go en mémoire (contre 274 Mo), indexe deux fois plus lentement
  (38 s pour tous les documents, une seule fois) et cherche en 37 ms au lieu de 18 : invisible
  à côté des 10 s du modèle de chat.

## Recommandation (non appliquée)

Passer à `bge-m3`, avec :

```env
RAG_EMBED_MODEL=bge-m3
RAG_MIN_SCORE=0.50
CACHE_EMBED_MODEL=bge-m3
CACHE_SIMILARITY=0.80
```

puis `/ingest` pour réindexer (le cache se vide à cette occasion). À faire en même temps que le
choix du modèle de chat, et à vérifier dans le chat sur quelques questions avant la keynote.

## Limites du banc

- 22 questions et 10 paires, écrites à la main : de quoi voir une tendance et poser des seuils,
  pas une précision fine. Les seuils proposés sont à revérifier si les documents changent.
- Un document est « trouvé » s'il figure parmi les extraits ; la qualité de la réponse finale
  dépend ensuite du modèle de chat (voir [chat_models.md](chat_models.md)).
