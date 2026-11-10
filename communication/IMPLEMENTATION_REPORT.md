# Configuration-driven refactor

## Result and architecture

The existing OpenDNP3, MQTT and HTTPS architecture is preserved. A Gateway's JSON is the authoritative device/point contract. DER categories are arbitrary nonempty metadata; communication behavior depends only on configured point direction/type, index and constraints.

1. The Gateway and simulator load the same validated JSON at startup. The Gateway creates sparse AI/BI database points, initial values and logical addresses from it. AO/BO handlers resolve type/index back to the configured command, validate it and publish a canonical MQTT command envelope.
2. The Gateway registers the JSON over verified HTTPS with Bearer authentication. DERMS validates it, rejects conflicting identities/endpoints and creates an isolated DNP3 Master session. Identical renewal is idempotent. Registration and TCP connection status are distinct.
3. The reusable registry exposes the original points and communication configuration, direction-separated commands/telemetry, registration times, TCP channel state and latest DNP3 observations. Authenticated GET endpoints provide device lists, individual descriptors and telemetry snapshots. Registry access is synchronized by the service.
4. Commands arrive through the existing MQTT interface using device ID, logical name or alias, value and protocol envelope. The Master validates them against that device's mapping, sends AO Double64 or BO latch at its configured index, and publishes the actual DNP3 command result with the caller's request ID.
5. MQTT telemetry updates the Gateway's configured AI/BI database. An explicit interface READ performs a real DNP3 Class 0 request. Session-local SOE handling resolves the measurement, caches its value/quality/receipt time and publishes it to the interface MQTT broker. There is no periodic telemetry acquisition or startup integrity read.
6. The Qt Master application discovers and selects devices through HTTPS without local device files. Commands, aliases, units and limits come from the registry. The Qt DER application launches the generic C++ simulator, which uses configured initial values and optional compatible `feedback_point` echo rules.

A DNP3 acknowledgement means Outstation acceptance and submission of an MQTT publication. It does not prove MQTT delivery or DER execution. Standard AO/BO commands carry no application request ID; the Gateway creates a new downstream envelope ID. Static Class 0 observations have no device timestamp: `dnp3_timestamp=0` means unavailable, while `received_at` is Master receipt time.

## Source changes

| Files | Responsibility |
|---|---|
| `shared/common.hpp`, `shared/common.cpp` (added) | One configuration/message/value validation implementation, point/alias lookup, timestamps and envelopes |
| `DERMS/src/common.hpp`, `DERMS/src/common.cpp`, `Gateway/src/common.hpp`, `Gateway/src/common.cpp` | Compatibility wrappers around the shared implementation |
| `DERMS/src/registry.hpp`, `DERMS/src/registry.cpp` | Capabilities and runtime snapshots, connection state, registration renewals, isolated latest telemetry |
| `DERMS/src/master.cpp` | Runtime registry integration, authenticated device/detail/telemetry discovery, generic dispatch, READ completion and reliable error responses |
| `TestApps/master_app.py`, `TestApps/der_app.py` | Qt device discovery, commands, measurements and native process supervision |
| `Gateway/src/outstation.cpp` | Configured registration endpoint, shared value validation, checked DNP3 startup/shutdown and useful registration failure diagnostics |
| `DERMS/CMakeLists.txt`, `Gateway/CMakeLists.txt` | Shared sources, generic `edgecs_der_sim` executable with historical executable retained, optional integration CTest |
| `Gateway/tests/test_common.cpp` | Configuration, message and point validation tests |
| `tests/integration.py` (added) | Real HTTPS/OpenDNP3/MQTT acceptance harness using private ports, broker, generated certificate and token |
| `Gateway/config/outstation.schema.json` | Arbitrary DER categories, optional legacy MQTT settings and configured registration host |
| `Gateway/config/outstation_config.json`, `Gateway/config/generator_config.json` | BESS and generator examples with explicit registration host |
| `DERMS/config/gateway_bess01_example.json`, `DERMS/config/gateway_bess02_example.json`, `DERMS/config/gateway_generator_example.json` | Matching registration examples |
| `DERMS/Dockerfile`, `Gateway/Dockerfile` | Workspace-root contexts containing shared code, explicit source copies, updated dependencies/executables |
| `README.md`, `GUIDE_CONFIGURATION_DYNAMIQUE.md`, `DERMS/README.md`, `Gateway/README.md` | Current architecture, APIs, build/startup, certificate setup, configuration rules, tests and restart instructions |
| `IMPLEMENTATION_REPORT.md` (added) | Change inventory, implementation decisions and verification record |

`Gateway/src/simulated_der.cpp` fournit le moteur générique requis par la DER App, avec un mode IPC JSON pour Qt et un mode terminal. Aucun modèle physique de DER n'a été introduit. La console Master autonome et `DERMS/tests/test_multi_gateway.cpp` ont été retirés lors du nettoyage demandé pour les applications graphiques ; leurs cibles CMake ne font plus partie du projet.

