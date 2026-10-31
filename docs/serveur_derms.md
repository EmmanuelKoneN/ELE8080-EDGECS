# Serveur DERMS : fonctionnement, protocoles et décisions

État au 2026-10-30, sur la branche `feature/derms-server-core`. Les identifiants comme `PF-113`
renvoient au Tableau 8.1 du cahier des charges, qui n'est pas dans le dépôt.

## 1. Où on en est

`python -m derms.main` lance un serveur Web qui démarre les 7 modules du DERMS et reste actif
jusqu'à Ctrl+C. **Les modules sont encore vides** : ils confirment seulement leur démarrage.

| Fait | Pas encore fait |
|---|---|
| Serveur Web actif en continu | Logique réelle des modules |
| Démarrage et arrêt ordonnés des 7 modules | Liaison DNP3 avec les passerelles |
| Suivi de l'état de chaque module | Lecture d'un fichier de configuration |
| Page d'état `/sante` et API `/api/sante` | Stockage et journal des événements sur disque |

Restent à décider en équipe : le contrat des modules et la bibliothèque DNP3 (section 5).

## 2. Lancer et vérifier

L'installation complète est dans la section « Installation de zéro » de `CONTRIBUTING.md`.
Ensuite, depuis la racine du dépôt, dans Ubuntu :

```bash
source .venv/bin/activate
python -m derms.main
```

| Adresse | Contenu |
|---|---|
| `http://127.0.0.1:8000/sante` | Page lisible : nombre de modules démarrés et état de chacun |
| `http://127.0.0.1:8000/api/sante` | Même information en JSON, pour les scripts et les essais |

Ctrl+C arrête le serveur. La réponse HTTP est 200 même si un module est en échec : le statut se lit
dans le contenu (`ok` ou `degrade`).

## 3. Fonctionnement

### Vue d'ensemble

```
Navigateur ──HTTP──▶ Uvicorn ──ASGI──▶ FastAPI ──▶ ModuleSupervisor
                                                     │ start() / stop()
             ┌───────────┬──────────────┬────────────┼──────────────┬───────────────┬───────────┐
       configuration  stockage  initialisation  dnp3_master  simulation_pcc  planification  interface_ui
```

Tout tourne dans **un seul processus Python**, autour d'une boucle `asyncio`.

| Fichier | Rôle |
|---|---|
| `derms/main.py` | Point d'entrée : configure le journal et lance Uvicorn |
| `derms/serveur.py` | Application FastAPI, superviseur des modules, liste des modules |
| `derms/etat_module.py` | États possibles d'un module |
| `derms/interface_ui/page_sante.py` | Construction de la page `/sante` |
| `derms/<module>/module_<module>.py` | Classe de chaque module |

### Démarrage et arrêt

1. `main()` configure le journal, crée les modules et l'application, puis lance Uvicorn.
2. Au démarrage, FastAPI appelle `lifespan`, qui demande au superviseur de démarrer les modules.
3. Le superviseur les démarre un à la fois, dans l'ordre de `create_modules()` :
   `configuration`, `stockage`, `initialisation`, `dnp3_master`, `simulation_pcc`, `planification`,
   `interface_ui`.
4. Le serveur répond ensuite aux requêtes Web jusqu'à Ctrl+C.
5. À l'arrêt, seuls les modules à l'état `demarre` sont arrêtés, dans l'ordre inverse.

Cet ordre suit les échanges internes : la configuration alimente l'initialisation, et la
planification utilise les modules précédents. Il pourra changer avec le vrai code.

### États d'un module

| État | Sens |
|---|---|
| `non_demarre` | Le module n'a pas encore été démarré |
| `demarre` | `start()` s'est terminé sans erreur |
| `en_echec` | `start()` ou `stop()` a levé une exception |
| `arrete` | `stop()` s'est terminé sans erreur |

L'état est tenu par le superviseur, pas par les modules. Chaque changement est écrit dans le journal
avec son horodatage.

