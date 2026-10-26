# User Stories : Limite de tokens et affichage de l'usage

## [M2, extension] Limite de tokens

**US-TK-01** En tant qu'utilisateur, je veux que l'assistant refuse d'envoyer un message quand le contexte dépasse la limite de tokens, même après compression, afin d'éviter que le modèle tronque silencieusement le début de la conversation et me réponde à côté.

Critères d'acceptation :

* Si le contexte estimé dépasse `CONTEXT_TOKEN_BUDGET` après compression, le message n'est pas envoyé au modèle
* Un message explique ce qui s'est passé et comment s'en sortir (`/new`, `/conversations`, ou changer le réglage)
* Rien n'est sauvegardé pour ce tour : l'historique de la conversation reste intact
* La conversation reste bloquée tant que son contexte dépasse la limite, mais une nouvelle conversation fonctionne normalement

**US-TK-02** En tant qu'administrateur ou développeur, je veux choisir dans la configuration si l'assistant doit se bloquer ou continuer après la limite, afin d'adapter le comportement à l'usage (prudence en contexte RH, souplesse en démo ou en test).

Critères d'acceptation :

* `TOKEN_LIMIT_ACTION=block` (valeur par défaut) bloque le message
* `TOKEN_LIMIT_ACTION=continue` envoie le message après un avertissement explicite
* L'option `--on-token-limit` en ligne de commande remplace la valeur du fichier de configuration
* Une valeur inconnue affiche un avertissement et applique le comportement le plus sûr (`block`)

---

## Affichage de l'usage des tokens

**US-TK-03** En tant qu'utilisateur, je veux voir discrètement sous chaque réponse le nombre de tokens utilisés par l'échange, afin de comprendre ce que coûte chaque message sans que l'affichage ne gêne la lecture.

Critères d'acceptation :

* Une ligne courte (`tokens: 83 in · 3 out`) s'affiche après chaque réponse : tokens envoyés au modèle et tokens de la réponse
* Les valeurs sont celles rapportées par Ollama ; à défaut, une estimation est utilisée et marquée d'un `~`
* La ligne est atténuée (texte grisé) dans un terminal, sans code d'échappement quand la sortie est redirigée ou si `NO_COLOR` est défini
* `SHOW_TOKEN_USAGE=false` désactive l'affichage

**US-TK-04** En tant qu'utilisateur, je veux être prévenu quand le contexte approche de la limite, afin d'anticiper la compression ou le blocage plutôt que de les subir.

Critères d'acceptation :

* Tant que l'usage reste sous le seuil (80 % par défaut, celui de la compression), aucun pourcentage n'est affiché
* À partir du seuil, la ligne ajoute le pourcentage du contexte utilisé (`context 86% (86/100)`)
* Au-delà de la limite, la ligne indique `limit exceeded`
