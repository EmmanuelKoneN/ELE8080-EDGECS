# Serveur DERMS — centre de gestion sur site (section 8.1)

Centre de gestion sur site. Il connaît l'inventaire des DER, calcule les consignes
et les envoie aux passerelles en DNP3, puis suit les mesures en retour.

Pour la vue d'ensemble du système, voir le [README principal](../README.md).

| Module | Rôle |
|---|---|
| `interface_ui/` | Application Web pour l'opérateur : état des DER, objectifs, horaires |
| `initialisation/` | Démarrage du système et inventaire des DER |
| `configuration/` | IP, ports, points DNP3, limites de fonctionnement |
| `planification/` | Profil de puissance, répartition entre les DER, écrêtage des pointes, contingences |
| `stockage/` | Stockage local : inventaire, horaires, journal |
| `dnp3_master/` | Client DNP3 (station maîtresse) : envoie les consignes, lit les mesures |
| `simulation_pcc/` | Réseau simulé : fournit la puissance au point de couplage commun (PCC) |

**Lancer :** depuis la racine du dépôt, `python -m derms.main`

## Fonctionnement du serveur

Selon le [diagramme d'architecture](../assets/EDGECS_architecture.drawio), le serveur DERMS est un
hôte Linux. L'opérateur y accède par navigateur Web, en HTTP(S).

Échanges logiciels internes :

- `configuration/` alimente `initialisation/`.
- `initialisation/` et `interface_ui/` alimentent `planification/`.
- `planification/` échange avec `stockage/`.
- `planification/` échange les commandes et les télémesures avec `dnp3_master/`.

## Client DNP3 maître

Le module `dnp3_master/` est la station maîtresse : il envoie les consignes aux passerelles et lit
leurs mesures, en DNP3 sur TCP/IP (IEEE 1815, profil DER IEEE 1815.2).

La cible est définie dans `derms/main.py` :

| Constante | Valeur | Rôle |
|---|---|---|
| `GATEWAY_ADDRESS` | `127.0.0.1` | Adresse de la passerelle DNP3 à joindre |
| `GATEWAY_PORT` | `20000` | Port DNP3 de la passerelle |

Pour l'instant, `derms/main.py` affiche seulement « à implémenter » et ne vise qu'une passerelle.

Les points DNP3 sont définis dans [points_dnp3.yaml](../points_dnp3.yaml), encore à l'état de
brouillon. Ce fichier est le contrat avec la passerelle : voir la règle d'équipe dans
[CONTRIBUTING.md](../CONTRIBUTING.md) avant de le modifier.

> **TODO** : indiquer la bibliothèque DNP3 retenue (pas encore choisie).

> **TODO** : documenter les paramètres DNP3 (adresses, fréquence de lecture des mesures) et la
> connexion aux 3 passerelles.

## Simulation du réseau

Le module `simulation_pcc/` contient le code du réseau simulé. Dans le
[diagramme d'architecture](../assets/EDGECS_architecture.drawio), la simulation du réseau est un
bloc distinct du serveur DERMS, composé de :

| Élément | Description |
|---|---|
| Réseau principal | Poste, transformateur |
| Charge simulée et PCC | Profil de consommation journalier, puissance appelée au PCC |

La simulation fournit au serveur DERMS la puissance du réseau simulée au PCC. Le diagramme indique
aussi un couplage de simulation entre les DER et le réseau ; les modèles de DER sont décrits dans
[gateway/README.md](../gateway/README.md).

> **TODO** : documenter le modèle du réseau, le profil de consommation journalier et le couplage
> de simulation DER ↔ réseau.