## Hardcoded assumptions removed

- The fixed BESS/PV/GENERATOR/EVSE/OTHER category allowlist is replaced with arbitrary nonempty `der_type` metadata.
- The Master application needs no local DER configuration or fixed device selection to discover all registered devices and capabilities.
- Separate copies of point validation/mapping are replaced by one shared implementation used by both applications and supporting tools.
- Master commands now accept configured aliases as well as canonical names. Numeric values retain Double64 precision through an already-supported Gateway handler.
- Telemetry is available through the common registry and REST snapshots, rather than being visible only inside a session and its MQTT publications.

Existing Gateway database creation, per-session DNP3 point mapping and simulator feedback were already configuration-driven. They were retained and verified rather than replaced with device-specific alternatives.

## Example configurations

| Example | Analog command | Analog feedback | Binary command / feedback |
|---|---|---|---|
| [BESS](Gateway/config/outstation_config.json) | `power_setpoint_kw`, alias `power`, AO[0], -50..50 kW | `measured_power_kw`, AI[0]; `soc_pct`, AI[1] | `enable`, BO[0] / `running`, BI[0] |
| [Generator](Gateway/config/generator_config.json) | `frequency_setpoint_hz`, alias `frequency`, AO[3], 55..65 Hz | `measured_frequency_hz`, AI[5]; `temperature_c`, AI[8] | `start_generator`, BO[1] / `generator_running`, BI[2] |

The integration test deliberately uses generator frequency at AI[1] alongside BESS SOC at AI[1], demonstrating different meanings for the same index across sessions. It subsequently changes the BESS configuration to arbitrary type `THERMAL_STORE`, command `dispatch_target`/`target` at AO[23] and feedback `observed_output` at AI[17], then restarts the same executables.

## Build and execution

From the workspace root, using the existing dependency installations:

```bash
cmake -S Gateway -B Gateway/build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install"
cmake --build Gateway/build -j2
cmake -S DERMS -B DERMS/build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install;$PWD/drogon-ssl-install"
cmake --build DERMS/build -j2
ctest --test-dir Gateway/build --output-on-failure
python3 tests/integration.py --keep-artifacts
```

The integration command launches and cleans up its own real processes and generates test credentials. It needs local network sockets. No existing broker, certificates or secrets are required.

Pour une démonstration interactive, suivre le [premier lancement Qt](TestApps/README.md#premier-lancement-local) : démarrer Mosquitto, ouvrir la Master App, préparer les accès locaux et démarrer le Master, puis ouvrir une DER App par configuration :

```bash
TestApps/.venv/bin/python TestApps/master_app.py
TestApps/.venv/bin/python TestApps/der_app.py Gateway/config/outstation_config.json
TestApps/.venv/bin/python TestApps/der_app.py Gateway/config/generator_config.json
```

Sélectionner une DER dans le Master pour utiliser ses commandes et **Lire les mesures**. Chaque DER App supervise sa propre Gateway et son simulateur. Les accès TLS et paramètres réseau sont décrits dans le guide.

## Verification record

Les validations courantes sont la compilation des deux projets, le CTest Gateway, `tests/integration.py`, `tests/test_simulator_ipc.py` et les tests Qt décrits dans [TestApps](TestApps/README.md#vérifications). Le test DERMS autonome supprimé n'est plus une cible CTest par défaut. L'option `EDGECS_INTEGRATION_TESTS=ON` permet toujours d'exécuter le scénario de communication via CTest.

Après le nettoyage, la compilation native, le CTest Gateway (1/1), les deux phases de l'intégration native et la suite Qt (12/12, `offscreen`, avertissements de ressources traités en erreurs) ont réussi.

Le scénario natif vérifie HTTPS authentifié, les commandes et lectures DNP3 réelles, MQTT, plusieurs ressources, l'isolation des indices et le redémarrage avec des noms/indices modifiés. Les tests Qt couvrent également plusieurs DER et leur isolation. Le mode `offscreen` ne valide pas l'affichage sur un bureau Ubuntu / WSLg ; Docker et les DER physiques nécessitent leurs propres vérifications.

## Remaining limits

- Configuration loads at startup. Changing an already registered mapping requires restarting DERMS and the affected Gateway/simulator through their Qt windows. Unchanged Gateways renew registration every 30 seconds. There is no hot reload or device-removal API.
- Registry and latest telemetry state are in memory. TCP `open` is a connection indication, not DER health. READ returns current Gateway database values without forcing a fresh DER acquisition.
- Supported point/control kinds remain AO, boolean BO latch, AI and BI. Pulse/trip-close/counters and physical/control models need separate explicit extensions.
- Existing verified HTTPS/Bearer and private-address registration restrictions remain. DNP3 has no TLS/SAv5 and MQTT uses plain TCP with optional username/password, as in the prototype. No security check was disabled. Deployment beyond the existing laboratory scope needs separate transport/security work.
- OpenDNP3 3.1.2 is an archived dependency. Docker packaging and production/physical hardware behavior remain unverified.
