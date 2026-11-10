#!/usr/bin/env python3
"""Qt laboratory supervisor for the existing C++ DERMS Master."""
import ipaddress
import json
import os
from pathlib import Path
import ssl
import sys
import time

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from common.api_client import ApiClient
from common.config import (
    DeviceLock, check_bind, envelope, find_executable, validate_ipv4,
    validate_port, validate_value,
)
from common.lab import load_lab_settings, prepare_lab
from common.mqtt_client import MqttClient
from common.process_manager import ManagedProcess
from common.widgets import (
    editor_value, fill_table, log_append, make_table, run_job, style, value_editor,
)


class MasterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EDGECS · Master — laboratoire")
        self.resize(1320, 930)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.process = ManagedProcess(self)
        self.process.output.connect(lambda text: self.log("Master · " + text))
        self.process.error.connect(self._process_error)
        self.process.exited.connect(self._exited)
        # The legacy executable asks for its bind IP; an empty answer uses EDGECS_API_HOST.
        self.process.started.connect(lambda: self.process.write_line(""))
        self.mqtt = MqttClient(self, client_prefix="master-gui")
        self.mqtt.connected.connect(self._mqtt_status)
        self.mqtt.error.connect(self.log)
        self.mqtt.message.connect(self._message)
        self.devices = {}
        self.selected_id = None
        self.pending = {}
        self.results = []
        self.command_editors = {}
        self._rendered_points = None
        self.api = None
        self._busy = False
        self._starting = False
        self._stopping = False
        self._closed = False
        self._mqtt_ready = False
        self._generation = 0
        self._last_api_error = ""
        self._deadline = 0
        self._lock = None
        self._failure = ""
        self._preparing = False
        self._engine_mqtt = False
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    @staticmethod
    def _port(value):
        field = QSpinBox()
        field.setRange(1, 65535)
        field.setValue(int(value))
        return field

    def _path_field(self, value, title, secret=False):
        field = QLineEdit(value)
        if secret:
            field.setEchoMode(QLineEdit.EchoMode.Password)
            return field, field
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(field)
        browse = QPushButton("Parcourir…")
        def choose():
            filename, _ = QFileDialog.getOpenFileName(self, title, field.text())
            if filename:
                field.setText(filename)
        browse.clicked.connect(choose)
        layout.addWidget(browse)
        return field, container

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("EDGECS  /  MASTER")
        title.setStyleSheet("font-size: 23px; font-weight: 700; color: #164e7d; padding: 5px;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Essais de DER simulées · acquisition DNP3 manuelle · dernières valeurs connues"))
        top = QHBoxLayout()
        self.network_box = QGroupBox("Démarrage du serveur")
        form = QFormLayout(self.network_box)
        self.host = QLineEdit(os.environ.get("EDGECS_API_HOST", "127.0.0.1"))
        self.api_port = self._port(os.environ.get("EDGECS_API_PORT", "8443"))
        self.mqtt_host = QLineEdit(os.environ.get("MQTT_HOST", "127.0.0.1"))
        self.mqtt_port = self._port(os.environ.get("MQTT_PORT", "1883"))
        form.addRow("IPv4 locale du Master", self.host)
        form.addRow("Port HTTPS", self.api_port)
        form.addRow("Broker MQTT externe", self.mqtt_host)
        form.addRow("Port MQTT", self.mqtt_port)
        top.addWidget(self.network_box, 1)
        self.security_box = QGroupBox("Accès HTTPS vérifiés")
        security = QFormLayout(self.security_box)
        saved = load_lab_settings()
        self.token, token_widget = self._path_field(saved["token"], "Jeton", True)
        self.cert, cert_widget = self._path_field(saved["cert"], "Certificat serveur")
        self.key, key_widget = self._path_field(saved["key"], "Clé privée")
        self.ca, ca_widget = self._path_field(saved["ca"], "Autorité de confiance")
        security.addRow("Jeton partagé", token_widget)
        security.addRow("Certificat serveur", cert_widget)
        security.addRow("Clé privée", key_widget)
        security.addRow("CA de confiance", ca_widget)
        self.prepare_button = QPushButton("Créer / charger les accès locaux du laboratoire")
        self.prepare_button.clicked.connect(self._prepare)
        security.addRow(self.prepare_button)
        top.addWidget(self.security_box, 2)
        layout.addLayout(top)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Démarrer le Master")
        self.start_button.setProperty("primary", True)
        self.start_button.clicked.connect(self.start_master)
        self.stop_button = QPushButton("Arrêter le Master")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_master)
        self.status_label = QLabel("Serveur : arrêté")
        self.mqtt_label = QLabel("MQTT interface : arrêté")
        self.count_label = QLabel("DER enregistrées : 0 · canaux DNP3 ouverts : 0")
        for widget in (self.start_button, self.stop_button, self.status_label, self.mqtt_label):
            actions.addWidget(widget)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(self.count_label)
        split = QSplitter(Qt.Orientation.Vertical)
        self.device_table = make_table([
            "Identifiant", "Nom", "Type", "IP DNP3", "Port", "Adresse Outstation",
            "Canal DNP3", "Dernière mesure reçue",
        ])
        self.device_table.itemSelectionChanged.connect(self._select_device)
        split.addWidget(self.device_table)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.details_label = QLabel("Aucune DER sélectionnée. Les enregistrements apparaissent automatiquement.")
        self.details_label.setWordWrap(True)
        detail_layout.addWidget(self.details_label)
        tabs = QTabWidget()
        telemetry = QWidget()
        telemetry_layout = QVBoxLayout(telemetry)
        row = QHBoxLayout()
        self.read_button = QPushButton("Lire les mesures")
        self.read_button.setEnabled(False)
        self.read_button.clicked.connect(self.read_measurements)
        row.addWidget(self.read_button)
        row.addWidget(QLabel("Valeurs mémorisées, horodatées à leur réception par le Master."))
        row.addStretch()
        telemetry_layout.addLayout(row)
        self.telemetry_table = make_table(["Point", "Alias", "Type", "Index", "Dernière valeur connue", "Unité", "Reçue le"])
        telemetry_layout.addWidget(self.telemetry_table)
        tabs.addTab(telemetry, "Mesures et états · AI / BI")
        commands = QWidget()
        command_layout = QVBoxLayout(commands)
        note = QLabel("Acceptation DNP3 et exécution physique sont distinctes. Le retour de mesure exige une lecture.\n"
                      "feedback_point représente ici un écho simulé, sans modèle physique.")
        note.setWordWrap(True)
        command_layout.addWidget(note)
        self.command_scroll = QScrollArea()
        self.command_scroll.setWidgetResizable(True)
        command_layout.addWidget(self.command_scroll)
        tabs.addTab(commands, "Commandes · AO / BO")
        self.history = make_table(["Heure", "DER", "Point", "Valeur", "État / résultat", "request_id"])
        tabs.addTab(self.history, "Résultats et délais")
        detail_layout.addWidget(tabs)
        split.addWidget(detail)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.document().setMaximumBlockCount(1800)
        split.addWidget(self.logs)
        split.setSizes([200, 370, 130])
        layout.addWidget(split, 1)
        self.setCentralWidget(root)

    def log(self, message):
        log_append(self.logs, message)

    def _prepare(self):
        try:
            host = validate_ipv4(self.host.text().strip())
        except Exception as error:
            self.fail(str(error))
            return
        generation = self._generation
        self._preparing = True
        self.start_button.setEnabled(False)
        self.security_box.setEnabled(False)
        self.network_box.setEnabled(False)
        def unlock():
            self._preparing = False
            if not self._closed and generation == self._generation:
                self.start_button.setEnabled(True)
                self.security_box.setEnabled(True)
                self.network_box.setEnabled(True)
        def ready(settings):
            unlock()
            if self._closed or generation != self._generation:
                return
            for name in ("token", "cert", "key", "ca"):
                getattr(self, name).setText(settings[name])
            self.log("Accès locaux prêts. Les DER App lancées sur cette machine les chargeront automatiquement.")
        def failed(message):
            unlock()
            if self._closed or generation != self._generation:
                return
            self.fail(message)
        run_job(self.pool, lambda: prepare_lab(host), ready, failed)

    def fail(self, message):
        self.status_label.setText("Erreur : " + message)
        self.log("ERREUR · " + message)

    def start_master(self):
        if self._preparing or self._starting or self.process.is_running():
            return
        try:
            host = validate_ipv4(self.host.text().strip())
            address = ipaddress.IPv4Address(host)
            if not (address.is_private or address.is_loopback) or address.is_unspecified:
                raise ValueError("Utilisez une IPv4 locale privée pour le Master de laboratoire.")
            port = validate_port(self.api_port.value())
            broker = validate_ipv4(self.mqtt_host.text().strip())
            broker_port = validate_port(self.mqtt_port.value())
            token = self.token.text()
            if len(token) < 16:
                raise ValueError("Jeton requis (16 caractères minimum). Créez les accès locaux ou configurez EDGECS_REGISTRATION_TOKEN.")
            paths = {name: str(Path(getattr(self, name).text()).expanduser().resolve()) for name in ("cert", "key", "ca")}
            for path in paths.values():
                if not Path(path).is_file():
                    raise ValueError("Fichier TLS introuvable : " + path)
            env = dict(os.environ, EDGECS_API_HOST=host, EDGECS_API_PORT=str(port),
                       MQTT_HOST=broker, MQTT_PORT=str(broker_port),
                       EDGECS_REGISTRATION_TOKEN=token, EDGECS_TLS_CERT=paths["cert"],
                       EDGECS_TLS_KEY=paths["key"], EDGECS_CA_CERT=paths["ca"])
            program = find_executable("edgecs_master")
            lock = DeviceLock(broker, broker_port, "__edgecs_master_gui__")
            lock.acquire()
            self._lock = lock
        except Exception as error:
            self.fail(str(error))
            return
        self._generation += 1
        generation = self._generation
        self._starting = True
        self._failure = ""
        self._busy = False
        self._engine_mqtt = False
        self._last_api_error = ""
        self._stopping = False
        self._deadline = time.monotonic() + 30
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.network_box.setEnabled(False)
        self.security_box.setEnabled(False)
        self.status_label.setText("Vérification des ports et de TLS…")
        def preflight():
            check_bind(host, port)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(paths["cert"], paths["key"])
            return ApiClient(host, port, token=token, ca_cert=paths["ca"])
        def ready(api):
            if generation != self._generation or self._closed:
                return
            self.api = api
            self._launch = (program, env)
            self.status_label.setText("Connexion au broker MQTT…")
            self.mqtt.start(broker, broker_port)
        def failed(message):
            if generation == self._generation:
                self._abort(message)
        run_job(self.pool, preflight, ready, failed)

    def _mqtt_status(self, connected, message):
        if connected != self.mqtt.is_connected():
            return  # Ignore an old callback queued before a stop/restart.
        self._mqtt_ready = connected
        self.mqtt_label.setText("MQTT interface : " + ("connectée" if connected else "déconnectée"))
        self.log(message)
        if connected and self._starting and not self.process.is_running() and hasattr(self, "_launch"):
            program, env = self._launch
            del self._launch
            self.status_label.setText("Démarrage du moteur C++ et attente HTTPS…")
            self.process.start(program, [], env)
        self._update_actions()

    def _tick(self):
        if self._closed:
            return
        now = time.monotonic()
        for request, entry in list(self.pending.items()):
            if now - entry["sent_at"] > 18:
                entry["status"] = "Délai expiré · résultat inconnu"
                self.pending.pop(request, None)
                self.log(f"Délai expiré · {entry['device']} / {entry['point']} · {request}")
                self._history()
        if self._starting and now > self._deadline:
            self._abort("Délai de démarrage dépassé. " + self._last_api_error)
            return
        if self.api is None or self._busy or not self.process.is_running() or self._stopping:
            return
        self._busy = True
        generation = self._generation
        api = self.api
        def fetch():
            return api.devices(), api.health()
        def success(result):
            if generation != self._generation or self._closed:
                return
            self._busy = False
            descriptors, health = result
            self._last_api_error = ""
            self._starting = False
            self.status_label.setText("Master démarré · HTTPS vérifié")
            engine_mqtt = health.get("mqtt_connected")
            self._engine_mqtt = engine_mqtt is True
            if engine_mqtt is not None:
                self.mqtt_label.setText("MQTT interface : " + ("connectée" if self._mqtt_ready else "déconnectée") +
                                        " · moteur : " + ("connecté" if engine_mqtt else "déconnecté"))
            self._refresh_devices(descriptors)
        def failed(message):
            if generation != self._generation or self._closed:
                return
            self._busy = False
            if message != self._last_api_error:
                self.log("HTTPS · " + message)
            self._last_api_error = message
            if not self._starting:
                self.status_label.setText("Master HTTPS inaccessible : " + message)
                self.read_button.setEnabled(False)
                for _, button in self.command_editors.values():
                    button.setEnabled(False)
        run_job(self.pool, fetch, success, failed)

    def _refresh_devices(self, descriptors):
        previous = set(self.devices)
        self.devices = {item["device_id"]: item for item in descriptors}
        for device in set(self.devices) - previous:
            self.log("DER enregistrée : " + device)
        selected = self.selected_id
        self.device_table.blockSignals(True)
        rows = []
        identifiers = sorted(self.devices)
        for device in identifiers:
            info = self.devices[device]
            last = max((m.get("received_at", m.get("timestamp", "")) for m in info.get("latest_telemetry", {}).values()), default="—")
            rows.append([device, info["name"], info["der_type"], info["dnp3"]["host"], info["dnp3"]["port"],
                         info["dnp3"]["outstation_address"], info.get("connection", {}).get("state", "inconnu"), last])
        fill_table(self.device_table, rows)
        if selected in identifiers:
            self.device_table.selectRow(identifiers.index(selected))
        elif identifiers:
            selected = identifiers[0]
            self.device_table.selectRow(0)
        else:
            selected = None
        self.device_table.blockSignals(False)
        self.selected_id = selected
        connected = sum(item.get("connection", {}).get("state") == "open" for item in self.devices.values())
        self.count_label.setText(f"DER enregistrées : {len(self.devices)} · canaux DNP3 ouverts : {connected} · "
                                 f"https://{self.host.text()}:{self.api_port.value()}")
        self._show_details()

    def _select_device(self):
        row = self.device_table.currentRow()
        item = self.device_table.item(row, 0)
        self.selected_id = item.text() if item else None
        self._show_details()

    def _show_details(self):
        info = self.devices.get(self.selected_id)
        if info is None:
            self.details_label.setText("Aucune DER enregistrée. Le Master attend les enregistrements HTTPS.")
            fill_table(self.telemetry_table, [])
            self._render_commands(None)
            self._update_actions()
            return
        connection = info.get("connection", {})
        self.details_label.setText(f"{info['device_id']} · {info['name']} · {info['der_type']}\n"
                                  f"Enregistrée : {info.get('registered_at', '—')} · canal TCP/DNP3 : {connection.get('state', 'inconnu')} "
                                  f"(état depuis {connection.get('updated_at', '—')}) · adresses logiques "
                                  f"Master {info['dnp3']['master_address']} / Outstation {info['dnp3']['outstation_address']}")
        latest = info.get("latest_telemetry", {})
        rows = []
        for point in info["points"]:
            if point["direction"] != "telemetry":
                continue
            measurement = latest.get(point["name"], {})
            rows.append([point["name"], point.get("alias", "—"), point["dnp3_type"], point["index"],
                         json.dumps(measurement["value"], ensure_ascii=False) if "value" in measurement else "Non reçue",
                         point["unit"], measurement.get("received_at", measurement.get("timestamp", "—"))])
        fill_table(self.telemetry_table, rows)
        self._render_commands(info)
        self._update_actions()

    def _render_commands(self, info):
        signature = None if info is None else (info["device_id"], json.dumps(info["points"], sort_keys=True))
        if signature == self._rendered_points:
            return
        self._rendered_points = signature
        container = QWidget()
        layout = QVBoxLayout(container)
        self.command_editors.clear()
        if info:
            for point in info["points"]:
                if point["direction"] != "command":
                    continue
                group = QGroupBox(point.get("alias", point["name"]))
                row = QHBoxLayout(group)
                description = f"{point['name']} · {point['dnp3_type']}[{point['index']}]"
                if point["dnp3_type"] == "AO":
                    description += f" · {point['min']} à {point['max']} {point['unit']}"
                if point.get("feedback_point"):
                    description += " · écho simulé → " + point["feedback_point"]
                label = QLabel(description)
                label.setWordWrap(True)
                row.addWidget(label, 1)
                editor = value_editor(point)
                row.addWidget(editor)
                button = QPushButton("Envoyer")
                device = info["device_id"]
                button.clicked.connect(lambda checked=False, d=device, p=point, e=editor: self._send_editor(d, p, e))
                row.addWidget(button)
                self.command_editors[point["name"]] = (editor, button)
                layout.addWidget(group)
        layout.addStretch()
        old = self.command_scroll.takeWidget()
        if old:
            old.deleteLater()
        self.command_scroll.setWidget(container)

    def _update_actions(self):
        info = self.devices.get(self.selected_id, {})
        usable = bool(self.process.is_running() and self._mqtt_ready and self._engine_mqtt and not self._starting and
                      not self._stopping and not self._last_api_error and info.get("connection", {}).get("state") == "open")
        self.read_button.setEnabled(usable)
        for _, button in self.command_editors.values():
            button.setEnabled(usable)

    def _track(self, message):
        definition = next((point for point in self.devices.get(message["device_id"], {}).get("points", [])
                           if point["name"] == message["point"]), {})
        entry = dict(device=message["device_id"], point=message["point"], value=message["value"],
                     request=message["request_id"], timestamp=message["timestamp"],
                     kind=message["kind"], feedback=definition.get("feedback_point"),
                     sent_at=time.monotonic(), status="Envoyée · attente du moteur C++")
        self.results.append(entry)
        if len(self.results) > 300:
            removed = self.results.pop(0)
            self.pending.pop(removed["request"], None)
        self.pending[entry["request"]] = entry
        self._history()

    def _history(self):
        fill_table(self.history, [[e["timestamp"], e["device"], e["point"], json.dumps(e["value"]),
                                  e["status"] + e.get("feedback_text", ""), e["request"]]
                                  for e in reversed(self.results)])

    def send_command(self, device, point, value):
        try:
            validate_value(point, value)
            if self.devices.get(device, {}).get("connection", {}).get("state") != "open":
                raise ValueError("Canal DNP3 fermé : commande non envoyée.")
            message = envelope(device, point["name"], value, "command")
            if not self.mqtt.publish(f"edgecs/{device}/command", message):
                raise ValueError("MQTT indisponible : commande non envoyée.")
            self._track(message)
            self.log(f"Commande envoyée · {device} / {point['name']} = {value} · {message['request_id']}")
        except Exception as error:
            self.log("Commande refusée · " + str(error))

    def _send_editor(self, device, point, editor):
        try:
            value = editor_value(editor)
        except ValueError as error:
            self.log("Commande refusée · " + str(error))
            return
        self.send_command(device, point, value)

    def read_measurements(self):
        if not self.selected_id:
            return
        message = envelope(self.selected_id, "*", None, "read")
        if self.mqtt.publish(f"edgecs/{self.selected_id}/read", message):
            self._track(message)
            self.log("Lecture Class 0 demandée · " + self.selected_id)
        else:
            self.log("Lecture impossible : MQTT déconnecté.")

    def _message(self, topic, message):
        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != "edgecs" or parts[2] not in ("telemetry", "command_result", "read_result"):
            return
        if not isinstance(message, dict):
            self.log("Message MQTT ignoré : objet JSON attendu.")
            return
        required = ("device_id", "point", "kind", "request_id", "timestamp")
        if (type(message.get("schema_version")) is not int or message["schema_version"] != 1 or
                any(not isinstance(message.get(field), str) or not message[field] for field in required) or
                "value" not in message or message["device_id"] != parts[1] or message["kind"] != parts[2]):
            self.log("Message MQTT ignoré : enveloppe, version ou topic incohérent.")
            return
        device = message.get("device_id")
        if device not in self.devices:
            return
        if topic == f"edgecs/{device}/telemetry" and message.get("kind") == "telemetry":
            point = next((p for p in self.devices[device]["points"] if p["name"] == message.get("point") and p["direction"] == "telemetry"), None)
            if point is None:
                return
            try:
                validate_value(point, message.get("value"))
            except Exception as error:
                self.log("Télémesure invalide : " + str(error))
                return
            self.devices[device].setdefault("latest_telemetry", {})[point["name"]] = message
            for entry in self.results:
                if (entry["device"] == device and entry.get("feedback") == point["name"] and
                        message["timestamp"] >= entry["timestamp"]):
                    entry["feedback_text"] = (f" · retour connu après lecture : {message['value']} {point['unit']} "
                                               f"({message['timestamp']})")
            self._history()
            if device == self.selected_id:
                self._show_details()
            return
        if topic not in (f"edgecs/{device}/command_result", f"edgecs/{device}/read_result"):
            return
        entry = next((result for result in reversed(self.results) if result["request"] == message["request_id"]), None)
        if entry is None or entry["device"] != device:
            return
        if message["point"] != entry["point"] or message["kind"] != ("read_result" if entry["kind"] == "read" else "command_result"):
            self.log("Résultat MQTT ignoré : point ou type de requête incohérent.")
            return
        status = message.get("status", "résultat sans état")
        if not isinstance(status, str):
            self.log("Résultat MQTT ignoré : état non textuel.")
            return
        if status == "scan_requested" and entry["request"] not in self.pending:
            return
        labels = {"accepted_by_outstation": "Acceptée par DNP3 · exécution physique non confirmée · lire le retour",
                  "rejected_by_dnp3": "Refusée par DNP3", "rejected_by_master": "Refusée par le Master",
                  "scan_requested": "Lecture demandée · attente DNP3", "read_completed": "Lecture DNP3 terminée · dernières valeurs reçues",
                  "read_failed": "Échec de lecture DNP3"}
        entry["status"] = labels.get(status, status)
        if message.get("reason"):
            entry["status"] += " · " + str(message["reason"])
        if status != "scan_requested":
            self.pending.pop(entry["request"], None)
        self._history()
        self.log(f"{device} / {entry['point']} · {entry['status']}")

    def _abort(self, message):
        self._failure = message
        self.stop_master()
        self.fail(message)

    def _process_error(self, message):
        if not self._stopping:
            self._abort("Processus Master : " + message)

    def stop_master(self):
        self._generation += 1
        self._starting = False
        self._stopping = True
        self._busy = False
        self._engine_mqtt = False
        self.api = None
        self._mqtt_ready = False
        if hasattr(self, "_launch"):
            del self._launch
        self.mqtt.stop()
        for entry in self.pending.values():
            entry["status"] = "Master arrêté · résultat inconnu"
        self.pending.clear()
        self._history()
        self.process.stop()
        self._update_actions()
        if not self.process.is_running():
            self._reset_stopped()

    def _exited(self, code):
        expected = self._stopping
        if not expected:
            self._failure = f"Processus C++ terminé (code {code}). Consultez le journal."
        self.stop_master()

    def _reset_stopped(self):
        if self._lock is not None:
            self._lock.release()
            self._lock = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.network_box.setEnabled(True)
        self.security_box.setEnabled(True)
        self.status_label.setText("Erreur : " + self._failure if self._failure else "Serveur : arrêté")
        self.mqtt_label.setText("MQTT interface : arrêté")
        self.devices.clear()
        self.selected_id = None
        self._refresh_devices([])

    def closeEvent(self, event):
        self._closed = True
        self.timer.stop()
        self.stop_master()
        self.process.cleanup()
        self.mqtt.cleanup()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EDGECS Master")
    style(app)
    window = MasterWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