### Si un module échoue

Pour l'instant, **aucun module n'arrête le serveur**. Une exception pendant `start()` fait passer le
module à `en_echec`, écrit l'erreur au journal, et les modules suivants démarrent quand même. Une
exception pendant `stop()` n'empêche pas l'arrêt des autres modules. La page `/sante` reste
accessible et signale l'échec, comme le demande PF-113.

## 4. Protocoles

| Liaison | Protocole | État | Détails |
|---|---|---|---|
| Navigateur → serveur | HTTP | En place | Port 8000, sans chiffrement, sur `127.0.0.1` seulement |
| Uvicorn → FastAPI | ASGI | En place | Interface Python interne, pas un protocole réseau |
| Scripts → serveur | HTTP + JSON | En place | `/api/sante` |
| Entre modules | Appels Python | Prévu | Aucun protocole réseau : même processus, sans échange pour l'instant |
| Simulation → planification | Appels Python | Prévu | La simulation est dans le serveur pour le MVP |
| DERMS → passerelles | DNP3 sur TCP/IP | Non implémenté | Exigé par PH-142. Bibliothèque à choisir |

**Port ouvert par le serveur (G-012) :** 8000. Aucun port DNP3 n'est utilisé pour l'instant.
`GATEWAY_ADDRESS` et `GATEWAY_PORT` restent dans `derms/main.py`, mais rien ne les lit encore.

## 5. Décisions

### Prises

| Décision | Pourquoi | Options écartées |
|---|---|---|
| **Serveur : FastAPI + Uvicorn** | Étape officielle de démarrage et d'arrêt pour lancer les modules ; prépare l'interface Web (PH-131) | Flask + Waitress : démarrage, arrêt et threads à écrire soi-même. Python seul : pas de Web |
| **Exécution : un processus, asyncio et threads aux frontières** | Voir l'étude ci-dessous | asyncio pur, threads seuls, plusieurs processus |
| **Simulation du réseau dans le serveur pour le MVP** | Plus simple pour le MVP, cohérent avec `derms/simulation_pcc/` | Bloc externe, comme dans la figure 7.2 du cahier des charges |
| **Aucun module n'arrête le serveur pour l'instant** | Le Web doit rester accessible en cas de panne (PF-113) ; suffisant tant que les modules sont vides | Arrêt complet au premier échec |
| **Aucune infrastructure DNP3 pour l'instant** | Le choix se fera avec le volet Communication | Intégrer une bibliothèque dès le squelette |
| **Modules neutres, sans classe de base** | Laisse le choix du contrat à l'équipe | Imposer ABC ou Protocol dès maintenant |
| **Page `/sante` lisible, JSON sur `/api/sante`** | Le JSON brut était difficile à lire ; la page n'utilise aucune ressource externe (G-002) | JSON seul |
| **Cible : hôte Linux, MVP sur PC** | PH-141. Le Raspberry Pi n'est plus considéré pour l'instant | Déploiement sur Raspberry Pi |
| **Développement dans Ubuntu avec WSL2** | Même type de système que la cible, sans machine dédiée ; `dnp3-python` n'existe que pour Linux | Rester sous Windows jusqu'au DNP3 ; machine virtuelle complète ; double démarrage |
| **Dépôt cloné dans le dossier Linux, une seule copie de travail** | Accès aux fichiers plus rapides qu'avec `/mnt/c/` ; évite de mélanger les modifications | Copie sur le disque Windows |
| **Python 3.11 installé par `uv` dans `.venv`** | Même version que la CI, sans toucher au Python d'Ubuntu (3.12) | Python d'Ubuntu ; installation dans le système |
| **VS Code reste sous Windows, avec l'extension WSL** | Une seule fenêtre, connectée à Ubuntu | Interface graphique Linux ; deux fenêtres, une par système |
| **Docker pour l'application réceptrice seulement** | La proposition d'Eaton n'exige la conteneurisation que côté périphérie | Conteneuriser aussi le DERMS, ce qui reste possible plus tard pour G-014 |

