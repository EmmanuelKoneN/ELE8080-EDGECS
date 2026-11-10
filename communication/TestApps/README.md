# Applications graphiques de test EDGECS

Deux applications Python supervisent les moteurs C++ existants :

- `master_app.py` démarre `edgecs_master`, découvre les DER enregistrées et propose leurs commandes et leurs mesures.
- `der_app.py` charge un JSON, démarre une Gateway et son simulateur, et affiche l'état interne de cette simulation.

Ces interfaces sont destinées aux essais de laboratoire sur des ressources simulées. Les communications DNP3 restent assurées par OpenDNP3 en C++. Le mode terminal du simulateur reste utilisable.

```text
Master App ── HTTPS / MQTT ── DERMS Master C++
                                    │
                                 DNP3/TCP
                                    │
DER App ── supervision ── Gateway / Outstation C++
   │                                │
   │                               MQTT
   │                                │
   └──── stdin / événements ── Simulateur DER C++
```

Mosquitto est partagé entre les applications. Le mode implémenté est **le broker externe (mode A)** : les interfaces s'y connectent et ne le démarrent ni ne l'arrêtent. Le mode B, broker géré par la Master App, reste facultatif et n'est pas implémenté.

## Installation Ubuntu / WSL2

Exécuter les commandes depuis la racine `EDGECS`. Un bureau Linux ou WSLg est nécessaire pour afficher les fenêtres. Les vérifications automatiques peuvent utiliser Qt en mode `offscreen`.

Installer les dépendances système adaptées à l'environnement Ubuntu :

```bash
sudo apt update
sudo apt install python3 python3-venv mosquitto mosquitto-clients openssl \
  build-essential cmake pkg-config libpaho-mqttpp-dev \
  libcurl4-openssl-dev nlohmann-json3-dev libssl-dev \
  libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0
```

OpenDNP3 3.1.2 et Drogon avec HTTPS sont également nécessaires à la compilation native. Ce workspace possède déjà `opendnp3-install` et `drogon-ssl-install`. Pour une installation différente, adapter `CMAKE_PREFIX_PATH` aux bibliothèques existantes ; consulter aussi les [instructions DERMS](../DERMS/README.md) et [Gateway](../Gateway/README.md).

Les dépendances Python sont isolées dans un environnement virtuel :

```bash
python3 -m venv TestApps/.venv
TestApps/.venv/bin/python -m pip install -r TestApps/requirements.txt
```

PySide6 fournit Qt et Paho assure la connexion MQTT de supervision. Les interfaces Python ne chargent aucune bibliothèque DNP3.

Compiler les exécutables :

```bash
cmake -S Gateway -B Gateway/build -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install"
cmake --build Gateway/build -j2

cmake -S DERMS -B DERMS/build -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install;$PWD/drogon-ssl-install"
cmake --build DERMS/build -j2
```

Les exécutables utilisés sont `DERMS/build/edgecs_master`, `Gateway/build/edgecs_gateway` et `Gateway/build/edgecs_bess_sim`. Ce dernier est générique malgré son nom historique ; `edgecs_der_sim` est construit depuis la même source.

La recherche automatique examine les dossiers `build` habituels des projets, les dossiers `build-*`, leurs variantes `Release` / `Debug`, puis le `PATH`. Pour un autre emplacement :

```bash
export EDGECS_MASTER_BIN=/chemin/vers/edgecs_master
export EDGECS_GATEWAY_BIN=/chemin/vers/edgecs_gateway
export EDGECS_SIMULATOR_BIN=/chemin/vers/edgecs_bess_sim
```

## Premier lancement local

