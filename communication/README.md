# EDGECS — configuration-driven DERMS and Gateway

EDGECS uses one JSON point contract for HTTPS Gateway registration, DERMS device discovery, DNP3 command/telemetry mapping, and the generic MQTT DER simulator. Resource types are metadata; new device names, aliases and DNP3 indices do not require recompiling the applications.

The independent Qt laboratory applications are in [TestApps](TestApps/README.md):
`python3 TestApps/master_app.py` supervises the C++ Master, and each instance of
`python3 TestApps/der_app.py` supervises its own C++ Gateway and simulator. Install
their separate Python requirements first, then use the Master window's local TLS
setup button for a same-machine laboratory session. Mosquitto remains external.

See [the execution and configuration guide](GUIDE_CONFIGURATION_DYNAMIQUE.md) for startup, discovery API examples, configuration rules and restart behavior.
See [the implementation report](IMPLEMENTATION_REPORT.md) for the complete changed-file inventory, verification results and remaining limits.

Build from this workspace with the existing dependency installations:

```bash
cmake -S Gateway -B Gateway/build -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install" -DCMAKE_BUILD_TYPE=Debug
cmake --build Gateway/build -j2
cmake -S DERMS -B DERMS/build -DCMAKE_PREFIX_PATH="$PWD/opendnp3-install;$PWD/drogon-ssl-install" -DCMAKE_BUILD_TYPE=Debug
cmake --build DERMS/build -j2
ctest --test-dir Gateway/build --output-on-failure
python3 tests/integration.py
```

The integration test starts its own loopback Mosquitto broker and real Master, Gateway and simulator processes. It generates a temporary certificate/token, checks both communication paths and two simultaneous resource types, then restarts the same binaries with renamed/reindexed points and a new resource type. Failed runs retain logs and temporary configurations in the printed directory. Use `--keep-artifacts` to retain a successful run.

Key paths:

| Path | Responsibility |
|---|---|
| `shared/common.hpp`, `shared/common.cpp` | Shared configuration/message validation, point and alias resolution, envelopes |
| `DERMS/src/master.cpp` | HTTPS registration/discovery, isolated DNP3 sessions, commands and on-demand READ |
| `DERMS/src/registry.*` | Registered capabilities, connection state and latest received telemetry |
| `TestApps/master_app.py`, `TestApps/der_app.py` | Qt interfaces for discovery, commands, measurements and native process supervision |
| `Gateway/src/outstation.cpp` | Configuration-created DNP3 database and DNP3↔MQTT translation |
| `Gateway/src/simulated_der.cpp` | DER App simulation engine and optional generic command feedback; executables `edgecs_der_sim` and compatibility name `edgecs_bess_sim` |
| `Gateway/config/outstation_config.json` | BESS example: AO[0], AI[0]/AI[1], BO[0]/BI[0] |
| `Gateway/config/generator_config.json` | Generator example: AO[3], AI[5]/AI[8], BO[1]/BI[2] |
| `tests/integration.py` | Actual HTTPS/DNP3/MQTT acceptance tests |

Configuration is loaded at startup. After changing an already registered mapping, restart the DERMS, affected Gateway and simulator through their Qt windows. DNP3 telemetry acquisition remains on demand through **Lire les mesures** or the MQTT `read` API. The simulator echoes configured `feedback_point` values and provides no physical DER model.

The project remains a laboratory prototype. HTTPS authentication and certificate verification are preserved. DNP3 and MQTT transport security have the same limits described in the guide.
