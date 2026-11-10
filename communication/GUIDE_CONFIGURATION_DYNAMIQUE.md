# EDGECS configuration and execution guide

## Architecture

Each Gateway loads and validates a JSON configuration at startup, creates its DNP3 AI/BI database and registers that configuration with the DERMS through authenticated HTTPS. DERMS validates it again and creates an isolated Master session. A `device_id` identifies a registry entry; the DNP3 type and index are always interpreted inside that device's session.

The shared implementation in `shared/common.*` owns configuration validation, value validation, canonical point lookup, direction-specific alias lookup and protocol envelopes. The Gateway, simulator and Master use it. `der_type` is nonempty descriptive metadata; it selects no communication behavior.

```text
Master App / backend                    DERMS                       Gateway                  Simulated DER
GET HTTPS registry -------------------> capabilities + latest state
MQTT <id>/command --------------------> configured AO/BO -- DNP3 --> configured point
                                                                       | MQTT <id>/edge/command
                                                                       +-------------------> command
                                                                       |<------------------- feedback/measurement
                                                                       | MQTT <id>/edge/telemetry
                                                                       v
MQTT <id>/read -----------------------> DNP3 READ Class 0 ------------> current AI/BI database
                                       <------------------------------ AI/BI response
                                       cache canonical telemetry
MQTT <id>/telemetry <------------------+
```

All MQTT topics above start with `edgecs/`. DERMS subscribes to interface `command`/`read` topics; the Gateway subscribes to `edge/telemetry`; the simulator subscribes to `edge/command`. The commands therefore traverse real DNP3 before they reach the DER. The Master interface broker is configured with `MQTT_HOST`/`MQTT_PORT`; the edge broker is configured by each Gateway JSON's `mqtt` object. They can differ.

There is no periodic telemetry acquisition and no startup integrity scan. `read` performs an actual DNP3 Class 0 acquisition. A Gateway keeps its latest values independently of reads. READ retrieves that current database; it does not force a new physical sensor sample. Repeated READs publish unchanged values too.

## Configuration contract

Use [the BESS configuration](Gateway/config/outstation_config.json), [the generator configuration](Gateway/config/generator_config.json) and [the JSON schema](Gateway/config/outstation.schema.json). Runtime validation also checks cross-point and cross-device constraints that JSON Schema cannot express.

| Field | Meaning |
|---|---|
| `schema_version` | Integer `1` |
| `device_id` | Unique nonempty identifier using letters, digits, `_` and `-` |
| `name`, `der_type` | Nonempty identity/display metadata; arbitrary resource types are supported |
| `dnp3.host` | Gateway IPv4 address reachable from DERMS; registration permits loopback/private addresses |
| `dnp3.port` | Gateway TCP listener port, 1–65535 |
| `dnp3.master_address`, `outstation_address` | Distinct logical DNP3 addresses, 0–65519 |
| `mqtt.host`, `mqtt.port` | Edge-side broker IPv4 and port; when `mqtt` is absent, existing MQTT environment defaults apply |
| `master_api_host`, `master_api_port` | Optional DERMS registration IPv4 and HTTPS port (default 8443) |
| `points` | Nonempty list of configured point definitions |

`MASTER_REGISTER_URL=https://host:port/api/v1/outstations/register` overrides the complete registration URL, including host and port. HTTPS remains required. Without a configured/environment Master host or full URL, the Gateway retains its interactive IPv4 prompt. `EDGECS_API_HOST` selects DERMS's local HTTPS bind address; it is independent of the Gateway's advertised `dnp3.host`.

| Point field | Rule |
|---|---|
| `name` | Canonical logical identifier, unique within the device |
| `alias` | Optional name for commands/CLI; unambiguous within its direction, including collisions with canonical names |
| `direction` | `command` for AO/BO; `telemetry` for AI/BI |
| `dnp3_type` | AO numeric command, BO boolean latch command, AI numeric measurement, BI boolean measurement |
| `index` | Integer 0–65535, unique within the device and DNP3 type; sparse indices are supported |
| `unit` | Display metadata string |
| `min`, `max` | Required finite ordered AO limits, inclusive; absent on other types |
| `initial` | Optional AI number/BI boolean; defaults to 0/false; absent on commands |
| `feedback_point` | Optional canonical telemetry name on commands; AO→AI or BO→BI only |

An alias can be reused in the other direction, such as BESS command `power` and telemetry `power`. Unknown keys, duplicate indices/names, ambiguous aliases, invalid directions/types/values and invalid feedback targets are rejected. Analog values must be finite numbers; booleans must be JSON booleans. The simulator's terminal mode also accepts `1/0`, `true/false` and `on/off` as text for boolean points.