1. Démarrer un broker externe, par exemple avec `sudo service mosquitto start`. Cette commande est exécutée explicitement par l'utilisateur ; aucune demande `sudo` n'est cachée dans les interfaces.
2. Lancer `TestApps/.venv/bin/python TestApps/master_app.py`.
3. Conserver `127.0.0.1`, HTTPS `8443` et MQTT `127.0.0.1:1883` pour un essai local.
4. Cliquer sur **Créer / charger les accès locaux du laboratoire**. Le bouton prépare un jeton aléatoire et les fichiers TLS locaux.
5. Cliquer sur **Démarrer le Master**. Le tableau doit rester utilisable avec zéro DER enregistrée.
6. Lancer `TestApps/.venv/bin/python TestApps/der_app.py` dans une autre instance. Les accès locaux sont chargés automatiquement.
7. Cliquer sur **Parcourir…**, choisir `Gateway/config/outstation_config.json`, vérifier les paramètres et cliquer sur **Démarrer la DER**.
8. Attendre l'enregistrement HTTPS, l'ouverture du canal DNP3, puis le démarrage et l'abonnement MQTT du simulateur.
9. Dans le Master, sélectionner la DER, envoyer une commande, puis cliquer sur **Lire les mesures** pour acquérir le retour DNP3.

Avec un environnement virtuel activé, les commandes demandées sont directement utilisables :

```bash
source TestApps/.venv/bin/activate
python3 TestApps/master_app.py
python3 TestApps/der_app.py
```

On peut aussi présélectionner un fichier sans figer son chemin dans le code :

```bash
TestApps/.venv/bin/python TestApps/der_app.py /chemin/absolu/ma_configuration.json
```

Le bouton **Arrêter la DER** et la fermeture de sa fenêtre arrêtent uniquement la Gateway et le simulateur créés par cette instance. Le Master et les autres DER continuent à fonctionner. Fermer la Master App arrête son propre serveur C++ ; les DER peuvent alors signaler la perte de communication.

## TLS et authentification

La préparation locale crée `TestApps/.local/`, un dossier privé ignoré par Git, contenant :

| Fichier | Usage |
|---|---|
| `lab.json` | Jeton partagé et chemins des fichiers TLS |
| `server.crt` | Certificat auto-signé du Master, utilisé comme ancre de confiance locale |
| `server.key` | Clé privée du serveur |

Le certificat est valable **30 jours à sa création**. Ses SAN incluent `localhost`, `127.0.0.1` et l'IPv4 choisie lors de la préparation. La clé et le manifeste contenant le jeton sont créés avec des permissions privées. Une préparation ultérieure charge les accès existants ; elle ne remplace pas silencieusement le certificat de confiance et ne prolonge pas sa validité.

La même préparation peut être faite sans Qt :

```bash
TestApps/.venv/bin/python TestApps/setup_lab.py --host 127.0.0.1
```

Après expiration ou changement d'adresse du Master, arrêter les applications, renouveler explicitement les accès et distribuer le nouveau certificat de confiance aux DER concernées. Vérifier les fichiers existants avant de les remplacer.

Pour fournir ses propres accès, renseigner les champs TLS ou les variables d'environnement **avant le lancement** :

```bash
export EDGECS_REGISTRATION_TOKEN='<jeton partagé de 16 caractères minimum>'
export EDGECS_TLS_CERT=/chemin/absolu/master.crt
export EDGECS_TLS_KEY=/chemin/absolu/master.key
export EDGECS_CA_CERT=/chemin/absolu/autorite.crt
```

Ces variables priment sur les paramètres locaux enregistrés. Le Master utilise le certificat serveur et sa clé ; la DER n'a besoin que du jeton et du certificat de l'autorité de confiance. La clé privée du Master reste sur sa machine.

Pour plusieurs machines, utiliser des IPv4 privées joignables. Le certificat du Master doit contenir **l'adresse réellement utilisée par les DER dans un SAN de type IP**. Distribuer le certificat public de confiance et le jeton par un moyen adapté. Les vérifications de certificat et d'adresse restent actives dans Python et dans la Gateway ; aucun mode TLS non vérifié n'est ajouté.

Les champs **IPv4 Master DERMS** et **IPv4 Gateway** sont distincts. L'adresse Gateway sert ici à l'écoute locale et à l'annonce au Master : elle doit appartenir à la machine qui exécute cette DER App et être joignable depuis le Master. La traduction d'adresse NAT n'est pas automatisée. Sous WSL2, choisir les adresses selon le mode réseau utilisé et vérifier les accès entre machines.

