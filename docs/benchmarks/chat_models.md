# Banc d'essai : modèles de chat

Quel modèle de chat choisir pour Sensai, sur la machine qui le fait tourner ? Ce document
compare les candidats sur les vrais usages du projet, mesurés le 29 octobre 2026.

**En bref :** `qwen2.5:7b` réussit tout mais met environ 20 s par réponse à froid ;
`qwen2.5:3b` réussit tout sauf le type de congé (2 fois sur 3), deux fois plus vite.
`qwen3:4b` est éliminé : jusqu'à 5 minutes par réponse.

## La machine

| | |
|---|---|
| Processeur | AMD Ryzen 7 8840HS, 8 cœurs / 16 threads, AVX-512 |
| Mémoire | 14 Go, partagés avec la puce graphique intégrée ; ~9 Go libres en usage normal |
| Carte graphique | Radeon 780M intégrée, non utilisée par Ollama : **tout tourne sur le processeur** |
| Ollama | 0.34.2 |

Conséquence : au-delà de 8 milliards de paramètres, le modèle ne tient plus en mémoire.
Les candidats sont donc des modèles de 3 à 8B qui savent appeler des outils.

## La méthode

Le script [`back/benchmarks/Bench_chat.py`](../../back/benchmarks/Bench_chat.py) passe chaque
question par **le vrai pipeline de Sensai** : `chat_turn`, le prompt système RH, le RAG sur
`data/docs` (indexé avec `nomic-embed-text`), l'agent ReAct et ses outils, la demande de congé
avec confirmation (A3). Seules deux choses sont simulées :

- la base de données est un fichier temporaire ;
- la recherche web renvoie toujours le même résultat, avec un montant inventé exprès
  (« 12,34 € ») : une réponse qui le cite ne peut venir que de l'outil.

Six scénarios, trois passages chacun, température 0,2 :

| Scénario | Question | Réussi si |
|---|---|---|
| date | « on est quel jour ? » | la réponse donne le bon jour, sans outil |
| no tool | « Explique la différence entre un CDD et un CDI en trois phrases. » | réponse en français, sans outil |
| RAG (md) | « Combien de jours de congé ai-je pour mon mariage ? » | « 4 jours » (`loi_conge_mariage_pacs.md`) |
| RAG (pdf) | « Quel est le montant de la prime de cooptation pour le recrutement d'un CDI ? » | « 2 000 € » (accord NAO, PDF) |
| leave (A3) | « Je pose du 3 au 7 novembre 2026 pour des vacances. » | demande préparée, en attente de `/confirm` : `paid_leave`, du 2026-11-03 au 2026-11-07 |
| web search | « Quel est le montant actuel du SMIC horaire brut ? » | appelle `search_internet` puis cite 12,34 € |

Pour reproduire : `python back/benchmarks/Bench_chat.py qwen2.5:3b qwen2.5:7b --runs 3`.

## Les résultats

| Modèle | date | no tool | RAG (md) | RAG (pdf) | leave (A3) | web search | Total | Réponse complète, à froid (médiane / max) |
|---|---|---|---|---|---|---|---|---|
| **qwen2.5:3b** (1,9 Go) | 3/3 | 3/3 | 3/3 | 3/3 | 1/3 | 3/3 | **16/18** | **9,8 s / 26 s** |
| **qwen2.5:7b** (4,7 Go) | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | **18/18** (17 en réalité, voir plus bas) | 20,7 s / 61 s |
| qwen3:4b (2,5 Go) * | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 16/18 | 69 s (médiane, tous passages) / **297 s** |
| qwen3:4b, `think: false` * | 3/3 | 3/3 | 3/3 | 3/3 | – | – | arrêté | 42 s / 125 s |

« À froid » = premier passage de chaque scénario. Les passages suivants, identiques, profitent
du cache de prompt d'Ollama (premier mot en 0,2 s) : ce n'est pas ce que vit un utilisateur.
Le prompt envoyé fait environ 1 370 tokens (persona, profil, extraits RAG, consignes des outils).

\* qwen3:4b a été mesuré lors d'un premier passage, avant les corrections décrites plus bas
(ancien prompt système) ; il n'a pas été relancé, ses temps de réponse l'éliminant de toute façon.

### Ce que les chiffres ne disent pas