Examples in the supplied files:

| Device | Command | DNP3 | Feedback |
|---|---|---|---|
| `bess-01` | `power_setpoint_kw` / `power` | AO[0], -50…50 kW | `measured_power_kw`, AI[0] |
| `bess-01` | `enable` | BO[0] | `running`, BI[0] |
| `generator-01` | `frequency_setpoint_hz` / `frequency` | AO[3], 55…65 Hz | `measured_frequency_hz`, AI[5] |
| `generator-01` | `start_generator` / `start` | BO[1] | `generator_running`, BI[2] |

The BESS also has `soc_pct` at AI[1]; the generator has `temperature_c` at AI[8]. These names occur in examples and tests, not in command dispatch or point translation.

## Build and automated verification

Run from the workspace root. Existing dependency installations can be reused:

```bash
cmake -S Gateway -B Gateway/build -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install"
cmake --build Gateway/build -j2
cmake -S DERMS -B DERMS/build -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install;$PWD/drogon-ssl-install"
cmake --build DERMS/build -j2
ctest --test-dir Gateway/build --output-on-failure
python3 tests/integration.py
```

Dependencies are C++17, CMake, OpenDNP3 3.1.2, SSL-enabled Drogon, Paho MQTT C++, libcurl, nlohmann/json and Threads. The integration harness additionally uses Python 3's standard library, `openssl`, `mosquitto`, `mosquitto_pub` and `mosquitto_sub`. It creates an independent loopback broker, token and TLS certificate and uses free temporary ports. It does not change existing configuration files or require a running system broker.