Si le broker exige un identifiant et un mot de passe, les variables existantes `MQTT_USERNAME` et `MQTT_PASSWORD` sont reprises par les clients Python et C++. Le transport MQTT conserve le fonctionnement du prototype existant.

## Plusieurs DER simultanées

Ouvrir une nouvelle instance de `der_app.py` pour chaque DER. Les configurations fournies proposent :

| Configuration | `device_id` | Gateway DNP3 | Adresse Master | Adresse Outstation |
|---|---|---|---|---|
| `Gateway/config/outstation_config.json` | `bess-01` | `127.0.0.1:20000` | 1 | 10 |
| `Gateway/config/generator_config.json` | `generator-01` | `127.0.0.1:20002` | 1 | 11 |

Les deux ressources peuvent partager le broker `127.0.0.1:1883` et le Master HTTPS `127.0.0.1:8443`. Les adresses logiques et indices de points proviennent de chaque JSON. Un même indice peut être utilisé dans plusieurs Outstations : leurs sessions DNP3 restent indépendantes.

Avant de lancer les moteurs, la DER App vérifie les ports, la connexion HTTPS, le registre Master et la disponibilité de son identité. Un verrou local, propre à l'utilisateur et à la combinaison broker/port/`device_id`, empêche deux DER App locales d'utiliser la même identité MQTT. Le registre complète ce contrôle pour les ressources connues du Master. Les erreurs de doublon et de port occupé sont affichées dans la fenêtre.

Le Master garde les enregistrements après l'arrêt d'une Gateway. Un redémarrage à configuration identique est possible lorsque son ancien canal n'est plus ouvert. Une modification du mapping d'une identité déjà enregistrée, ou la réutilisation d'un endpoint conservé pour une autre identité, nécessite de redémarrer le Master. Un registre conservé n'est pas une preuve de connexion active.

Les précontrôles ne réservent pas les ports jusqu'à leur utilisation par les processus : un autre programme peut encore occuper un port pendant le démarrage. Les erreurs natives et les sorties prématurées sont alors rapportées dans le journal.

La DER App produit une copie temporaire validée du JSON avec les substitutions réseau. Elle transmet **la même copie** à la Gateway et au simulateur, puis la supprime après leur arrêt. Le fichier sélectionné n'est jamais modifié. Les identifiants MQTT des interfaces sont uniques ; les identifiants des moteurs C++ restent séparés par `device_id`.

## Ce que signifient les états affichés

| État | Signification |
|---|---|
| DER enregistrée | Le Master a accepté une configuration HTTPS authentifiée. |
| Canal DNP3 `open` | Le canal TCP de la session OpenDNP3 est ouvert. Cela ne confirme pas une exécution physique. |
| Dernière mesure reçue | Dernière valeur acquise par le Master, avec son horodatage de réception. Elle peut être ancienne. |
| MQTT interface prêt | La connexion MQTT Python et les abonnements ont été confirmés. |
| MQTT moteur connecté | Le client MQTT du Master C++ annonce une connexion active. |
| MQTT simulateur prêt | Le simulateur C++ a confirmé sa connexion et son abonnement aux commandes. |
| `accepted_by_outstation` | DNP3 a accepté la commande dans l'Outstation. |
| `accepted_by_simulator` | Le simulateur a validé la commande reçue ; un éventuel retour est un écho simulé. |

L'interface distingue l'envoi, le résultat DNP3, les erreurs ou délais expirés, puis la réception d'une mesure après lecture. L'écho `feedback_point` n'est pas un modèle physique de batterie ou de génératrice.

**Lire les mesures** publie une demande explicite de lecture Class 0. L'interrogation régulière du registre HTTPS met à jour la supervision ; elle ne déclenche aucun scan DNP3 périodique. Le scan automatique de trois secondes n'est pas réintroduit.

