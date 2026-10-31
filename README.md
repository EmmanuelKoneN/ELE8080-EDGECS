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

- **Python 3.11** (langage principal), avec un environnement virtuel géré par **uv**
- **FastAPI + Uvicorn** pour le serveur Web du DERMS
- **WSL2 + Ubuntu 24.04** comme environnement Linux de développement sous Windows
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
| `docs/` | Documentation de conception, dont le fonctionnement du serveur DERMS et ses décisions |
| `assets/` | Diagramme d'architecture |
| `requirements.txt` | Dépendances Python |
| `requirements-dev.txt` | Outils de développement et d'analyse |
| `CONTRIBUTING.md` | Standard de programmation, règles d'équipe, outils et tutoriels |

## Installation de zéro

L'équipe développe sous **Linux**, dans Ubuntu avec WSL2 : le client exige un serveur Linux, et une
bibliothèque DNP3 envisagée n'existe que pour Linux. WSL2 fait tourner Ubuntu dans Windows, sans
double démarrage. VS Code reste installé sous Windows, mais le code, le terminal et Python sont
dans Ubuntu.

Il faut Windows 10 ou 11, [VS Code](https://code.visualstudio.com/) et
[Git pour Windows](https://git-scm.com/download/win).

### 1. Installer Ubuntu

Dans PowerShell, ouvert avec **Exécuter en tant qu'administrateur** :

```powershell
wsl --install
```

Redémarrez si on vous le demande, puis ouvrez **Ubuntu** depuis le menu Démarrer et créez votre
utilisateur Linux. L'erreur `ERROR_ALREADY_EXISTS` veut dire qu'Ubuntu est déjà installé :
`wsl --list --verbose` doit l'afficher en version 2.

### 2. Préparer VS Code

Dans VS Code, installez l'extension **WSL** de Microsoft (Ctrl+Maj+X).

### 3. Cloner le dépôt dans Ubuntu

Dans le terminal Ubuntu, en remplaçant le nom et le courriel :

```bash
git config --global user.name "Prénom Nom"
git config --global user.email "votre@courriel"
git config --global credential.helper "/mnt/c/Program\ Files/Git/mingw64/bin/git-credential-manager.exe"

cd ~
git clone https://github.com/EmmanuelKoneN/ELE8080-EDGECS.git
cd ELE8080-EDGECS
```

La troisième ligne réutilise la connexion GitHub de Windows. Le dépôt doit rester dans votre dossier
Linux (`~/`), pas dans `/mnt/c/` : les accès aux fichiers Windows depuis Ubuntu sont plus lents.

### 4. Installer Python 3.11 et les dépendances

La CI utilise Python 3.11, qu'Ubuntu ne fournit pas forcément. `uv` l'installe dans un environnement
propre au projet (`.venv/`), sans toucher au Python du système :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt
```

`python --version` doit afficher `3.11.x`, et `(.venv)` doit apparaître au début de la ligne de
commande.

### 5. Ouvrir le projet dans VS Code

```bash
code .
```

**WSL: Ubuntu** doit s'afficher en bas à gauche de VS Code. Installez ensuite les extensions
recommandées dans WSL : dans le panneau Extensions, cliquez sur **Install in WSL: Ubuntu** pour
chacune. Le projet utilise `.venv` par défaut ; sinon, choisissez-le avec Ctrl+Maj+P, puis
**Python: Select Interpreter**.

### 6. Vérifier l'installation

Dans le terminal de VS Code :

```bash
python -m derms.main
```

Ouvrez `http://127.0.0.1:8000/sante` dans votre navigateur : la page doit afficher
**7 modules démarrés sur 7**. Ctrl+C arrête le serveur.

Vérifiez aussi votre connexion GitHub avec `git push` depuis une branche de travail : le résultat
attendu est `Everything up-to-date`. Une fenêtre de connexion peut s'ouvrir la première fois.

### Outils facultatifs

- **Doxygen** : `sudo apt install doxygen`, pour vérifier la documentation avant une pull request.
- **Docker** : pour la passerelle, activez Ubuntu dans Docker Desktop, sous
  **Settings → Resources → WSL Integration**.

## Travailler au quotidien

1. Ouvrez VS Code, puis **File → Open Recent** et `ELE8080-EDGECS [WSL: Ubuntu]`. Il n'est pas
   nécessaire d'ouvrir Ubuntu à part.
2. Vérifiez que **WSL: Ubuntu** s'affiche en bas à gauche, et n'utilisez que cette fenêtre.
3. Lancez les programmes depuis le terminal de VS Code, à la racine du dépôt :

```bash
source .venv/bin/activate    # si (.venv) n'apparaît pas

# Terminal 1 : la passerelle (port 20000 par défaut)
python -m gateway.main

# Terminal 2 : le serveur DERMS, actif jusqu'à Ctrl+C
python -m derms.main
```

Pour une 2e ou 3e passerelle : `python -m gateway.main 20001`, `python -m gateway.main 20002`.
La configuration **DERMS** de « Exécuter et déboguer » (F5) fonctionne aussi. N'utilisez pas le
bouton ▶ : il lance le fichier seul, et Python ne trouve plus le paquet `derms`.

Le projet est au stade de l'échafaudage : la passerelle affiche seulement « à implémenter », et les
modules du DERMS confirment seulement leur démarrage. Aucun échange DNP3 n'a encore lieu.

| Problème | Solution |
|---|---|
| `No module named 'derms'` | Lancez `python -m derms.main` depuis la racine, pas le bouton ▶ |
| `(.venv)` n'apparaît pas | `source .venv/bin/activate` |
| `uv` est introuvable | `source ~/.local/bin/env`, ou fermez et rouvrez le terminal |
| `WSL: Ubuntu` n'apparaît pas | Vous êtes dans une fenêtre Windows : rouvrez le projet avec **Open Recent** |
| VS Code propose d'enregistrer le workspace | Répondez **Don't Save** : ce fichier n'est pas utile ici |

## Principaux choix

| Choix | Raison |
|---|---|
| Linux via WSL2 pour le développement | Le serveur et la passerelle visent Linux, et cela évite les écarts entre Windows et la cible |
| Python 3.11 | Même version que la CI |
| FastAPI + Uvicorn | Serveur Web prêt pour l'interface, avec une étape de démarrage et d'arrêt pour les modules |
| Un processus, `asyncio` et threads aux frontières | Simple à déboguer, et compatible avec une bibliothèque DNP3 à threads |
| Simulation du réseau dans le serveur pour le MVP | Plus simple tant que le MVP tourne sur un PC |
| Docker pour l'application réceptrice seulement | Seul le côté périphérie doit être conteneurisé |

Le détail, les options écartées, les sujets encore à décider et les limites connues sont dans
<a href="docs/serveur_derms.md">docs/serveur_derms.md</a>.

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
- <a href="docs/serveur_derms.md">docs/serveur_derms.md</a> : fonctionnement du serveur DERMS, protocoles et décisions
- <a href="gateway/README.md">gateway/README.md</a> : passerelle DER, outstation DNP3 et modèles DER
- <a href="CONTRIBUTING.md">CONTRIBUTING.md</a> : standard de programmation, règles d'équipe et tutoriels