Le README principal mentionne encore les Raspberry Pi pour la version finale. Il sera à ajuster si
cet abandon est confirmé.

### Étude du modèle d'exécution

Les délais du cahier des charges se comptent en dizaines de secondes (G-004, G-005, F-104) : la
vitesse ne départage pas les options. Le critère principal est la robustesse.

| Critère | A. asyncio pur | **B. asyncio + threads (retenu)** | C. Threads | D. Plusieurs processus |
|---|---|---|---|---|
| Compatible avec opendnp3 | Non, à cause de ses threads | Oui | Oui | Oui |
| Web actif en cas de panne (PF-113) | Fragile | Oui pour les erreurs Python | Oui pour les erreurs Python | Le plus solide |
| DER ajoutée sans redémarrage (F-121, F-122) | Simple | Simple | Verrous nécessaires | Synchronisation à prévoir |
| Aucune commande à l'arrêt (G-009) | Simple | Un seul chemin d'arrêt | À coordonner | À coordonner |
| Installation sur machine vierge (G-014) | Simple | Simple | Simple | Plus lourde |

**Limite de B :** un plantage natif dans du code C++, comme une bibliothèque DNP3, tuerait tout le
processus, Web compris. Python ne peut pas intercepter ce type de plantage. Le client DNP3 doit donc
rester derrière une interface étroite. Si l'essai montre que le risque est réel, ce module seul
pourra passer dans un processus séparé.

La compatibilité avec opendnp3 est une déduction : ses exemples créent un gestionnaire à threads,
mais le modèle exact reste à confirmer par un essai.

### À décider

| Sujet | Options | Ce qu'il faut savoir | Qui |
|---|---|---|---|
| **Contrat des modules** (PH-143) | ABC ou Protocol | ABC partage le code commun ; Protocol ne décrit que les méthodes. `start` et `stop` seront `async`. Il faudra aussi prévoir les dépendances entre modules | Équipe |
| **Bibliothèque DNP3** | `dnp3-python` ou `yadnp3`, toutes deux basées sur opendnp3 | Voir le tableau ci-dessous | Volet Communication et DERMS |
| **Configuration illisible** | Arrêter le serveur ou continuer | À revoir quand le module lira un vrai fichier, car le serveur y lira son port | Volet DERMS |
| **Stockage** (F-146) | SQLite, PostgreSQL/Redis (cités au WBS) ou autre | Un service séparé complique l'installation sur machine vierge (G-014) | Volet DERMS |

opendnp3 est la pile C++. On l'utilise depuis Python par une couche de liaison, donc le vrai choix
porte sur cette couche. État vérifié le 2026-10-30 sur les pages PyPI et GitHub :

