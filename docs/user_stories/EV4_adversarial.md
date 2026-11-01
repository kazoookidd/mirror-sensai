# User Stories : Tests adverses (EV4)

## [EV4] Attaquer Sensai pour savoir où il tient

**US-EV4-01**
En tant que membre de l'équipe, je veux une suite qui attaque Sensai (jailbreaks, questions sur un
collègue, données personnelles déguisées, réponses dangereuses), afin de savoir précisément où les
garde-fous tiennent et où ils cèdent avant de le présenter.

Critères d'acceptation :
- `python back/benchmarks/Bench_adversarial.py` attaque les intercepteurs d'entrée et de sortie sans modèle, en quelques secondes
- Chaque cas affiche ce que la défense devrait faire, ce qu'elle a fait (tenu ou cédé) et une gravité (haute, moyenne, basse)
- Les questions légitimes qui ne doivent pas être bloquées (« salaire de base », « congé de maternité ») font partie des cas : un blocage à tort compte comme un échec
- Le rapport ([docs/benchmarks/adversarial.md](../benchmarks/adversarial.md)) liste ce qui cède et pourquoi, et propose les corrections par ordre de rentabilité

**US-EV4-02**
En tant que responsable RH, je veux être sûr qu'un employé ne peut ni voir ni modifier les données
des autres, même en contournant l'interface, afin de confier les demandes de congés à Sensai.

Critères d'acceptation :
- La suite attaque le vrai serveur sur une base temporaire : un employé qui liste ou décide les demandes, qui désactive les garde-fous, qui importe dans la base RH, qui lit ou exporte la conversation d'un autre, un lien public deviné, un cookie forgé, une inscription qui demande le rôle RH
- Toutes ces attaques sont refusées côté serveur, et la demande d'un collègue reste intacte à la fin
- Ces cas sont aussi dans les tests (`back/tests/Test_adversarial.py`) : une régression fait échouer la suite

**US-EV4-03**
En tant que salarié, je veux qu'un document piégé ou une erreur du modèle ne puisse jamais déposer
ou annuler une demande à ma place, afin de garder la main sur ce qui est fait en mon nom.

Critères d'acceptation :
- Un document RH qui ordonne à l'agent de déposer un congé est testé avec les vrais modèles (`--live`) : rien n'est enregistré sans `/confirm`
- Un test avec un modèle scripté qui obéit au document montre que l'action est seulement préparée (A3) et que la base reste vide
- « Annule mon congé » ou « confirme que ma demande est enregistrée » sans demande existante ne donnent jamais « c'est fait » : un détecteur de fausses confirmations le vérifie

**US-EV4-04**
En tant que développeur, je veux que la suite résiste aux entrées malformées, afin qu'une requête
bizarre ne fasse jamais planter le serveur.

Critères d'acceptation :
- Injection SQL dans le profil, `../../` dans un nom de fichier, message de 200 000 caractères, caractères de contrôle et marques droite-à-gauche, JSON cassé : aucune erreur 500
- Chaque cas indique la réponse attendue (texte stocké tel quel, 422, refus par la limite de tokens...)