Dans la DER App, **Actualiser l'état interne du simulateur** demande un instantané IPC local. Ce bouton n'effectue aucune lecture DNP3. **Modifier** envoie une valeur au simulateur C++, attend sa confirmation, puis le simulateur publie sa télémesure habituelle vers la Gateway. Le GUI ne publie pas de mesures à sa place.

## Contrats de communication

### HTTPS

Les points d'accès existants sont réutilisés :

| Méthode et chemin | Usage |
|---|---|
| `GET /health` | Disponibilité HTTPS et booléen `mqtt_connected` du moteur C++ ; sans jeton. |
| `GET /api/v1/outstations` | Registre dynamique, capacités, état du canal et dernières valeurs ; authentifié. |
| `GET /api/v1/outstations/{device_id}` | Détail d'une DER ; authentifié. |
| `GET /api/v1/outstations/{device_id}/telemetry` | Instantané des dernières acquisitions ; authentifié. |
| `POST /api/v1/outstations/register` | Enregistrement effectué par la Gateway C++ ; authentifié. |

Les appels authentifiés portent `Authorization: Bearer <jeton>`. Les interfaces n'enregistrent pas elles-mêmes une fausse Gateway. Aucun secret TLS n'est ajouté aux descripteurs de découverte.

### MQTT

Toutes les commandes et demandes de lecture ont une enveloppe compatible avec `edgecs::envelope()` :

```json
{
  "schema_version": 1,
  "device_id": "bess-01",
  "point": "power_setpoint_kw",
  "value": 30.0,
  "kind": "command",
  "request_id": "28f46776-b5c7-4b82-b83a-d393faad8616",
  "timestamp": "2026-11-09T14:32:11.123+00:00"
}
```

Les noms et indices de cet exemple ne servent pas de tables de dispatch dans le GUI : les contrôles AO/BO et AI/BI sont créés depuis `points`. Les valeurs AO sont bornées par `min` / `max` ; les points binaires utilisent des booléens JSON stricts. Le C++ valide également les valeurs reçues.

| Topic `edgecs/{device_id}/…` | Producteur → consommateur |
|---|---|
| `command` | Master App → Master C++ → commande DNP3 |
| `command_result` | Master C++ → Master App ; `accepted_by_outstation`, `rejected_by_dnp3` ou `rejected_by_master` |
| `read` | Master App → Master C++ ; `kind: "read"`, `point: "*"`, `value: null` |
| `read_result` | Master C++ → interface ; `scan_requested`, puis `read_completed` ou `read_failed` |
| `telemetry` | Master C++ → interface ; données acquises via DNP3 |
| `edge/command` | Gateway C++ → simulateur C++ |
| `edge/telemetry` | Simulateur C++ → Gateway C++ |

Les publications des interfaces utilisent QoS 1, sans message retenu. `request_id` sert à associer les résultats à leur demande. Les conversions de commandes en DNP3 restent entièrement dans les moteurs C++.

### IPC privé du simulateur

Le seul mode C++ ajouté pour l'intégration graphique est optionnel :

```bash
Gateway/build/edgecs_bess_sim /chemin/configuration.json --gui
```

Sans `--gui`, les commandes console `list`, `status`, `set`, les alias, `send` et `quit` conservent leur usage. En mode GUI, stdin reçoit un objet JSON par ligne :

```json
{"op":"snapshot","request_id":"snapshot-1"}
{"op":"set","point":"soc_pct","value":75.0,"request_id":"set-1"}
{"op":"set","point":"running","value":true,"request_id":"set-2"}
{"op":"quit"}
```

`set` accepte un nom canonique de point de télémesure et une valeur JSON numérique finie ou booléenne selon son type. `request_id` est facultatif et doit être une chaîne lorsqu'il est fourni. Une requête invalide produit une erreur sans modifier la valeur ni son horodatage. Ces opérations restent dans le pipe local ; elles ne créent aucun topic de contrôle MQTT.

