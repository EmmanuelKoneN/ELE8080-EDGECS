"""Paho network callbacks forwarded to the Qt thread through signals."""

from __future__ import annotations

import json
import os
import threading
import uuid

import paho.mqtt.client as mqtt
from PySide6.QtCore import QObject, Signal

from .config import validate_ipv4, validate_port


_DEFAULT_TOPICS = tuple(
    f"edgecs/+/{suffix}" for suffix in (
        "telemetry", "command_result", "read_result", "edge/telemetry",
        "edge/command", "edge/simulation_result", "edge/simulation_control_result",
    )
)


class MqttClient(QObject):
    connected = Signal(bool, str)
    message = Signal(str, dict)
    error = Signal(str)

    def __init__(self, parent=None, client_prefix: str = "gui", topics=None):
        super().__init__(parent)
        self._prefix = client_prefix
        self._topics = tuple(_DEFAULT_TOPICS if topics is None else topics)
        self._client = None
        self._ready = False
        self._subscription_mid = None
        self._cleanup_threads = []

    def is_connected(self) -> bool:
        """True only after MQTT CONNECT and every requested SUBACK succeeded."""
        return self._ready

    def start(self, host: str, port=1883) -> None:
        host, port = validate_ipv4(host), validate_port(port)
        self.stop()
        self._cleanup_threads = [thread for thread in self._cleanup_threads if thread.is_alive()]
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"edgecs-{self._prefix}-{uuid.uuid4().hex}",
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        client.connect_timeout = 3.0
        client.reconnect_delay_set(min_delay=1, max_delay=8)
        username = os.environ.get("MQTT_USERNAME", "")
        if username:
            client.username_pw_set(username, os.environ.get("MQTT_PASSWORD", ""))
        client.on_connect = self._on_connect
        client.on_connect_fail = self._on_connect_fail
        client.on_disconnect = self._on_disconnect
        client.on_subscribe = self._on_subscribe
        client.on_message = self._on_message
        self._client = client
        self._ready = False
        self._subscription_mid = None
        self.connected.emit(False, f"Connexion MQTT a {host}:{port}...")
        try:
            client.connect_async(host, port, keepalive=20)
            result = client.loop_start()
            if result != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"demarrage reseau MQTT impossible : {result}")
        except Exception as exc:
            self.stop()
            self.error.emit(f"Broker MQTT inaccessible : {exc}")

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if client is not self._client:
            return
        self._ready = False
        self._subscription_mid = None
        if reason_code.is_failure:
            message = f"Connexion MQTT refusee : {reason_code}"
            self.connected.emit(False, message)
            self.error.emit(message)
            return
        if not self._topics:
            self._ready = True
            self.connected.emit(True, "MQTT connecte (aucun abonnement).")
            return
        result, mid = client.subscribe([(topic, 1) for topic in self._topics])
        if result != mqtt.MQTT_ERR_SUCCESS:
            message = f"Abonnements MQTT impossibles : {mqtt.error_string(result)}"
            self.connected.emit(False, message)
            self.error.emit(message)
            return
        self._subscription_mid = mid
        self.connected.emit(False, "MQTT connecte, attente de confirmation des abonnements...")

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties) -> None:
        if client is not self._client or mid != self._subscription_mid:
            return
        self._subscription_mid = None
        if len(reason_codes) != len(self._topics) or any(code.is_failure for code in reason_codes):
            self._ready = False
            message = "Le broker a refuse au moins un abonnement MQTT."
            self.connected.emit(False, message)
            self.error.emit(message)
            return
        self._ready = True
        self.connected.emit(True, "MQTT connecte, abonnements QoS 1 confirmes.")

    def _on_connect_fail(self, client, userdata) -> None:
        if client is self._client:
            self._ready = False
            message = "Broker MQTT inaccessible; nouvelle tentative automatique."
            self.connected.emit(False, message)
            self.error.emit(message)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        if client is not self._client:
            return
        self._ready = False
        self._subscription_mid = None
        self.connected.emit(False, f"Connexion MQTT interrompue : {reason_code}; reconnexion automatique.")

    def _on_message(self, client, userdata, packet) -> None:
        if client is not self._client:
            return
        try:
            if len(packet.payload) > 1024 * 1024:
                raise ValueError("message trop volumineux (limite : 1 Mio)")
            payload = json.loads(packet.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("objet JSON attendu")
            self.message.emit(packet.topic, payload)
        except (ValueError, UnicodeError) as exc:
            self.error.emit(f"Message MQTT invalide sur {packet.topic} : {exc}")

    def publish(self, topic: str, payload: dict) -> bool:
        client = self._client
        if client is None or not self._ready:
            self.error.emit("Publication refusee : MQTT et ses abonnements ne sont pas prets.")
            return False
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            result = client.publish(topic, body, qos=1, retain=False)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(mqtt.error_string(result.rc))
            return True
        except (ValueError, TypeError, RuntimeError) as exc:
            self.error.emit(f"Publication MQTT impossible : {exc}")
            return False

    def stop(self) -> None:
        client, self._client = self._client, None
        was_ready, self._ready = self._ready, False
        self._subscription_mid = None
        if client is None:
            return
        # disconnect is nonblocking. loop_stop joins Paho's network thread and
        # can wait for an in-flight connect, so run that join away from Qt.
        client.disconnect()
        thread = threading.Thread(target=client.loop_stop, name="edgecs-mqtt-stop", daemon=True)
        self._cleanup_threads.append(thread)
        thread.start()
        if was_ready:
            self.connected.emit(False, "MQTT arrete.")

    def cleanup(self, timeout: float = 3.5) -> None:
        """Final bounded network cleanup; normal UI actions should use stop()."""
        import time

        self.stop()
        deadline = time.monotonic() + max(0, timeout)
        for thread in self._cleanup_threads:
            thread.join(max(0, deadline - time.monotonic()))
        self._cleanup_threads = [thread for thread in self._cleanup_threads if thread.is_alive()]
