# Gateway / DNP3 Outstation and generic DER simulator

The Gateway loads identity, addresses, MQTT settings and all point definitions from JSON. It creates configured AI/BI database points, resolves AO/BO commands by type/index, validates values and publishes canonical logical names to the simulator's MQTT command topic. Telemetry follows the inverse mapping. It registers the same validated configuration with DERMS over authenticated HTTPS.

See [the workspace guide](../GUIDE_CONFIGURATION_DYNAMIQUE.md) for configuration rules, multi-device startup, discovery, tests and restart behavior.

From the workspace root, using the local OpenDNP3 installation:

```bash
cmake -S Gateway -B Gateway/build -DCMAKE_BUILD_TYPE=Debug -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install"
cmake --build Gateway/build -j2
ctest --test-dir Gateway/build --output-on-failure
```

Dependencies: C++17, CMake, Threads, OpenDNP3 3.1.2, Paho MQTT C++, libcurl and nlohmann/json. Docker uses the **workspace root** as build context: `docker build -f Gateway/Dockerfile -t edgecs-gateway .`.

Start in separate terminals, using the same JSON for the Gateway and its simulator:

The Gateway requires exactly one configuration file path at launch, either relative to the current directory or absolute. Missing or extra arguments print usage and stop; `EDGECS_CONFIG` does not select the Gateway configuration.

```bash
export EDGECS_REGISTRATION_TOKEN='<same token as DERMS>'
export EDGECS_CA_CERT="$PWD/DERMS/certs/server.crt"
./Gateway/build/edgecs_gateway Gateway/config/outstation_config.json
```

```bash
./Gateway/build/edgecs_der_sim Gateway/config/outstation_config.json
```

Use `Gateway/config/generator_config.json` for a second resource on a different DNP3 port. `edgecs_bess_sim` remains an executable compatibility name for the same generic simulator.

The Docker image also requires a configuration path, for example `docker run --rm edgecs-gateway /app/config/generator_config.json` (with the registration credentials and CA mounted/configured as described in the guide).

`master_api_host` and `master_api_port` configure the registration endpoint. `MASTER_REGISTER_URL=https://.../api/v1/outstations/register` overrides its full URL. Legacy configurations without a Master host retain the IPv4 startup prompt. `EDGECS_CA_CERT` sets the trusted CA; hostname and certificate checks stay enabled. Registrations renew every 30 seconds. Nontransient HTTP 4xx registration failures stop with the server's error; network and server failures retry.

Simulator commands are `list`, `status`, `set <measurement_or_alias> <value>`, `<alias> <value>`, `send`, and `quit`. Commands received from MQTT update only the configured compatible `feedback_point`, if present. This is a generic echo demonstration, with no battery/generator/inverter physics.

The [Qt DER application](../TestApps/README.md) launches its own Gateway
and simulator using one temporary validated configuration. `src/simulated_der.cpp`
is the C++ simulation engine required by that application. The simulator's
`<configuration.json> --gui` mode accepts private JSON-line stdin requests and
reports structured internal-state events; terminal mode remains available.

The Gateway maintains current telemetry independently of DNP3 reads. DERMS acquires those values only when its interface requests `read`; there is no periodic Master acquisition. A configuration change requires restarting the affected Gateway and simulator and restarting DERMS if that device identity was already registered with another mapping.
