# User Stories : Cache sémantique (A6)

**US-A6-01**
En tant qu'employé, je veux obtenir immédiatement la réponse à une question que
l'assistant a déjà traitée (même formulée autrement), afin de ne pas attendre une
nouvelle génération pour une question fréquente comme « comment poser un congé ? ».

Critères d'acceptation :
- Une question de sens proche d'une question déjà posée (similarité d'embeddings au-dessus du seuil, 0,92 par défaut) reçoit la réponse mémorisée, sans appel au modèle
- La réponse est affichée avec une ligne discrète indiquant qu'elle vient du cache et le pourcentage de similarité
- Ni la compression, ni la recherche dans les documents (RAG), ni le modèle ne sont sollicités lors d'un hit
- L'échange est enregistré dans l'historique comme n'importe quel autre

**US-A6-02**
En tant qu'administrateur, je veux que le cache ne serve jamais une réponse
périmée ou hors-sujet, afin qu'un gain de vitesse ne devienne pas une source d'erreurs RH.

Critères d'acceptation :
- Les questions qui dépendent de la conversation (« et pour demain ? », « explique ça ») ne sont jamais servies depuis le cache
- Les questions sensibles au temps (aujourd'hui, demain, dernier, météo, actualités…) et les demandes de recherche web ne sont ni servies ni stockées
- Une réponse obtenue avec des outils (résultats web), un refus (« je ne peux pas faire de recherches ») ou une réponse très courte n'est jamais stockée
- Par défaut, seules les réponses données au début d'une conversation (sans historique) sont stockées
- Une entrée expire après `CACHE_TTL_HOURS` (168 h par défaut) et le cache est borné (`CACHE_MAX_ENTRIES`, les moins utilisées partent d'abord)
- Les entrées ne sont réutilisées que pour le même modèle et le même prompt de persona

**US-A6-03**
En tant qu'employé, je veux que mes réponses mémorisées ne soient pas réutilisées pour
un autre employé, afin de protéger la confidentialité des échanges RH.

Critères d'acceptation :
- Par défaut (`CACHE_SCOPE=user`), chaque utilisateur ne retrouve que ses propres réponses
- `CACHE_SCOPE=global` permet de partager le cache entre utilisateurs, pour les FAQ non personnelles

**US-A6-04**
En tant qu'utilisateur, je veux pouvoir consulter, vider et désactiver le cache sans
quitter l'assistant, afin de garder la main si une réponse mémorisée me semble fausse.

Critères d'acceptation :
- `/cache` affiche le nombre d'entrées, de hits, le seuil, la durée de vie et le modèle d'embedding ; `/cache clear` vide les entrées de l'utilisateur
- `/settings cache on|off` active ou désactive le cache à chaud
- Après `/ingest`, le cache est vidé : ses réponses venaient des anciens documents

**US-A6-05**
En tant que développeur, je veux que le cache ne casse jamais une conversation, afin
qu'une panne de l'embedding n'empêche pas l'assistant de répondre.

Critères d'acceptation :
- Si le modèle d'embedding n'est pas installé, une seule note discrète l'indique et le cache est désactivé pour la session
- Si Ollama ne répond pas à l'embedding ou si la base est en erreur, le tour se déroule sans cache
