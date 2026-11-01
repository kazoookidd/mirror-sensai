# Banc d'essai : les formulaires écrits par le modèle (X4, `ask_form`)

`ask_form` laisse le modèle écrire lui-même un petit formulaire (un titre, 1 à 5 champs) quand il a
besoin de plusieurs réponses à la fois. Avant de l'activer, nous avons mesuré si les modèles s'en
servent bien. Mesuré le 1er novembre 2026, sur la machine des [autres bancs](chat_models.md).

**En bref :** **aucun des deux modèles ne l'utilise jamais**, ni à bon escient (0/12), ni à tort
(0/12), et aucun schéma invalide n'a été produit. Le 7B demande même en texte « veuillez me fournir
les détails suivants : votre nouveau numéro… », exactement ce que le formulaire devait remplacer.
`ask_form` reste donc **désactivé par défaut** (`AGENT_ASK_FORM=false`).

## La méthode

Le script [`back/benchmarks/Bench_forms.py`](../../back/benchmarks/Bench_forms.py) active `ask_form`
et passe chaque message par le vrai pipeline (prompt RH, RAG sur `data/docs`, agent, outils),
2 passages par message :

- **où un formulaire a du sens** : « Je veux déclarer un changement d'adresse. », « Je voudrais
  prendre rendez-vous avec le service RH. », « Je veux signaler une erreur sur ma fiche de paie. »
- **où il n'en a pas** : « Combien de jours de congé pour un mariage ? », « Explique la différence
  entre un CDD et un CDI en trois phrases. », « Je veux poser un congé. » (qui a son propre formulaire)

Pour reproduire : `python back/benchmarks/Bench_forms.py qwen2.5:3b qwen2.5:7b --runs 2`.

## Les résultats

| Modèle | `ask_form` là où il avait du sens | Description refusée | `ask_form` à tort | Ce qu'il fait à la place |
|---|---|---|---|---|
| qwen2.5:3b | **0/6** | 0 | 0/6 | renvoie vers le service RH, ou pose une question en texte |
| qwen2.5:7b | **0/6** | 0 | 0/6 | demande les informations en texte (« veuillez me fournir… ») |

« Je veux poser un congé. » a ouvert le formulaire de congé à chaque fois (4/4), sans le modèle :
ce cas ne dépend pas de lui.

## Ce que ça veut dire

- **Le risque redouté ne s'est pas produit** : pas de formulaire absurde, pas de schéma cassé, pas
  d'usage à tort. Et même s'il se produisait, un formulaire du modèle ne fait que recueillir des
  réponses : il ne peut rien enregistrer ni déclencher, et sa description est validée strictement
  (1 à 5 champs, 3 types, 2 à 6 options) avant d'être affichée.
- **Mais l'outil n'apporte rien avec ces modèles** : ils ne choisissent pas spontanément un outil
  qui sert à *demander* plutôt qu'à *faire*. C'est la même observation qu'avec `ask_user`.
- **Ce qui marche, c'est le formulaire construit par le code** : la demande de congé sans date ouvre
  son formulaire à tous les coups, parce que la décision ne dépend pas du modèle.

## Décision

`ask_form` reste dans le code, testé et **désactivé par défaut**. Il peut être activé
(`AGENT_ASK_FORM=true`) avec un modèle plus grand ; il faudra alors relancer ce banc pour vérifier
qu'il s'en sert à bon escient.

## Limites

- 3 situations « utiles » et 3 « inutiles », 2 passages chacune : assez pour voir un comportement
  systématique (0 sur 12), pas pour estimer un taux rare.
- Le banc a aussi révélé un faux positif du filtre de sortie (EV2) : « un salarié peut bénéficier
  de 4 jours de congé… » était bloqué. C'est corrigé (voir [adversarial.md](adversarial.md)).
