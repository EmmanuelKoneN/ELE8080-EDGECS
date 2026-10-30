# Passerelle DER — nœud EDGE (sections 8.2 et 8.3)

Fait le lien entre le DERMS et une ou plusieurs DER. Elle reçoit les commandes DNP3,
les applique aux DER et renvoie leurs mesures, états et alarmes.

Pour la vue d'ensemble du système, voir le [README principal](../README.md).

| Module | Rôle |
|---|---|
| `dnp3_outstation/` | Passerelle DNP3 (station semi-asservie) : écoute les commandes du DERMS (section 8.2) |
| `app_receptrice/` | Interprète les commandes et les achemine vers la bonne DER (section 8.3) |
| `journaux/` | Journalisation des événements de la passerelle |
| `simulation_der/` | Modèles logiciels des DER : BESS, génératrice, etc. (section 8.4) |

**Lancer :** depuis la racine du dépôt, `python -m gateway.main [port]`
(port 20000 par défaut ; 20001 et 20002 pour les autres passerelles)

## Outstation DNP3

Le module `dnp3_outstation/` est la station semi-asservie : il écoute les commandes du DERMS, en
DNP3 sur TCP/IP (IEEE 1815, profil DER IEEE 1815.2), et les transmet à l'application réceptrice.

L'écoute est définie dans `gateway/main.py` :

| Constante | Valeur | Rôle |
|---|---|---|
| `LISTEN_ADDRESS` | `127.0.0.1` | Adresse d'écoute de l'outstation DNP3 |
| `DEFAULT_PORT` | `20000` | Port DNP3 utilisé si aucun port n'est donné en argument |

Pour l'instant, `gateway/main.py` affiche seulement « à implémenter ».

Les points DNP3 sont définis dans [points_dnp3.yaml](../points_dnp3.yaml), encore à l'état de
brouillon. Ce fichier est le contrat avec le DERMS : voir la règle d'équipe dans
[CONTRIBUTING.md](../CONTRIBUTING.md) avant de le modifier.

> **TODO** : indiquer la bibliothèque DNP3 retenue (pas encore choisie).

> **TODO** : documenter les paramètres DNP3 (adresses) et l'adresse d'écoute sur Raspberry Pi.

## Application réceptrice

Le module `app_receptrice/` interprète les commandes reçues et les achemine vers la bonne DER
(section 8.3). Elle doit tourner dans un conteneur Docker (exigence du client).

> **TODO** : ajouter le Dockerfile et documenter la construction et le lancement du conteneur.

## Modèles DER

Le module `simulation_der/` contient les modèles logiciels des DER : BESS, génératrice, etc.
(section 8.4). Dans le [diagramme d'architecture](../assets/EDGECS_architecture.drawio), la
simulation des DER est un bloc distinct des passerelles, qui regroupe les DER 1 à 3.

L'interface entre la passerelle et les DER n'impose pas de protocole. Le diagramme indique aussi
un couplage de simulation entre les DER et le réseau ; la simulation du réseau est décrite dans
[derms/README.md](../derms/README.md).

> **TODO** : documenter le modèle de chaque DER (équations, paramètres, limites).

> **TODO** : préciser le protocole retenu entre la passerelle et les DER.