The harness exercises acceptance scenarios through real processes: BESS and generator registration/discovery; alias AO/BO commands observed after DNP3 at the edge MQTT subscriber; simulator feedback; manual DNP3 READ into the registry; same AI index with different meanings on separate sessions; invalid registrations/commands/telemetry; TLS and authentication rejection; and a full restart with an arbitrary resource type and renamed/reindexed points. It compares executable hashes before/after the configuration change. Success messages are printed only after those assertions pass. Failed runs retain configs/logs in the printed `/tmp/edgecs-integration-*` directory; `--keep-artifacts` also keeps successful runs. The Qt test commands are documented in [TestApps](TestApps/README.md#vérifications).

For other binary locations, pass `--derms-build <path>` and `--gateway-build <path>`. Optional DERMS CTest integration is enabled with `-DEDGECS_INTEGRATION_TESTS=ON` and expects `Gateway/build`.

Docker build contexts must include the shared source directory:

```bash
docker build -f DERMS/Dockerfile -t edgecs-derms .
docker build -f Gateway/Dockerfile -t edgecs-gateway .
```

The Dockerfiles download build dependencies and OpenDNP3, so these builds need network access. Their source copies exclude local certificates and private keys. Mount credentials and certificates at runtime. Docker packaging is separate from the local executable acceptance test.

## Create a local certificate and token

From the workspace root:

```bash
mkdir -p DERMS/certs
openssl req -x509 -newkey rsa:3072 -sha256 -nodes \
  -keyout DERMS/certs/server.key -out DERMS/certs/server.crt -days 3 \
  -subj '/CN=localhost' -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'
chmod 600 DERMS/certs/server.key
export EDGECS_REGISTRATION_TOKEN="$(openssl rand -hex 24)"
```

Use this same generated token for DERMS, Gateway and the Qt applications. Set `EDGECS_CA_CERT` to the trusted certificate path for clients. A remote deployment's certificate must contain its actual DNS/IP in SAN. No client disables certificate or hostname verification. For a local GUI session, the Master application's **Créer / charger les accès locaux du laboratoire** button prepares shared credentials instead; see [TLS setup](TestApps/README.md#tls-et-authentification).

## Run the two examples

Après l'[installation Python](TestApps/README.md#installation-ubuntu--wsl2) et la compilation native, démarrer un broker Mosquitto local, puis lancer les fenêtres dans des terminaux distincts :

```bash
TestApps/.venv/bin/python TestApps/master_app.py
TestApps/.venv/bin/python TestApps/der_app.py Gateway/config/outstation_config.json
TestApps/.venv/bin/python TestApps/der_app.py Gateway/config/generator_config.json
```

Dans la Master App, conserver les paramètres locaux, préparer les accès TLS, puis cliquer sur **Démarrer le Master**. Lancer ensuite les deux DER App pour qu'elles chargent ces mêmes accès et cliquer sur **Démarrer la DER** dans chaque fenêtre. Les exemples partagent MQTT `127.0.0.1:1883`, avec des ports DNP3 et des adresses Outstation distincts. Les fenêtres démarrent leurs moteurs C++ ; aucun lancement natif supplémentaire n'est nécessaire.

Le Master découvre les DER par HTTPS sans fichier JSON local. Sélectionner `bess-01`, envoyer `power_setpoint_kw = 30` et `enable = true`, puis cliquer sur **Lire les mesures**. Sélectionner ensuite `generator-01`, envoyer `frequency_setpoint_hz = 60.5` et `start_generator = true`, puis lire ses mesures. Les contrôles affichés viennent de chaque configuration.

Dans une DER App, modifier `soc_pct` ou `temperature_c` agit sur le simulateur C++ ; une nouvelle lecture dans la Master App récupère la valeur via la Gateway et DNP3. `feedback_point` fournit seulement un écho générique, sans modèle physique. Le [mode terminal du simulateur](Gateway/README.md) reste disponible pour des essais natifs ; `simulated_der.cpp` est aussi le moteur requis par la DER App.

## Discovery API and command results

All registry endpoints require `Authorization: Bearer <token>`:

```bash
curl --cacert DERMS/certs/server.crt \
  -H "Authorization: Bearer $EDGECS_REGISTRATION_TOKEN" \
  https://127.0.0.1:8443/api/v1/outstations
```

- `GET /api/v1/outstations` returns `{ "outstations": [...] }`.
- `GET /api/v1/outstations/<device_id>` returns one descriptor or 404.
- `GET /api/v1/outstations/<device_id>/telemetry` returns `device_id`, `latest_telemetry` and `connection`.

Descriptors contain identity, communication configuration, all `points`, direction-separated `commands` and `telemetry`, `registered_at`, `last_registration_at`, `connection` and `latest_telemetry`. Latest telemetry is keyed by canonical logical name and contains the normal envelope plus `dnp3_type`, `dnp3_index`, `quality_flags`, `dnp3_timestamp` and `received_at`. It is empty before a DNP3 read. `dnp3_timestamp` is DNP3 time in milliseconds when available; current static Class 0 points carry no time, so zero means unavailable. Envelope/receipt timestamps represent Master receipt, not sensor acquisition time. Channel state `open` indicates a TCP connection and provides no guarantee of physical DER health.

A backend can submit a configured command on `edgecs/<device_id>/command` using this envelope:

```json
{
  "schema_version": 1,
  "device_id": "generator-01",
  "point": "frequency",
  "value": 60.5,
  "kind": "command",
  "request_id": "unique-application-request-id",
  "timestamp": "2026-01-01T00:00:00.000+00:00"
}
```

The point may be its canonical name or unambiguous configured alias. `command_result` retains the caller's request ID, canonical point and DNP3 mapping. `accepted_by_outstation` means the Outstation accepted DNP3 OPERATE and submitted its MQTT publication. It does not confirm DER execution or MQTT delivery. DER feedback must be observed separately. DNP3 AO/BO messages do not carry this application request ID, so the Gateway creates its own command-envelope ID across that boundary.

A `kind: "read"`, `point: "*"`, `value: null` envelope on the `read` suffix requests acquisition. `read_result` first reports `scan_requested` and subsequently `read_completed` or `read_failed` with a DNP3 task result. Measurements arrive separately on the `telemetry` suffix.

## Changes, errors and limits

Configuration is loaded at process startup. After changing an already registered device's mapping, stop/restart DERMS and the affected Gateway/simulator through their Qt windows. Unchanged Gateways renew registration every 30 seconds and rebuild the in-memory registry after a Master restart. An identical renewal is idempotent. A changed configuration for an existing `device_id`, or another identity claiming the same DNP3 endpoint, is rejected. There is no hot reload or device-removal API.

Transient registration network/server failures retry; nontransient HTTP 4xx responses stop the Gateway with the server's validation/authentication error. Invalid configurations, unknown commands and invalid values report useful errors. Registry/telemetry state is in memory. DNP3 support remains AO, BO latch, AI and BI; counter/pulse/trip-close control models are outside this contract. Connections are reported separately from registration and latest telemetry.

The existing prototype has authenticated verified HTTPS registration/discovery, private-address registration restrictions and optional MQTT username/password. Its DNP3 channel has no TLS/SAv5, and its MQTT transport is plain TCP. No transport-security mechanism has been disabled to implement dynamic mappings. OpenDNP3 3.1.2 is an archived dependency. Production authorization, durable state, DER execution acknowledgements and device-specific physical/control models remain separate work.
