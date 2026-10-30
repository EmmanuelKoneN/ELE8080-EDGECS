# ELE8080-EDGECS
**DERMS sur site avec interface DNP3 vers des passerelles DER**

Projet intégrateur de grande envergure (ELE8080), Polytechnique Montréal, automne 2026 – hiver 2027.

Client : Eaton – Centre d'excellence Energy Control Systems (ECS).

## Contexte

Un DERMS (*Distributed Energy Resource Management System*) coordonne plusieurs ressources
énergétiques distribuées (DER) : batteries (BESS), génératrices, panneaux solaires, etc.

Le système fonctionne **entièrement sur site**, sur un réseau local isolé, sans service infonuagique.

## Objectifs

L'objectif est de démontrer un **chemin fonctionnel complet** entre un DERMS et plusieurs DER :

1. le DERMS calcule une consigne (écrêtage des pointes, répartition planifiée, contingence)
2. il l'envoie en **DNP3** (IEEE 1815) à une passerelle DER
3. la passerelle l'interprète et l'applique à la DER
4. la DER renvoie ses mesures et états, qui remontent jusqu'au DERMS

## Architecture

Le détail de chaque module est décrit dans le cahier des charges (sections 8.1 à 8.4).

### MVP

**1 DERMS + 1 passerelle + 1 DER, sur le même PC**, qui communiquent en DNP3 via `127.0.0.1`.

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

> **TODO** : ajouter un diagramme du MVP dans `assets/` (aucun n'existe pour l'instant).

### Version finale

**1 DERMS + 3 passerelles, sur Raspberry Pi reliés par un switch Ethernet** (ou la passerelle Eaton
si fournie).

Diagramme de référence : [assets/EDGECS_architecture.drawio](assets/EDGECS_architecture.drawio).

- Le serveur DERMS communique en DNP3 sur TCP/IP (IEEE 1815, profil DER IEEE 1815.2) avec les
  3 passerelles, à travers le réseau Ethernet.
- L'opérateur accède à l'interface Web du DERMS par navigateur, en HTTP(S).
- La simulation du réseau fournit au DERMS la puissance au PCC.
- La simulation des DER regroupe les modèles logiciels des DER 1 à 3, reliés aux passerelles.

> **TODO** : exporter le diagramme en image dans `assets/` et l'afficher ici (GitHub n'affiche pas
> un fichier `.drawio`). Ajouter alors `IMAGE_PATH = assets` au `Doxyfile`.

> **TODO** : préciser l'adressage IP de la version finale.

## Technologies

- **Python** (langage principal)
- **DNP3** : bibliothèque de communication
- **Docker** pour l'application réceptrice (exigence du client)

> **TODO** : indiquer la bibliothèque DNP3 retenue (pas encore choisie).

## Normes de référence

- **IEEE 2030.11-2021** : spécification fonctionnelle du DERMS
- **IEEE 1815** : protocole DNP3
- **IEEE 1815.2** : profil DNP3 pour les DER (correspondance des points)

## Structure du dépôt

| Dossier / fichier | Contenu |
|---|---|
| `derms/` | Serveur DERMS : UI, initialisation, configuration, planification, stockage, client DNP3, simulation du réseau au PCC |
| `gateway/` | Passerelle DER : outstation DNP3, application réceptrice, journaux, simulation des DER |
| `points_dnp3.yaml` | Liste des points DNP3 partagée par les deux côtés (le « contrat » entre DERMS et gateway) |
| `assets/` | Diagramme d'architecture |
| `requirements.txt` | Dépendances Python |
| `requirements-dev.txt` | Outils de développement et d'analyse |
| `CONTRIBUTING.md` | Standard de programmation, règles d'équipe, outils et tutoriels |

## Démarrage rapide

Pour l'instant, tout tourne sur le même ordinateur et communique en DNP3 via `127.0.0.1`.

Le projet est au stade de l'échafaudage : les deux programmes démarrent, mais affichent seulement
« à implémenter ». Aucun échange DNP3 n'a encore lieu.

```bash
pip install -r requirements.txt

# Terminal 1 : la passerelle (écoute sur le port 20000)
python -m gateway.main

# Terminal 2 : le DERMS (se connecte à la passerelle)
python -m derms.main
```

Pour une 2e ou 3e passerelle : `python -m gateway.main 20001`, `python -m gateway.main 20002`.
Le DERMS ne vise pour l'instant que le port 20000.

## Équipe

| Volet | Responsable(s) |
|---|---|
| DERMS | [Chloé Truchon](https://www.linkedin.com/in/chlo%C3%A9-truchon-258a842a4/) & [Emmanuel Kone](https://www.linkedin.com/in/emmanuelkone/) |
| Gateway | [Adja Sokhna Fall](https://www.linkedin.com/in/adja-sokhna-fall-261a8b218/) & [Alireza Jafari](https://www.linkedin.com/in/alireza-jafari-polymtl/) |
| Communication (DNP3) | [Cazy Gaspard](https://www.linkedin.com/in/chrusley-cazy-920406332/) |
| Simulation (réseau + DER) | [Flavio Zapata](https://www.linkedin.com/in/flavio-zapata/) |

Membres : Chloé Truchon, Alireza Jafari, Cazy Gaspard, Flavio Zapata, Emmanuel Kone, Adja Sokhna Fall.

## Pour aller plus loin

<!-- Balises <a> : Doxygen lit ce fichier, mais pas les .md ciblés (voir INPUT dans le Doxyfile). -->
- <a href="derms/README.md">derms/README.md</a> : serveur DERMS, client DNP3 maître et simulation du réseau
- <a href="gateway/README.md">gateway/README.md</a> : passerelle DER, outstation DNP3 et modèles DER
- <a href="CONTRIBUTING.md">CONTRIBUTING.md</a> : standard de programmation, règles d'équipe et tutoriels
