#!/usr/bin/env python3
"""Laboratory GUI supervising one C++ Gateway and one C++ DER simulator.

The simulator remains the authority for local measurement state.  This GUI only
sends JSON requests over its private stdin pipe; it never publishes telemetry.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QPushButton, QSpinBox, QSplitter,
    QTabWidget, QTableWidgetItem, QPlainTextEdit, QVBoxLayout, QWidget,
)

from common.api_client import ApiClient
from common.config import (
    ConfigError, DeviceLock, TemporaryConfig, check_bind, find_executable,
    load_config, runtime_config, validate_config, validate_ipv4, validate_port,
    validate_value,
)
from common.lab import load_lab_settings
from common.mqtt_client import MqttClient
from common.process_manager import ManagedProcess
from common.widgets import (
    editor_value, fill_table, log_append, make_table, run_job, style, value_editor,
)


class DerWindow(QMainWindow):
    """Independent process ownership and startup state for one simulated DER."""

    START_TIMEOUT = 40.0
    IPC_TIMEOUT = 8.0

    def __init__(self):
        super().__init__()
        self.setWindowTitle("EDGECS · DER de laboratoire")
        self.resize(1220, 900)
        self._config = None
        self._runtime = None
        self._temporary = None
        self._lock = None
        self._api = None
        self._generation = 0
        self._active = False
        self._stopping = False
        self._closing = False
        self._poll_busy = False
        self._gateway_started = False
        self._simulator_started = False
        self._simulator_ready = False
        self._simulator_was_ready = False
        self._mqtt_ready = False
        self._preflight_ready = False
        self._deadline = 0.0
        self._failure = ""
        self._measurement_rows = {}
        self._editors = {}
        self._apply_buttons = []
        self._pending = {}
        self._command_points = {}
        self._output_buffers = {"Gateway": "", "Simulateur": ""}

        self.gateway = ManagedProcess(self)
        self.simulator = ManagedProcess(self)
        self.simulator.graceful_line = json.dumps({"op": "quit"})
        self.mqtt = MqttClient(self)
        self.pool = QThreadPool.globalInstance()
        self.gateway.output.connect(lambda line: self._output("Gateway", line))
        self.simulator.output.connect(lambda line: self._output("Simulateur", line))
        self.gateway.started.connect(lambda: self._process_started("Gateway"))
        self.simulator.started.connect(lambda: self._process_started("Simulateur"))
        self.gateway.exited.connect(lambda code: self._process_exited("Gateway", code))
        self.simulator.exited.connect(lambda code: self._process_exited("Simulateur", code))
        self.gateway.error.connect(lambda message: self._process_error("Gateway", message))
        self.simulator.error.connect(lambda message: self._process_error("Simulateur", message))
        self.mqtt.connected.connect(self._mqtt_connection)
        self.mqtt.error.connect(lambda message: self._log("MQTT : " + message))
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.stop_timer = QTimer(self)
        self.stop_timer.setInterval(100)
        self.stop_timer.timeout.connect(self._finish_stop)

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        title = QLabel("DER simulée · Gateway DNP3 + simulateur C++")
        title.setStyleSheet("font-size: 23px; font-weight: 700; color: #164e7d; padding: 5px;")
        layout.addWidget(title)
        note = QLabel("Essais de laboratoire uniquement. Les échos feedback_point sont simulés. "
                      "Les valeurs internes ci-dessous proviennent du simulateur C++.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.settings = QGroupBox("Configuration et réseau")
        settings_layout = QVBoxLayout(self.settings)
        file_row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setPlaceholderText("Sélectionner un fichier JSON depuis n'importe quel dossier")
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self._browse)
        file_row.addWidget(self.path, 1)
        file_row.addWidget(browse)
        settings_layout.addLayout(file_row)
        self.validation = QLabel("Aucune configuration chargée.")
        self.validation.setWordWrap(True)
        settings_layout.addWidget(self.validation)

        network = QHBoxLayout()
        left, right = QFormLayout(), QFormLayout()
        self.master_host = QLineEdit("127.0.0.1")
        self.api_port = self._port(8443)
        self.gateway_host = QLineEdit("127.0.0.1")
        self.dnp3_port = self._port(20000)
        self.mqtt_host = QLineEdit("127.0.0.1")
        self.mqtt_port = self._port(1883)
        left.addRow("IPv4 Master DERMS", self.master_host)
        left.addRow("Port HTTPS Master", self.api_port)
        left.addRow("IPv4 Gateway (écoute et annonce)", self.gateway_host)
        right.addRow("Port DNP3 Gateway", self.dnp3_port)
        right.addRow("Broker MQTT", self.mqtt_host)
        right.addRow("Port MQTT", self.mqtt_port)
        network.addLayout(left, 1)
        network.addLayout(right, 1)
        settings_layout.addLayout(network)

        self.advanced_toggle = QCheckBox("Afficher l'authentification TLS et les exécutables")
        settings_layout.addWidget(self.advanced_toggle)
        self.advanced = QWidget()
        advanced_layout = QFormLayout(self.advanced)
        lab = load_lab_settings()
        self.token = QLineEdit(lab.get("token", ""))
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("EDGECS_REGISTRATION_TOKEN / paramètres locaux du Master")
        self.ca = QLineEdit(lab.get("ca", ""))
        self.ca.setPlaceholderText("EDGECS_CA_CERT / certificat de confiance du Master")
        ca_row = QHBoxLayout()
        ca_row.addWidget(self.ca, 1)
        ca_browse = QPushButton("Parcourir…")
        ca_browse.clicked.connect(self._browse_ca)
        ca_row.addWidget(ca_browse)
        self.gateway_executable = QLineEdit()
        self.gateway_executable.setPlaceholderText("Détection automatique : edgecs_gateway")
        self.simulator_executable = QLineEdit()
        self.simulator_executable.setPlaceholderText("Détection automatique : edgecs_bess_sim")
        advanced_layout.addRow("Jeton d'enregistrement", self.token)
        advanced_layout.addRow("Autorité / certificat TLS", ca_row)
        advanced_layout.addRow("Exécutable Gateway (facultatif)", self.gateway_executable)
        advanced_layout.addRow("Exécutable simulateur (facultatif)", self.simulator_executable)
        self.advanced.setVisible(False)
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        settings_layout.addWidget(self.advanced)
        layout.addWidget(self.settings)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Démarrer la DER")
        self.start_button.setProperty("primary", True)
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start)
        self.stop_button = QPushButton("Arrêter la DER")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        self.state = QLabel("Arrêtée")
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.state, 1)
        layout.addLayout(actions)

        summary = QGroupBox("Supervision")
        summary_layout = QHBoxLayout(summary)
        first, second = QFormLayout(), QFormLayout()
        self.identity = QLabel("—")
        self.identity.setWordWrap(True)
        self.endpoint = QLabel("—")
        self.registration = QLabel("Non vérifié")
        self.dnp3 = QLabel("Inconnue")
        self.mqtt_state = QLabel("Arrêtée")
        self.simulator_mqtt = QLabel("Arrêté")
        self.gateway_state = QLabel("Arrêtée")
        self.simulator_state = QLabel("Arrêté")
        self.last_telemetry = QLabel("Aucune mesure DNP3 connue")
        first.addRow("DER", self.identity)
        first.addRow("Endpoint / adresses logiques", self.endpoint)
        first.addRow("Enregistrement HTTPS", self.registration)
        first.addRow("Canal DNP3 côté Master", self.dnp3)
        second.addRow("MQTT supervision", self.mqtt_state)
        second.addRow("MQTT simulateur", self.simulator_mqtt)
        second.addRow("Processus Gateway / simulateur", self._label_pair())
        second.addRow("Dernière télémesure reçue au Master", self.last_telemetry)
        summary_layout.addLayout(first, 1)
        summary_layout.addLayout(second, 1)
        layout.addWidget(summary)

        tabs = QTabWidget()
        measurements_page = QWidget()
        measurements_layout = QVBoxLayout(measurements_page)
        self.measurement_help = QLabel("Les valeurs JSON initiales sont indicatives avant le démarrage. "
                                      "Modifier transmet une demande au simulateur ; la valeur affichée change sur sa confirmation.")
        self.measurement_help.setWordWrap(True)
        measurements_layout.addWidget(self.measurement_help)
        self.measurements = make_table(["Point", "Alias", "DNP3", "Valeur interne", "Unité",
                                        "Dernière modification", "Origine", "Nouvelle valeur", "Action"])
        measurements_layout.addWidget(self.measurements)
        self.snapshot_button = QPushButton("Actualiser l'état interne du simulateur")
        self.snapshot_button.setEnabled(False)
        self.snapshot_button.clicked.connect(self._request_snapshot)
        measurements_layout.addWidget(self.snapshot_button)
        tabs.addTab(measurements_page, "Mesures internes AI / BI")

        commands_page = QWidget()
        commands_layout = QVBoxLayout(commands_page)
        command_note = QLabel("Commandes autorisées par le JSON. L'acceptation par le simulateur et les échos "
                              "simulés ne prouvent aucune exécution physique. Le Master lit le retour par une lecture DNP3 manuelle.")
        command_note.setWordWrap(True)
        commands_layout.addWidget(command_note)
        command_splitter = QSplitter(Qt.Orientation.Vertical)
        self.commands = make_table(["Point", "Alias", "DNP3", "Unité", "Minimum", "Maximum", "Retour simulé"])
        self.history = make_table(["Réception", "Point", "DNP3", "Valeur demandée", "Traitement simulateur", "Request ID"])
        command_splitter.addWidget(self.commands)
        command_splitter.addWidget(self.history)
        commands_layout.addWidget(command_splitter)
        tabs.addTab(commands_page, "Commandes et historique")

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(2000)
        tabs.addTab(self.log, "Journal et erreurs")
        layout.addWidget(tabs, 1)
        self.setCentralWidget(central)

    @staticmethod
    def _port(value):
        widget = QSpinBox()
        widget.setRange(1, 65535)
        widget.setValue(value)
        return widget

    def _label_pair(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.gateway_state)
        layout.addWidget(QLabel(" / "))
        layout.addWidget(self.simulator_state)
        layout.addStretch()
        return widget

    def _log(self, message):
        log_append(self.log, str(message))

    def _browse(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Configuration de la DER", "", "Configurations JSON (*.json);;Tous les fichiers (*)")
        if filename:
            self.load_configuration(filename)

    def _browse_ca(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Certificat TLS de confiance", "", "Certificats (*.crt *.pem);;Tous les fichiers (*)")
        if filename:
            self.ca.setText(str(Path(filename).resolve()))

    def load_configuration(self, filename):
        """Load an arbitrary path without ever modifying its contents."""
        if self._active:
            return
        self.path.setText(str(Path(filename).expanduser().resolve()))
        try:
            config = load_config(self.path.text())
            validate_config(config)
            self._config = config
            self.master_host.setText(config.get("master_api_host", "127.0.0.1"))
            self.api_port.setValue(config.get("master_api_port", 8443))
            self.gateway_host.setText(config["dnp3"]["host"])
            self.dnp3_port.setValue(config["dnp3"]["port"])
            self.mqtt_host.setText(config.get("mqtt", {}).get("host", "127.0.0.1"))
            self.mqtt_port.setValue(config.get("mqtt", {}).get("port", 1883))
            self.validation.setText("Configuration valide · " + self.path.text())
            self.validation.setStyleSheet("")
            self._render_configuration(config)
            self.start_button.setEnabled(True)
            self._log("Configuration validée : " + self.path.text())
        except Exception as error:
            self._config = None
            self.start_button.setEnabled(False)
            self.validation.setText("Configuration invalide : " + str(error))
            self.validation.setStyleSheet("color: #c0392b")
            self._clear_configuration()
            self._log("JSON invalide : " + str(error))

    def _clear_configuration(self):
        self.measurements.setRowCount(0)
        self.commands.setRowCount(0)
        self.history.setRowCount(0)
        self._measurement_rows.clear()
        self._editors.clear()
        self._apply_buttons.clear()
        self._command_points.clear()
        self.identity.setText("—")
        self.endpoint.setText("—")

    def _render_configuration(self, config):
        self._clear_configuration()
        self._identity(config)
        telemetry = [p for p in config["points"] if p["direction"] == "telemetry"]
        commands = [p for p in config["points"] if p["direction"] == "command"]
        rows = []
        for point in telemetry:
            rows.append([point["name"], point.get("alias", ""), f'{point["dnp3_type"]}[{point["index"]}]',
                         self._value_text(point.get("initial", False if point["dnp3_type"] == "BI" else 0)),
                         point.get("unit", ""), "Non démarré", "JSON initial", "", ""])
        fill_table(self.measurements, rows)
        for row, point in enumerate(telemetry):
            self._measurement_rows[point["name"]] = row
            editor = value_editor(point)
            self._editors[point["name"]] = editor
            self.measurements.setCellWidget(row, 7, editor)
            button = QPushButton("Modifier")
            button.setEnabled(False)
            button.clicked.connect(lambda checked=False, p=copy.deepcopy(point), e=editor: self._set_measurement(p, e))
            self.measurements.setCellWidget(row, 8, button)
            self._apply_buttons.append(button)
        fill_table(self.commands, [[p["name"], p.get("alias", ""), f'{p["dnp3_type"]}[{p["index"]}]',
                                   p.get("unit", ""), p.get("min", "—"), p.get("max", "—"),
                                   p.get("feedback_point", "—")] for p in commands])
        self._command_points = {p["name"]: p for p in commands}

    def _identity(self, config):
        self.identity.setText(f'{config["device_id"]} · {config.get("name", "")} · {config.get("der_type", "")}')
        dnp3 = config["dnp3"]
        self.endpoint.setText(f'{dnp3["host"]}:{dnp3["port"]} · Master {dnp3["master_address"]} / Outstation {dnp3["outstation_address"]}')

    def _start(self):
        if self._active or not self._config:
            return
        try:
            validate_config(self._config)
            master = self.master_host.text().strip()
            gateway = self.gateway_host.text().strip()
            validate_ipv4(master)
            validate_ipv4(gateway)
            for port in (self.api_port.value(), self.dnp3_port.value(), self.mqtt_port.value()):
                validate_port(port)
            mqtt_host = self.mqtt_host.text().strip()
            if not mqtt_host or any(c.isspace() for c in mqtt_host):
                raise ConfigError("Adresse du broker MQTT vide ou invalide")
            runtime = runtime_config(self._config, master, gateway, self.dnp3_port.value(),
                                     mqtt_host, self.mqtt_port.value(), self.api_port.value())
            lab = load_lab_settings()
            token = self.token.text().strip() or lab.get("token", "")
            ca = self.ca.text().strip() or lab.get("ca", "")
            if not token:
                raise ConfigError("Jeton manquant : démarrer/configurer la Master App ou renseigner EDGECS_REGISTRATION_TOKEN")
            if not ca or not Path(ca).expanduser().is_file():
                raise ConfigError("Certificat TLS introuvable : renseigner EDGECS_CA_CERT ou sélectionner le certificat du Master")
            self.token.setText(token)
            ca = str(Path(ca).expanduser().resolve())
            self.ca.setText(ca)
            api = ApiClient(master, self.api_port.value(), token=token, ca_cert=ca)
            device_lock = DeviceLock(mqtt_host, self.mqtt_port.value(), runtime["device_id"])
            device_lock.acquire()
            self._lock = device_lock
            self._temporary = TemporaryConfig(runtime)
            self._runtime = runtime
            self._api = api
            self._process_env = {
                "EDGECS_REGISTRATION_TOKEN": token, "EDGECS_CA_CERT": ca,
                "DNP3_BIND_HOST": gateway,
                "MASTER_REGISTER_URL": f"https://{master}:{self.api_port.value()}/api/v1/outstations/register",
            }
        except Exception as error:
            self._cleanup_resources()
            self._show_failure(str(error))
            return

        self._active = True
        self._stopping = False
        self._failure = ""
        self._generation += 1
        generation = self._generation
        self._gateway_started = False
        self._simulator_started = False
        self._simulator_ready = False
        self._simulator_was_ready = False
        self._mqtt_ready = False
        self._preflight_ready = False
        self._pending.clear()
        self._output_buffers = {"Gateway": "", "Simulateur": ""}
        self.settings.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.state.setText("Vérifications réseau, TLS et identité…")
        self.registration.setText("Vérification HTTPS authentifiée…")
        self.dnp3.setText("En attente")
        self.last_telemetry.setText("Aucune mesure DNP3 connue")
        self._identity(runtime)
        gateway_path = self.gateway_executable.text().strip()
        simulator_path = self.simulator_executable.text().strip()

        def preflight():
            # Every socket and HTTPS operation runs outside the Qt GUI thread.
            check_bind(gateway, runtime["dnp3"]["port"])
            gateway_program = self._executable(gateway_path, "edgecs_gateway")
            simulator_program = self._executable(simulator_path, "edgecs_bess_sim")
            registered = api.devices()
            previous_registration = None
            for device in registered:
                same_id = device.get("device_id") == runtime["device_id"]
                endpoint = device.get("dnp3", {})
                same_endpoint = endpoint.get("host") == gateway and endpoint.get("port") == runtime["dnp3"]["port"]
                if same_id:
                    # Bind and the local broker/device lock establish that this
                    # endpoint is available. Preserve idempotent restarts while
                    # refusing an existing active device or a changed mapping.
                    state = device.get("connection", {}).get("state", "unknown")
                    identical = self._matches_config(device, runtime)
                    if not identical or state == "open":
                        raise ConfigError(f'device_id déjà utilisé dans le Master : {runtime["device_id"]} (DNP3 {state})')
                    previous_registration = device.get("last_registration_at", device.get("registered_at"))
                elif same_endpoint:
                    raise ConfigError(f'Endpoint DNP3 {gateway}:{runtime["dnp3"]["port"]} déjà enregistré pour {device.get("device_id", "?")}')
            return gateway_program, simulator_program, previous_registration

        def ready(programs):
            if generation != self._generation or not self._active or self._stopping or self._closing:
                return
            self._programs = programs[:2]
            self._previous_registration = programs[2]
            self._preflight_ready = True
            self.registration.setText("API joignable · identité disponible")
            self.state.setText("Attente du broker MQTT (CONNACK + abonnement)…")
            self._deadline = time.monotonic() + self.START_TIMEOUT
            self.timer.start()
            self.mqtt.start(runtime["mqtt"]["host"], runtime["mqtt"]["port"])

        def failed(message):
            if generation == self._generation and self._active and not self._stopping:
                self._abort("Préparation impossible : " + message)

        run_job(self.pool, preflight, ready, failed)

    @staticmethod
    def _matches_config(device, runtime):
        fields = ("schema_version", "device_id", "name", "der_type", "dnp3", "mqtt", "master_api_host", "master_api_port", "points")
        return all(device.get(key) == runtime.get(key) for key in fields if key in runtime)

    @staticmethod
    def _executable(override, name):
        if override:
            candidate = Path(override).expanduser().resolve()
            if not candidate.is_file() or not os.access(candidate, os.X_OK):
                raise ConfigError(f"Exécutable introuvable ou non exécutable : {candidate}")
            return str(candidate)
        return str(find_executable(name))

    def _mqtt_connection(self, connected, message):
        # A Paho signal queued immediately before Stop may arrive during a new
        # start. Confirm readiness belongs to the currently installed client.
        self._mqtt_ready = bool(connected and self.mqtt.is_connected())
        self.mqtt_state.setText(("Connectée · " if self._mqtt_ready else "Déconnectée · ") + str(message))
        self._log("MQTT supervision : " + str(message))
        if self._mqtt_ready and self._preflight_ready and self._active and not self._stopping and not self._closing and not self._gateway_started:
            self._gateway_started = True
            self.gateway_state.setText("Démarrage…")
            self.registration.setText("Attente de l'enregistrement de la Gateway…")
            self.state.setText("Démarrage Gateway · attente HTTPS et canal DNP3 ouvert…")
            self.gateway.start(self._programs[0], [str(self._temporary.path)], self._process_env)

    def _process_started(self, name):
        if name == "Gateway":
            self.gateway_state.setText("En cours")
        else:
            self.simulator_state.setText("En cours · attente MQTT")
        self._log(name + " : processus démarré")
        if self._stopping:
            (self.gateway if name == "Gateway" else self.simulator).stop()

    def _tick(self):
        if not self._active or self._stopping:
            return
        now = time.monotonic()
        if not self._simulator_ready and now >= self._deadline:
            if not self._mqtt_ready:
                reason = "Broker MQTT inaccessible ou abonnement non confirmé"
            elif not self._simulator_started:
                reason = "Gateway non opérationnelle : enregistrement HTTPS et ouverture DNP3 non confirmés"
            else:
                reason = "Simulateur : connexion MQTT et abonnement aux commandes non confirmés"
            self._abort(reason + " (délai de démarrage expiré)")
            return
        for request_id, (point, sent_at) in list(self._pending.items()):
            if now - sent_at >= self.IPC_TIMEOUT:
                self._pending.pop(request_id, None)
                self._show_failure(f"Délai IPC expiré pour {point} : état interne non confirmé")
        if self._gateway_started and not self._poll_busy:
            self._poll_device()

    def _poll_device(self):
        generation = self._generation
        self._poll_busy = True
        device_id = self._runtime["device_id"]
        api = self._api

        def received(device):
            if generation != self._generation:
                return
            self._poll_busy = False
            if not self._active or self._stopping or self._closing:
                return
            if not self._matches_config(device, self._runtime):
                self._abort("device_id enregistré avec une autre configuration pendant le démarrage")
                return
            registration_at = device.get("last_registration_at", device.get("registered_at"))
            registration_current = bool(registration_at) and registration_at != self._previous_registration
            self.registration.setText("Enregistrée · HTTPS authentifié" if registration_current else
                                      "Configuration existante · attente du renouvellement HTTPS de la Gateway")
            connection = device.get("connection", {})
            state = connection.get("state", "unknown")
            self.dnp3.setText(f'{state} · {connection.get("updated_at", "heure inconnue")}')
            latest = device.get("latest_telemetry", {})
            dates = [str(v.get("received_at", v.get("timestamp", ""))) for v in latest.values() if isinstance(v, dict)]
            self.last_telemetry.setText(max(dates) if dates else "Aucune lecture DNP3 reçue")
            if state == "open" and registration_current and not self._simulator_started:
                if not self.gateway.is_running():
                    self._abort("La Gateway s'est arrêtée avant le démarrage du simulateur")
                    return
                self._simulator_started = True
                self.state.setText("Gateway enregistrée · canal DNP3 ouvert · démarrage du simulateur…")
                self.simulator_state.setText("Démarrage…")
                self._deadline = time.monotonic() + self.START_TIMEOUT
                self.simulator.start(self._programs[1], [str(self._temporary.path), "--gui"], self._process_env)
            elif self._simulator_ready:
                if state == "open":
                    self.state.setText("En cours · canal DNP3 ouvert · valeurs internes simulées")
                else:
                    self.state.setText(f"Communication DNP3 interrompue ou indisponible : {state}")

        def failed(message):
            if generation != self._generation:
                return
            self._poll_busy = False
            if not self._active or self._stopping or self._closing:
                return
            self.registration.setText("API Master non vérifiée : " + message)
            self.dnp3.setText("Inconnue · API inaccessible")
            if self._simulator_started:
                self.state.setText("Master/API inaccessible · processus locaux conservés")

        run_job(self.pool, lambda: api.device(device_id), received, failed)

    def _output(self, source, line):
        # QProcess can split a JSON line anywhere, including inside UTF-8 text.
        # ManagedProcess decodes UTF-8; retain incomplete lines here until the
        # newline arrives. Bound partial logs from misbehaving executables.
        buffered = self._output_buffers[source] + line
        lines = buffered.split("\n")
        self._output_buffers[source] = lines.pop()
        for complete in lines:
            self._output_line(source, complete.rstrip("\r"))
        if len(self._output_buffers[source]) > 1024 * 1024:
            self._log(source + " · sortie sans fin de ligne tronquée")
            self._output_buffers[source] = ""

    def _output_line(self, source, line):
        # The explicit simulator prefix is the only source of local values and
        # command events; broker traffic never overwrites this internal state.
        if source == "Simulateur" and line.startswith("EDGECS_GUI "):
            try:
                event = json.loads(line[len("EDGECS_GUI "):])
                if not isinstance(event, dict):
                    raise ValueError("objet JSON attendu")
                if self._runtime and event.get("device_id") != self._runtime["device_id"]:
                    raise ValueError("device_id IPC différent de cette instance")
                self._simulator_event(event)
            except (ValueError, TypeError, KeyError) as error:
                self._log("IPC simulateur invalide : " + str(error))
        else:
            self._log(source + " · " + line)

    def _simulator_event(self, event):
        kind = event.get("kind")
        if kind == "snapshot":
            self._pending.pop(event.get("request_id"), None)
            for measurement in event.get("measurements", []):
                self._measurement(measurement)
        elif kind == "measurement":
            self._measurement(event)
        elif kind == "command_result":
            point = self._command_points.get(event.get("point"))
            if not point:
                self._log("Commande IPC ignorée : point inconnu de cette configuration")
                return
            self._append_history([
                event.get("received_at", event.get("timestamp", "")), point["name"],
                f'{point["dnp3_type"]}[{point["index"]}]', self._value_text(event.get("value")),
                ("Acceptée par la simulation" if event.get("status") == "accepted_by_simulator" else event.get("status", "Inconnu")) +
                (" · écho simulé" if event.get("feedback_simulated") else ""), event.get("request_id", ""),
            ])
            self._log(f'Commande reçue par le simulateur : {point["name"]} = {self._value_text(event.get("value"))} · {event.get("status", "inconnu")}')
        elif kind == "status":
            ready = bool(event.get("mqtt_connected") and event.get("mqtt_subscribed"))
            self._simulator_ready = ready
            self.simulator_mqtt.setText(f'{event.get("state", "inconnu")} · {event.get("message", "")}')
            self._enable_measurement_actions(ready and self._active and not self._stopping)
            if ready:
                self._simulator_was_ready = True
                self.simulator_state.setText("En cours · MQTT abonné")
                self.state.setText("En cours · valeurs internes simulées · lecture DNP3 manuelle au Master")
            elif self._active and not self._stopping:
                self.simulator_state.setText("En cours · MQTT non confirmé")
                if event.get("state") == "disconnected":
                    self.state.setText("MQTT simulateur interrompu · reconnexion en cours")
                    # A subsequent disconnection is a communication fault, not a
                    # new failed startup; leave processes alive for reconnect.
                    if self._simulator_was_ready:
                        self._deadline = float("inf")
            self._log("Simulateur MQTT : " + str(event.get("message", event.get("state", ""))))
        elif kind == "error":
            self._pending.pop(event.get("request_id"), None)
            message = f'Simulateur ({event.get("op", "IPC")} / {event.get("point", "—")}) : {event.get("message", "erreur inconnue")}'
            self._show_failure(message)
            if event.get("op") == "command":
                point = self._command_points.get(event.get("point"), {})
                self._append_history([event.get("timestamp", ""), event.get("point", "—"),
                                      f'{point.get("dnp3_type", "?")}[{point.get("index", "?")}]',
                                      "—", "Refusée : " + event.get("message", "erreur"), event.get("request_id", "")])

    def _measurement(self, measurement):
        name = measurement.get("point")
        row = self._measurement_rows.get(name)
        if row is None:
            return
        value = measurement.get("value")
        self.measurements.item(row, 3).setText(self._value_text(value))
        self.measurements.item(row, 5).setText(str(measurement.get("updated_at", measurement.get("timestamp", "—"))))
        sources = {"initial": "Initialisation simulateur", "manual": "Modification manuelle", "feedback": "Écho simulé"}
        source = measurement.get("source", "simulateur")
        self.measurements.item(row, 6).setText(sources.get(source, source))
        request_id = measurement.get("request_id")
        if request_id in self._pending:
            self._pending.pop(request_id, None)
            self._log(f"État interne confirmé par le simulateur : {name} = {self._value_text(value)}")

    @staticmethod
    def _value_text(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _append_history(self, values):
        if self.history.rowCount() >= 500:
            self.history.removeRow(0)
        row = self.history.rowCount()
        self.history.insertRow(row)
        for column, value in enumerate(values):
            self.history.setItem(row, column, QTableWidgetItem(str(value)))
        self.history.scrollToBottom()

    def _enable_measurement_actions(self, enabled):
        self.snapshot_button.setEnabled(enabled)
        for button in self._apply_buttons:
            button.setEnabled(enabled)

    def _set_measurement(self, point, editor):
        if not self._active or self._stopping or not self.simulator.is_running() or not self._simulator_ready:
            return
        try:
            value = editor_value(editor)
            validate_value(point, value)
            request_id = str(uuid.uuid4())
            self.simulator.write_line(json.dumps({"op": "set", "point": point["name"], "value": value,
                                                 "request_id": request_id}, allow_nan=False))
            self._pending[request_id] = (point["name"], time.monotonic())
            self._log(f'Demande de modification envoyée au simulateur : {point["name"]} = {self._value_text(value)}')
        except Exception as error:
            self._show_failure("Valeur refusée : " + str(error))

    def _request_snapshot(self):
        if self.simulator.is_running() and not self._stopping:
            try:
                request_id = str(uuid.uuid4())
                self.simulator.write_line(json.dumps({"op": "snapshot", "request_id": request_id}))
                self._pending[request_id] = ("instantané du simulateur", time.monotonic())
            except Exception as error:
                self._show_failure("État interne indisponible : " + str(error))

    def _process_error(self, name, message):
        self._log(name + " : " + message)
        if self._active and not self._stopping:
            self._abort(name + " : " + message)

    def _process_exited(self, name, code):
        tail = self._output_buffers[name]
        self._output_buffers[name] = ""
        if tail:
            self._output_line(name, tail)
        label = self.gateway_state if name == "Gateway" else self.simulator_state
        label.setText(f"Arrêté · code {code}")
        self._log(f"{name} terminé · code {code}")
        if self._active and not self._stopping:
            self._abort(f"Processus C++ {name} terminé de façon inattendue (code {code})")
        elif self._stopping:
            self._finish_stop()

    def _show_failure(self, message):
        self.state.setText("Erreur · " + message)
        self.state.setToolTip(message)
        self._log("ERREUR · " + message)

    def _abort(self, message):
        self._failure = message
        self._show_failure(message)
        self._stop()

    def _stop(self):
        if self._stopping:
            return
        self._stopping = True
        self._generation += 1
        self._poll_busy = False
        self.timer.stop()
        self._enable_measurement_actions(False)
        self.stop_button.setEnabled(False)
        self.state.setText("Arrêt des processus de cette DER…")
        self.mqtt.stop()
        # Each supervisor signals only its own child; never stop the shared
        # broker, Master, or any child created by another DER application.
        self.simulator.stop()
        self.gateway.stop()
        self.stop_timer.start()
        self._finish_stop()

    def _finish_stop(self):
        if not self._stopping or self.gateway.is_running() or self.simulator.is_running():
            return
        self.stop_timer.stop()
        self._cleanup_resources()
        self._active = False
        self._stopping = False
        self._gateway_started = False
        self._simulator_started = False
        self._simulator_ready = False
        self._simulator_was_ready = False
        self._mqtt_ready = False
        self._preflight_ready = False
        self._pending.clear()
        self.settings.setEnabled(True)
        self.start_button.setEnabled(bool(self._config))
        self.stop_button.setEnabled(False)
        self.registration.setText("Gateway arrêtée · registre Master éventuellement conservé")
        self.dnp3.setText("Non supervisée · processus locaux arrêtés")
        self.mqtt_state.setText("Arrêtée")
        self.simulator_mqtt.setText("Arrêté")
        self.gateway_state.setText("Arrêtée")
        self.simulator_state.setText("Arrêté")
        if self._failure:
            self.state.setText("Erreur · " + self._failure)
        else:
            self.state.setText("Arrêtée · dernières valeurs internes conservées à l'écran")
        if self._closing:
            QTimer.singleShot(0, self.close)

    def _cleanup_resources(self):
        if self._temporary:
            self._temporary.cleanup()
            self._temporary = None
        if self._lock:
            self._lock.release()
            self._lock = None

    def closeEvent(self, event):
        if self._active or self.gateway.is_running() or self.simulator.is_running():
            self._closing = True
            event.ignore()
            self._stop()
        else:
            self._generation += 1
            self.mqtt.stop()
            self._cleanup_resources()
            event.accept()

    def cleanup(self):
        """Exit fallback; normal close uses the asynchronous stop state machine."""
        self.mqtt.cleanup()
        self.simulator.cleanup()
        self.gateway.cleanup()
        self._cleanup_resources()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EDGECS DER")
    style(app)
    window = DerWindow()
    app.aboutToQuit.connect(window.cleanup)
    window.show()
    if len(sys.argv) > 1:
        window.load_configuration(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
