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

**Lancer :** depuis la racine du dépôt, `python -m derms.main`. Ctrl+C arrête le serveur.
Dans Docker, avec les passerelles : `docker compose up --build` (image construite par
[Dockerfile](Dockerfile)).

Les décisions, les protocoles et les limites connues sont dans
[docs/serveur_derms.md](../docs/serveur_derms.md).

## Démarrage du serveur

`derms/main.py` lance FastAPI avec Uvicorn. `derms/serveur.py` démarre ensuite les modules dans
l'ordre suivant, et les arrête dans l'ordre inverse :

1. `configuration/`
2. `stockage/`
3. `initialisation/`
4. `dnp3_master/`
5. `simulation_pcc/`
6. `planification/`
7. `interface_ui/`

Pour l'instant, chaque module confirme seulement son démarrage. L'échec d'un module n'arrête pas le
serveur : le module passe à l'état `en_echec`, et les autres continuent de démarrer.

Le serveur ne fournit que des données JSON, sous `/api/`. `http://127.0.0.1:8000/api/sante` donne
l'état de chaque module, avec le statut global `ok` ou `degrade`.

`http://127.0.0.1:8000/` ouvre l'interface opérateur : des fichiers fixes (`interface_ui/static/`)
qui lisent l'API depuis le navigateur. L'état des modules est relu toutes les 2 s ; les DER sont
reçues en direct par un flux d'événements (voir [Partage des données entre
modules](#partage-des-données-entre-modules-état-central)).

Un module est pour l'instant un objet qui offre `name`, `async start()` et `async stop()`. Le contrat
définitif reste à choisir par l'équipe.

| Port | Protocole | Rôle |
|---|---|---|
| `8000` | HTTP | Interface Web du DERMS |

## Partage des données entre modules (état central)

Technique validée par l'équipe. Les modules du DERMS ne s'appellent pas entre eux : ils partagent
leurs données par un **état central**, l'objet `SystemState` de [live_data.py](live_data.py).

```
dnp3_master ──écrit──▶ ┌──────────────┐ ──lit──▶ planification
planification ─écrit─▶ │ SystemState  │ ──lit──▶ interface_ui ──flux SSE──▶ navigateur
                       └──────────────┘ ──avis──▶ abonnés (subscribe)
```

### Principe

- **Un seul objet**, créé une fois dans `main()`, puis donné aux modules et rangé dans
  `app.state.system_state` pour l'API. Personne ne crée son propre `SystemState`.
- Il garde les **dernières valeurs connues** (le présent). L'historique et ce qui doit survivre à
  un redémarrage relèvent de `stockage/`.
- Les fiches qu'il contient (`Der`, `Measurement`, `Alarm`) sont des `@dataclass(frozen=True)` :
  on ne les modifie pas, on en crée une copie avec `dataclasses.replace`, puis on la redonne à
  l'état central. Un module ne peut donc pas changer une valeur sans passer par lui.

### Utilisation

| Besoin | Méthode |
|---|---|
| Lire une DER | `state.der(der_id)` : la DER, ou `None` si elle n'existe pas |
| Lire toutes les DER | `state.ders()` : une copie de la liste |
| Ajouter ou remplacer une DER | `state.add_der(der)` : prévient aussi les abonnés |
| Être prévenu à chaque changement | `state.subscribe()` : une file `asyncio.Queue` à lire avec `await queue.get()` |
| Arrêter d'être prévenu | `state.unsubscribe(queue)` |

```python
der = state.der(1)
if der is not None and der.soc is not None:
    print(der.soc.value)  # lire

state.add_der(replace(der, desired_output_kw=20.0))  # modifier, puis prévenir les abonnés
```

Une valeur lue peut être `None` : la DER n'existe pas, ou aucune mesure n'est encore arrivée
(`der.soc`). Il faut le vérifier avant d'utiliser la valeur.

### Règles

1. **Seulement depuis la boucle asyncio.** Les écritures ne contiennent aucun `await` : elles
   s'exécutent d'un bloc, ce qui rend l'état central sûr sans verrou.
2. **Un thread n'écrit jamais directement.** Les rappels d'opendnp3 tournent dans leurs propres
   threads : ils confient l'écriture à la boucle avec
   `loop.call_soon_threadsafe(state.add_der, der)`.
3. **Un abonné se désabonne** quand il s'arrête (`try` / `finally`), sinon sa file reste dans la
   liste et se remplit pour rien. Une file pleine perd ses plus anciens avis
   (`SUBSCRIBER_QUEUE_SIZE`).
4. **Chaque donnée a un seul module écrivain.** La répartition (par exemple : `dnp3_master` écrit
   les mesures, `planification` les consignes) reste à fixer avec le contrat des modules.

### Affichage en direct

`interface_ui/` abonne chaque page ouverte à l'état central. La route
`/api/der/{der_id}/flux` (`stream_der`) envoie la DER dès l'ouverture, puis à chacun de ses
changements, en flux d'événements (SSE). Le navigateur la lit avec `EventSource`, qui se reconnecte
seul si le serveur redémarre. Quand la page se ferme, l'abonnement est retiré.

Les fichiers de l'interface sont envoyés avec `Cache-Control: no-cache` : le navigateur vérifie à
chaque chargement qu'il a la dernière version.

> **Démonstration temporaire** : au démarrage, `main.py` crée trois batteries d'exemple et fait
> varier le SOC de la batterie 1 entre 0 et 100 %, à 1 % par seconde. La page
> `http://127.0.0.1:8000/` le montre en direct. Ce code est à retirer avant la version finale.

> **TODO** : étendre l'état central aux autres données (puissance au PCC, consignes et leur
> statut, alarmes, état des liens DNP3) et fixer l'écrivain de chacune.

## Fonctionnement du serveur

Selon le [diagramme d'architecture](../assets/EDGECS_architecture.drawio), le serveur DERMS est un
hôte Linux. L'opérateur y accède par navigateur Web, en HTTP(S).

Pour le MVP, la simulation du réseau s'exécute à l'intérieur du serveur, dans `simulation_pcc/`.

Échanges logiciels internes, qui passent par l'état central (voir plus haut) :

- `configuration/` alimente `initialisation/`.
- `initialisation/` et `interface_ui/` alimentent `planification/`.
- `planification/` échange avec `stockage/`.
- `planification/` échange les commandes et les télémesures avec `dnp3_master/`.

## Client DNP3 maître

Le module `dnp3_master/` est la station maîtresse : il envoie les consignes aux passerelles et lit
leurs mesures, en DNP3 sur TCP/IP (IEEE 1815, profil DER IEEE 1815.2).

L'interface Web est configurée dans `derms/main.py` :

| Constante | Valeur | Rôle |
|---|---|---|
| `WEB_ADDRESS` | `127.0.0.1` | Adresse d'écoute de l'interface Web |
| `WEB_PORT` | `8000` | Port de l'interface Web |

La variable d'environnement `EDGECS_WEB_ADDRESS` remplace `WEB_ADDRESS` quand elle est définie ;
`derms/Dockerfile` la règle à `0.0.0.0`.

Pour l'instant, `dnp3_master/` confirme seulement son démarrage : aucune liaison DNP3 n'est établie.
L'adresse et le port de la passerelle seront ajoutés avec le client DNP3, sur le même modèle.

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
