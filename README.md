# ELE8080-EDGECS
**DERMS sur site avec interface DNP3 vers des passerelles DER**

Projet intégrateur de grande envergure (ELE8080), Polytechnique Montréal, automne 2026 – hiver 2027.
Client : Eaton – Centre d'excellence Energy Control Systems (ECS).

## Le projet en bref

Un DERMS (*Distributed Energy Resource Management System*) coordonne plusieurs ressources
énergétiques distribuées (DER) : batteries (BESS), génératrices, panneaux solaires, etc.

L'objectif est de démontrer un **chemin fonctionnel complet** entre un DERMS et plusieurs DER :

1. le DERMS calcule une consigne (écrêtage des pointes, répartition planifiée, contingence) ;
2. il l'envoie en **DNP3** (IEEE 1815) à une passerelle DER ;
3. la passerelle l'interprète et l'applique à la DER ;
4. la DER renvoie ses mesures et états, qui remontent jusqu'au DERMS.

Le système fonctionne **entièrement sur site**, sur un réseau local isolé, sans service infonuagique.

## Architecture (MVP)

```
┌──────────────────────────── DERMS ─────────────────────────────┐
│  Simulation PCC ─▶ Planification ─▶ Client DNP3 (maître)        │
│  Interface UI · Initialisation · Configuration · Stockage        │
└───────────────────────────────┬────────────────────────────────┘
                                │  DNP3 sur TCP/IP
                                │  ▼ consignes   ▲ mesures, états
┌───────────────────────── GATEWAY (×1 à 3) ─────────────────────┐
│  Outstation DNP3 ─▶ Application réceptrice ─▶ DER simulées       │
│  Journaux                                                        │
└────────────────────────────────────────────────────────────────┘
```

Le détail de chaque module est décrit dans le cahier des charges (sections 8.1 à 8.4).

## Organisation du dépôt

| Dossier / fichier | Contenu |
|---|---|
| `derms/` | Serveur DERMS : UI, initialisation, configuration, planification, stockage, client DNP3, simulation du réseau au PCC |
| `gateway/` | Passerelle DER : outstation DNP3, application réceptrice, journaux, simulation des DER |
| `points_dnp3.yaml` | Liste des points DNP3 partagée par les deux côtés (le « contrat » entre DERMS et gateway) |
| `requirements.txt` | Dépendances Python |

## Lancer le prototype (MVP sur un seul PC)

Pour l'instant, tout tourne sur le même ordinateur et communique en DNP3 via `127.0.0.1`.

```bash
pip install -r requirements.txt

# Terminal 1 : la passerelle (écoute sur le port 20000)
python -m gateway.main

# Terminal 2 : le DERMS (se connecte à la passerelle)
python -m derms.main
```

Pour une 2e ou 3e passerelle : `python -m gateway.main 20001`, `python -m gateway.main 20002`.

## Étapes du projet

| Étape | Configuration |
|---|---|
| **MVP** | 1 DERMS + 1 passerelle + 1 DER, sur le même PC |
| **Version finale** | 1 DERMS + 3 passerelles, sur Raspberry Pi reliés par un switch Ethernet (ou la passerelle Eaton si fournie) |

## Normes de référence

- **IEEE 2030.11-2021** : spécification fonctionnelle du DERMS
- **IEEE 1815** : protocole DNP3
- **IEEE 1815.2** : profil DNP3 pour les DER (correspondance des points)

## Technologies

- **Python** (langage principal)
- **DNP3** : bibliothèque en cours d'évaluation
- **Docker** pour l'application réceptrice (exigence du client)

## Équipe

| Volet | Responsable(s) |
|---|---|
| DERMS | *à compléter* |
| Gateway | *à compléter* |
| Communication (DNP3) | *à compléter* |
| Simulation (réseau + DER) | *à compléter* |

Membres : Chloé Truchon, Alireza Jafari, Cazy Gaspard, Flavio Zapata, Emmanuel Kone, Adja Sokhna Fall.

## Règles de travail

- Ne jamais pousser directement sur `main`.
- Une branche par tâche (ex. `derms/planification`), puis une pull request.
- Chaque pull request est relue par au moins un autre membre avant d'être fusionnée.
- Toute modification de `points_dnp3.yaml` doit être validée par le volet Communication.