| Bibliothèque | État | Point d'attention |
|---|---|---|
| [opendnp3](https://github.com/dnp3/opendnp3) | Archivé depuis le 2022-09-01 | Plus maintenu ; pas utilisable directement en Python |
| [dnp3-python](https://pypi.org/project/dnp3-python/) | Pré-version 0.3.0b2, novembre 2024 | Wheels pour Python 3.8 à 3.10 et Linux x86-64 seulement, alors que le projet vise 3.11 |
| [yadnp3](https://pypi.org/project/yadnp3/) | Version 3.2.1.4, octobre 2026, bêta | Python 3.9 à 3.14, Linux x86-64 et Windows ; fork expérimental, un seul mainteneur ; maître et outstation à confirmer |

Essai proposé sur une branche `poc/` : échanger une mesure et une consigne, puis couper le réseau et
vérifier la reconnexion en moins de 60 s (G-008).

## 6. Compléter un module

Le code de chaque volet va dans `derms/<module>/module_<module>.py`. Pour l'instant, un module offre
`name`, `async start()` et `async stop()`.

- **Une erreur au démarrage :** laisser l'exception sortir de `start()`, le superviseur la traite.
- **Une tâche continue :** la lancer dans `start()` avec `asyncio.create_task()`, puis l'annuler dans
  `stop()`. `start()` doit rendre la main, sinon le serveur reste bloqué au démarrage.
- **Du code bloquant ou un calcul long :** utiliser `asyncio.to_thread()`, sinon il bloque tout le
  serveur, y compris le Web.
- **Un appel venant d'un thread d'une bibliothèque :** revenir à la boucle avec
  `loop.call_soon_threadsafe()` avant de toucher aux données partagées.
- **Pas d'import de `gateway/` :** le DERMS et la passerelle ne communiquent que par DNP3.

## 7. Limites connues

| Limite | Exigence touchée | À faire |
|---|---|---|
| Adresse et port Web sont des constantes dans `derms/main.py` | G-003 | Les lire dans un fichier de configuration |
| Le Web écoute seulement sur `127.0.0.1` | PH-131 | Écouter sur le réseau local quand l'opérateur sera sur un autre poste |
| Le Web ne répond qu'après le démarrage de tous les modules | PF-113, PF-124, PF-125 | Lancer les connexions DNP3 en arrière-plan : une passerelle lente ne doit pas bloquer le Web |
| L'état d'une DER n'existe pas encore | F-123, PF-125, S-126 | Ajouter son état, distinct de celui d'un module : une passerelle hors ligne n'est pas une panne du module DNP3 |
| Un module en échec ne bloque pas ceux qui en dépendent | G-009, G-011 | Bloquer l'envoi de commandes si une dépendance manque |
| Journal affiché dans le terminal seulement | G-013, F-146 | L'écrire dans le stockage local |
| Un plantage natif tuerait tout le processus | PF-113 | Vérifier avec l'essai DNP3 |
| La simulation est dans le serveur, contrairement à la figure 7.2 | F-107 | Documenter cet écart dans le cahier de conception |
| Les pages automatiques de FastAPI (`/docs`, `/redoc`) chargent leurs fichiers depuis Internet | G-002 | Les désactiver ou fournir ces fichiers localement |
| La liste des modules est typée `Any` | Standard de programmation | Remplacer `Any` après le choix du contrat |

## 8. Vérifications

Essais manuels du 2026-10-30, d'abord sous Windows avec Python 3.14, puis sous Ubuntu 24.04 (WSL2)
avec Python 3.11.18. Aucun test automatisé n'existe encore, car le projet n'a pas de framework de
test.

| Essai | Résultat |
|---|---|
| Démarrage réel : 7 modules, `/api/sante` à `ok`, `/sante` à 7 sur 7 | Réussi sous Windows et Ubuntu |
| Arrêt : les 7 modules s'arrêtent, code de sortie 0 sous Ubuntu | Réussi, y compris par Ctrl+C au clavier sous Windows |
| Installation de `requirements.txt` et `requirements-dev.txt` | Réussie sous Ubuntu |
| Module qui plante au démarrage : `en_echec`, les autres démarrent, statut `degrade` | Réussi sous Windows |
| Module qui plante à l'arrêt : `en_echec`, les autres s'arrêtent | Réussi sous Windows |
| Contenu de `/sante`, avec et sans module en panne | Réussi sous Windows |
| `ruff format` et `ruff check` | Réussi sous Ubuntu |
| `doxygen Doxyfile` : `doxygen/avertissements.txt` vide | Réussi avec Doxygen 1.18 |

| Non vérifié | Raison |
|---|---|
| Doxygen de la CI | La version de la CI peut différer de la 1.18 ; à confirmer avec une pull request |
| Injection de pannes sous Ubuntu | Faite sous Windows seulement |
| Serveur sur un hôte Linux dédié | WSL2 sert au développement ; PH-141 reste à démontrer sur l'hôte final |