Chaque événement de stdout commence par `EDGECS_GUI `, suivi d'un objet JSON sur une seule ligne. Les journaux humains utilisent stderr ; en mode GUI ils se terminent également par une fin de ligne pour permettre leur fusion par Qt. Les écritures sont synchronisées entre le thread MQTT et stdin.

Tous les événements contiennent `kind`, `device_id` et `timestamp` en UTC. Les formes spécifiques sont :

| `kind` | Champs spécifiques |
|---|---|
| `snapshot` | `request_id`, `measurements` : tableau des mesures internes ; émis automatiquement au démarrage et sur demande. |
| `measurement` | `point`, `dnp3_type`, `index`, `value`, `updated_at`, `source`, `simulated`, `request_id`. |
| `command_result` | `point`, `dnp3_type`, `index`, `value`, `received_at`, `request_id`, `status: "accepted_by_simulator"`, `feedback_point` ou `null`, `feedback_simulated`. |
| `status` | `state`, `message`, `mqtt_connected`, `mqtt_subscribed`. États : `starting`, `connecting`, `connected`, `disconnected`, `stopped`. |
| `error` | `op`, `request_id`, `message`, et `point` lorsqu'il est connu. |

Chaque entrée de `measurements` reprend les champs de mesure `point`, `dnp3_type`, `index`, `value`, `updated_at`, `source` et `simulated`. Les origines sont `initial`, `manual` et `feedback` ; `simulated: true` identifie spécifiquement l'écho `feedback`. Tous ces points restent des valeurs de laboratoire.

Le résultat local d'une commande provient de la validation par le simulateur du message reçu sur `edge/command`. Il ne remplace pas le résultat DNP3 publié par le Master.

## Gestion des processus et limites

Les programmes sont lancés par Qt sans shell ni terminal supplémentaire. Les arguments et variables d'environnement sont transmis séparément. stdout et stderr sont affichés dans des journaux horodatés, les échanges réseau bloquants utilisent des tâches de travail et les connexions MQTT un thread réseau.

Le démarrage attend des confirmations explicites : HTTPS et abonnements MQTT pour le Master ; enregistrement et canal DNP3 pour la Gateway, puis abonnement MQTT pour le simulateur. Les interfaces signalent les erreurs de configuration, de TLS, d'authentification, de broker, de port, de doublon, de délai et les processus terminés.

Après une coupure du broker, les clients se reconnectent indépendamment. Le Master et le simulateur peuvent redevenir prêts avant le client MQTT de la Gateway : une commande DNP3 peut alors être refusée transitoirement. Son résultat affiché reste la référence ; l'interface ne rejoue pas automatiquement une commande. Une modification du simulateur suivie d'une lecture DNP3 permet de vérifier le retour du chemin de télémesure avant un nouvel essai.

L'arrêt cible les enfants créés par la fenêtre, avec demande d'arrêt / fermeture de stdin, puis signal de terminaison et arrêt forcé après délai si nécessaire. Aucun balayage global de processus par nom n'est utilisé. L'absence de heartbeat applicatif physique reste une limite du prototype : un canal ouvert et un ancien résultat ne garantissent aucune disponibilité d'un équipement réel.

## Vérifications

Depuis la racine du dépôt, après compilation :

```bash
ctest --test-dir Gateway/build --output-on-failure
python3 tests/integration.py
python3 tests/test_simulator_ipc.py -v

TestApps/.venv/bin/python -m unittest discover -s TestApps/tests -v
QT_QPA_PLATFORM=offscreen EDGECS_RUN_GUI_INTEGRATION=1 \
  TestApps/.venv/bin/python -m unittest discover -s TestApps/tests -v
```

Le test C++ autonome `test_multi_gateway.cpp` et la console Master ont été retirés du périmètre des applications graphiques. Les commandes ci-dessus couvrent les validations communes Gateway, les communications natives, l'IPC du simulateur et les parcours Qt, dont l'isolation de plusieurs DER. Une vérification visuelle sur un bureau Ubuntu / WSLg reste nécessaire.

