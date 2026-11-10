# DERMS / DNP3 Master

The Master creates one DNP3 session for each validated HTTPS Gateway registration. It resolves commands and incoming AI/BI values using that session's registered point definitions. Its authenticated read-only discovery endpoints expose identities, capabilities, TCP channel status and latest telemetry to the Qt Master application and other API clients.

See [the workspace guide](../GUIDE_CONFIGURATION_DYNAMIQUE.md) for the full configuration contract, launch commands, API examples and acceptance tests.

From the workspace root:

```bash
cmake -S DERMS -B DERMS/build -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install;$PWD/drogon-ssl-install"
cmake --build DERMS/build -j2
```

Dependencies are C++17, CMake, Threads, OpenDNP3 3.1.2, SSL-enabled Drogon, Paho MQTT C++ and nlohmann/json. The workspace contains local OpenDNP3 and Drogon installations; no dependency download is required when using them. A Docker development image can be built **from the workspace root** with `docker build -f DERMS/Dockerfile -t edgecs-derms .`.

Required runtime environment:

```bash
export EDGECS_REGISTRATION_TOKEN='<shared token, at least 16 characters>'
export EDGECS_TLS_CERT="$PWD/DERMS/certs/server.crt"
export EDGECS_TLS_KEY="$PWD/DERMS/certs/server.key"
export EDGECS_API_HOST=127.0.0.1
export EDGECS_API_PORT=8443
export MQTT_HOST=127.0.0.1
export MQTT_PORT=1883
./DERMS/build/edgecs_master
```

L'application graphique Master découvre les capacités sans fichier JSON de DER local et peut démarrer le moteur C++ :

```bash
TestApps/.venv/bin/python TestApps/master_app.py
```

Suivre le [premier lancement Qt](../TestApps/README.md#premier-lancement-local) pour préparer les accès TLS, démarrer le Master, sélectionner une DER, envoyer ses commandes et utiliser **Lire les mesures**. La fenêtre peut rester ouverte avec un registre vide. Ne pas démarrer simultanément un deuxième moteur sur les mêmes ports. Le broker de l'interface Master peut être distinct du broker configuré dans le JSON de chaque Gateway.

Authenticated endpoints:

- `GET /api/v1/outstations` → `{ "outstations": [device descriptors] }`.
- `GET /api/v1/outstations/<device_id>` → one device descriptor, or 404.
- `GET /api/v1/outstations/<device_id>/telemetry` → latest telemetry and connection snapshot.
- `POST /api/v1/outstations/register` → validated configuration registration; identical renewals are idempotent.

`GET /health` also reports `mqtt_connected` for the C++ Master's broker connection.
The optional [Qt Master application](../TestApps/README.md) manages the existing
executable and discovers devices through these endpoints.

Commands remain on `edgecs/<device_id>/command`; `read` requests a real DNP3 Class 0 acquisition through `edgecs/<device_id>/read`. Responses use `command_result`, `read_result` and `telemetry` suffixes. A successful DNP3 command acknowledges Outstation acceptance; physical execution requires separate DER confirmation. A read publishes `scan_requested`, then `read_completed` or `read_failed` after the DNP3 task finishes.

Run actual communication tests after building both projects:

```bash
python3 tests/integration.py
```

To also run the harness through DERMS CTest, configure with `-DEDGECS_INTEGRATION_TESTS=ON`. It expects the Gateway executables in `Gateway/build`; use the standalone script's `--gateway-build`/`--derms-build` options for other build directories.