- **qwen2.5:3b, demande de congé** : il appelle bien l'outil les 3 fois, avec les bonnes dates,
  mais classe 2 fois les vacances en `unpaid_leave` au lieu de `paid_leave`. C'est exactement le
  cas que la confirmation (A3) rattrape : le salarié voit le type avant d'enregistrer.
- **qwen2.5:7b, langue** : une fois sur 18, la réponse a basculé en chinois au milieu d'une
  phrase (« d'une durée限定对话上下文… »). Le contrôle automatique ne l'a pas vu ; en vrai,
  c'est un échec. Ce n'est pas arrivé avec qwen2.5:3b dans ce banc.
- **qwen3:4b** : il « réfléchit » avant chaque réponse (5 700 caractères pour « 2+2 », 110 s).
  Avec `think: false`, il réfléchit quand même, mais en anglais et dans la réponse
  (« Okay, let's see. The user is asking… »). Une fois, il a inventé un SMIC (« 14,12 € »,
  `\boxed{14,12}`) sans chercher. Inutilisable en direct sur cette machine.

## Trois défauts du projet trouvés grâce au banc

Le premier passage a montré que **qwen2.5:3b ne préparait jamais la demande de congé (0/3)
ni ne lançait la recherche web (0/3)**. Ce n'était pas le modèle, mais le projet. Chaque piste
a été testée séparément (3 essais chacune, `qwen2.5:3b`) :

| Changement | Recherche web | Demande de congé |
|---|---|---|
| Avant | 0/3 | 0/3 |
| Extraits RAG mis dans le message système, avec un texte qui les décrit au lieu de donner un ordre | – | 0/3 |
| Prompt système RH réécrit : il disait aussi « si les documents ne répondent pas, dis-le » | **3/3** | 0/3 |
| Même demande de congé, avec / sans extraits RAG (quel que soit le prompt) | – | 0/3 / **3/3** |
| Extraits placés en tête du prompt, dans le message utilisateur, ou en résultat d'outil | – | 1/3 au mieux |
| **Pas d'extraits RAG pour une demande de congé** (détection « je pose… », « je voudrais poser… ») | – | **3/3** outil appelé |

Ce qui a été gardé :

1. Les extraits RAG vont **dans le message système**, dans une section titrée qui les décrit :
   trouvés automatiquement, peut-être hors sujet, à citer s'ils répondent, à ignorer sinon, et
   jamais une raison de ne pas utiliser un outil ([`rag/Retriever.py`](../../back/rag/Retriever.py)).
2. Le prompt système RH dit d'utiliser l'outil pour une démarche, et de ne répondre « je ne sais
   pas » qu'en dernier recours ([`config/system_prompt.txt`](../../back/config/system_prompt.txt)).
3. Une demande de congé est une action : le RAG documentaire est sauté pour ce tour
   ([`Agents/Router.py`](../../back/Agents/Router.py), `asks_for_leave`). « Comment poser un
   congé ? » garde le RAG.

## Recommandation

| Usage | Modèle | Pourquoi |
|---|---|---|
| Démo en direct, usage quotidien | **qwen2.5:3b** | 16/18, ~10 s par réponse ; l'erreur de type de congé est rattrapée par la confirmation |
| Montrer la meilleure qualité (keynote) | **qwen2.5:7b** | 18/18 sur le fond, mais ~20 s par réponse et jusqu'à 1 min à froid : à préchauffer, sur une question préparée |
| À éviter sur cette machine | qwen3:4b, llama3.2:1b | trop lent / outils non fiables (voir le README) |

La configuration n'a pas été changée (`MODEL=qwen2.5:3b` dans `.env`). Pour passer au 7B
pendant une session : `/model qwen2.5:7b`, l'historique est gardé.

## Limites du banc

- 3 passages par scénario : assez pour voir un défaut systématique, pas pour une statistique fine.
- Les contrôles sont automatiques (présence d'un chiffre, d'un outil, de mots français) : ils ont
  laissé passer la réponse en chinois, relevée à la main dans les résultats bruts.
- La recherche web est simulée : la qualité réelle des résultats Tavily, Brave ou Exa n'est pas mesurée.
- Les temps dépendent de la charge de la machine ; ils ont été mesurés sans autre application lourde.