Vérifications réexécutées après ce nettoyage : compilation des moteurs réussie, CTest Gateway **1/1**, intégration native réussie dans ses deux phases, et suite Qt **12/12** avec intégration native activée en mode `offscreen` et avertissements de ressources traités en erreurs.

`tests/integration.py` utilise de vrais processus C++, HTTPS avec certificat temporaire, OpenDNP3/TCP et MQTT. Il vérifie plusieurs ressources simultanées puis des configurations avec noms et indices modifiés. Il crée son propre broker sur un port libre ; les traces d'un échec sont conservées. `--keep-artifacts` conserve aussi celles d'un succès. Les options `--derms-build` et `--gateway-build` sélectionnent d'autres dossiers de compilation.

`tests/test_simulator_ipc.py` lance de vrais simulateurs et un broker temporaire. Il contrôle les valeurs et horodatages internes, les types invalides, les limites de commandes, les échos identifiés, les noms inconnus du code, l'isolation de deux simulateurs, la compatibilité console, le cadrage des événements dans des sorties fusionnées et leur ordre pendant des changements concurrents. `--gateway-build` sélectionne un autre build.

Les tests Python de `TestApps/tests` vérifient les services communs. Sans `EDGECS_RUN_GUI_INTEGRATION=1`, les parcours natifs GUI sont ignorés explicitement. Avec cette variable, ils utilisent de vrais widgets Qt en mode `offscreen`, les moteurs compilés et un broker / des certificats temporaires, sur des ports libres. Le mode sans affichage ne remplace pas une vérification visuelle sur Ubuntu ou WSLg : ouvrir les deux fenêtres, contrôler leur lisibilité, tester le sélecteur de fichier, connecter les deux exemples, commander et lire chaque DER, puis fermer une DER en vérifiant que l'autre continue.

Pour le scénario d'une nouvelle configuration, copier un exemple dans un autre fichier, changer `device_id`, les noms, alias, indices et ports, conserver les associations de types AO→AI et BO→BI pour `feedback_point`, puis le charger. Aucun changement Python spécifique aux nouveaux points ne doit être nécessaire. Le schéma courant réserve `min` et `max` aux commandes AO.

Les tests avec sockets nécessitent l'autorisation de créer des connexions et écouteurs de boucle locale. Les tests natifs nécessitent les bibliothèques C++ et outils Mosquitto/openssl installés. Sans ces dépendances, un échec ou un test ignoré ne constitue pas une validation des communications.

## Dépannage

| Symptôme | Vérification |
|---|---|
| `No module named PySide6` ou `paho` | Utiliser `TestApps/.venv/bin/python` et installer `TestApps/requirements.txt`. |
| Qt ne trouve pas d'écran ou de plugin `xcb` | Vérifier WSLg / la session graphique et les bibliothèques système Qt. Utiliser `offscreen` uniquement pour les tests sans fenêtre. |
| Exécutable introuvable | Compiler le projet concerné ou définir `EDGECS_*_BIN`. |
| Broker inaccessible / abonnements non confirmés | Démarrer le broker externe, vérifier son IPv4, son port et ses accès MQTT. |
| Master inaccessible | Vérifier le processus, l'IPv4, le port HTTPS et l'état de démarrage. |
| Erreur TLS | Vérifier CA, expiration et SAN du certificat pour l'IP utilisée. |
| HTTP 401 | Vérifier que Master et DER utilisent le même jeton. |
| Identité ou endpoint déjà enregistré | Utiliser une identité distincte ; pour changer un mapping conservé, redémarrer le Master. |
| Port occupé ou IP non locale | Changer le port ou choisir une adresse appartenant à la machine Gateway. |
| Valeur Master ancienne après modification ou commande | Déclencher **Lire les mesures** ; la copie interne DER et la dernière acquisition Master sont distinctes. |
| Processus C++ terminé | Lire son journal dans l'application ; vérifier configuration, bibliothèques et erreur réseau native. |

Les détails du contrat JSON et des moteurs se trouvent dans le [guide de configuration](../GUIDE_CONFIGURATION_DYNAMIQUE.md).
