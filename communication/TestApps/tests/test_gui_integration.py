"""Exercise actual Qt windows, C++ engines, TLS, DNP3 and a private broker.

Run after compiling C++ and installing TestApps/requirements.txt:

    QT_QPA_PLATFORM=offscreen EDGECS_RUN_GUI_INTEGRATION=1 \
      TestApps/.venv/bin/python -m unittest discover -s TestApps/tests -v

Every service uses loopback and dynamically allocated ports. No existing broker
is used or stopped. Failure artifacts include each window's visible logs.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "TestApps"
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ENABLED = os.environ.get("EDGECS_RUN_GUI_INTEGRATION") == "1"


@unittest.skipUnless(ENABLED, "set EDGECS_RUN_GUI_INTEGRATION=1 for native GUI acceptance tests")
class GuiAcceptanceTests(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication
        from integration import Harness

        self.app = QApplication.instance() or QApplication([])
        self.app.setQuitOnLastWindowClosed(False)
        self.windows = []
        self.harness = Harness(ROOT, ROOT / "DERMS/build", ROOT / "Gateway/build", keep=False)
        self.environment = dict(os.environ)
        self.success = False
        try:
            self.harness.setup()
            os.environ.clear()
            os.environ.update(self.harness.env)
            os.environ.update(EDGECS_MASTER_BIN=str(ROOT / "DERMS/build/edgecs_master"),
                              EDGECS_GATEWAY_BIN=str(ROOT / "Gateway/build/edgecs_gateway"),
                              EDGECS_SIMULATOR_BIN=str(ROOT / "Gateway/build/edgecs_bess_sim"))
        except Exception:
            self.harness.cleanup(False)
            raise

    def tearDown(self):
        from PySide6.QtCore import QThreadPool

        for index, window in enumerate(self.windows):
            widget = getattr(window, "logs", None)
            if widget is None:
                widget = getattr(window, "log", None)
            if widget is not None:
                (self.harness.directory / f"window-{index}.log").write_text(widget.toPlainText())
        for window in reversed(self.windows):
            window.close()
            if hasattr(window, "cleanup"):
                window.cleanup()
            else:
                window.process.cleanup()
            window.mqtt.cleanup()
        self.pump(0.1)
        QThreadPool.globalInstance().waitForDone(8000)
        self.harness.cleanup(self.success)
        for process in self.harness.processes:
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
        os.environ.clear()
        os.environ.update(self.environment)

    def pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)

    def wait(self, predicate, label, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        descriptions = [getattr(window, "state", getattr(window, "status_label", None)).text()
                        for window in self.windows]
        self.fail(f"Timeout: {label}; visible states: {descriptions}")

    def master_window(self):
        from master_app import MasterWindow

        master = MasterWindow()
        self.windows.append(master)
        master.host.setText("127.0.0.1")
        master.api_port.setValue(self.harness.api_port)
        master.mqtt_host.setText("127.0.0.1")
        master.mqtt_port.setValue(self.harness.mqtt_port)
        master.token.setText(self.harness.token)
        master.cert.setText(str(self.harness.cert))
        master.key.setText(str(self.harness.key))
        master.ca.setText(str(self.harness.cert))
        return master

    def der_window(self, cfg):
        from der_app import DerWindow

        filename = self.harness.directory / f"gui-{cfg['device_id']}-{len(self.windows)}.json"
        filename.write_text(json.dumps(cfg, indent=2))
        der = DerWindow()
        self.windows.append(der)
        der.load_configuration(filename)
        self.assertIsNotNone(der._config)
        der.api_port.setValue(self.harness.api_port)
        der.mqtt_port.setValue(self.harness.mqtt_port)
        der.token.setText(self.harness.token)
        der.ca.setText(str(self.harness.cert))
        return der

    def select(self, master, device):
        rows = [master.device_table.item(index, 0).text() for index in range(master.device_table.rowCount())]
        master.device_table.selectRow(rows.index(device))
        self.app.processEvents()
        self.assertEqual(master.selected_id, device)

    def set_editor(self, editor, value):
        from PySide6.QtWidgets import QComboBox

        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(int(bool(value)))
        else:
            editor.setValue(value)

    def command(self, master, der, cfg, name, value):
        device = cfg["device_id"]
        self.select(master, device)
        editor, button = master.command_editors[name]
        self.assertTrue(button.isEnabled())
        self.set_editor(editor, value)
        previous = len(master.results)
        history = der.history.rowCount()
        button.click()
        self.assertEqual(len(master.results), previous + 1)
        result = master.results[-1]
        self.wait(lambda: result["request"] not in master.pending, "DNP3 command result")
        self.assertIn("Acceptée par DNP3", result["status"])
        self.wait(lambda: der.history.rowCount() > history, "simulator command acknowledgement")
        self.assertEqual(der.history.item(der.history.rowCount() - 1, 1).text(), name)
        return result

    def read(self, master, cfg, expected):
        device = cfg["device_id"]
        self.select(master, device)
        deadline = time.monotonic() + 15
        while True:
            self.assertTrue(master.read_button.isEnabled())
            master.read_button.click()
            result = master.results[-1]
            self.wait(lambda: result["request"] not in master.pending, "manual Class 0 result", timeout=10)
            self.assertIn("Lecture DNP3 terminée", result["status"])
            if all(master.devices[device].get("latest_telemetry", {}).get(name, {}).get("value") == value
                   for name, value in expected.items()):
                return
            # A simulator command acknowledgement can precede the asynchronous
            # MQTT feedback reaching the Gateway. A new explicit GUI read is
            # required; waiting alone must never manufacture a fresh value.
            self.assertLess(time.monotonic(), deadline, f"manual reads did not return {expected}")
            self.pump(0.1)

    def test_real_windows_multi_der_and_dynamic_configuration(self):
        from common.api_client import ApiClient, ApiError
        from common.config import validate_config
        from integration import free_ports

        master = self.master_window()
        master.start_button.click()
        self.wait(lambda: master.process.is_running() and not master._starting and master.api is not None,
                  "Master ready with zero DER")
        self.assertEqual(master.device_table.rowCount(), 0)
        self.assertEqual(master.devices, {})
        self.assertIn("DER enregistrées : 0", master.count_label.text())
        print("PASS GUI Master starts with zero DER", flush=True)

        bess_cfg, generator_cfg = self.harness.configs()
        bess, generator = self.der_window(bess_cfg), self.der_window(generator_cfg)
        bess_hash = hashlib.sha256(Path(bess.path.text()).read_bytes()).digest()
        bess.start_button.click()
        generator.start_button.click()
        self.wait(lambda: bess._simulator_ready and generator._simulator_ready and len(master.devices) == 2,
                  "two independent DER windows registered and subscribed", timeout=45)
        self.wait(lambda: all(item.get("connection", {}).get("state") == "open" for item in master.devices.values()),
                  "two DNP3 channels open")
        self.assertEqual(bess.commands.rowCount(), 2)
        self.assertEqual(generator.commands.rowCount(), 2)
        self.assertEqual(bess.measurements.rowCount(), 3)
        self.assertEqual(generator.measurements.rowCount(), 3)
        self.select(master, bess_cfg["device_id"])
        editor = master.command_editors["power_setpoint_kw"][0]
        editor.setValue(12.125)
        self.pump(1.2)
        self.assertIs(master.command_editors["power_setpoint_kw"][0], editor)
        self.assertEqual(editor.value(), 12.125)
        print("PASS GUI two DER registrations and dynamic tables", flush=True)

        generator_history = generator.history.rowCount()
        self.command(master, bess, bess_cfg, "power_setpoint_kw", 21.25)
        self.assertEqual(generator.history.rowCount(), generator_history)
        bess_history = bess.history.rowCount()
        self.command(master, generator, generator_cfg, "frequency_setpoint_hz", 61.75)
        self.assertEqual(bess.history.rowCount(), bess_history)
        self.command(master, bess, bess_cfg, "enable", True)
        self.command(master, generator, generator_cfg, "start_generator", True)
        self.pump(0.2)
        self.read(master, bess_cfg, {"measured_power_kw": 21.25, "running": True})
        self.read(master, generator_cfg, {"measured_frequency_hz": 61.75, "generator_running": True})
        print("PASS GUI AO/BO commands, request results and per-device manual reads", flush=True)

        point = next(point for point in bess_cfg["points"] if point["name"] == "measured_power_kw")
        self.set_editor(bess._editors[point["name"]], -13.5)
        bess._set_measurement(point, bess._editors[point["name"]])
        row = bess._measurement_rows[point["name"]]
        self.wait(lambda: bess.measurements.item(row, 3).text() == "-13.5" and not bess._pending,
                  "simulator stdin measurement confirmation")
        self.pump(3.3)
        self.assertEqual(master.devices[bess_cfg["device_id"]]["latest_telemetry"][point["name"]]["value"], 21.25)
        self.pump(0.2)
        self.read(master, bess_cfg, {"measured_power_kw": -13.5})
        self.assertEqual(hashlib.sha256(Path(bess.path.text()).read_bytes()).digest(), bess_hash)
        print("PASS GUI simulator edit travels through C++ before a manual DNP3 read; original JSON preserved", flush=True)

        result_count = len(master.results)
        self.select(master, bess_cfg["device_id"])
        master.send_command(bess_cfg["device_id"], bess_cfg["points"][0], 999)
        self.assertEqual(len(master.results), result_count)
        self.assertIn("hors limites", master.logs.toPlainText())

        duplicate_cfg = copy.deepcopy(bess_cfg)
        duplicate_cfg["dnp3"]["port"] = free_ports(1)[0]
        duplicate = self.der_window(duplicate_cfg)
        duplicate.start_button.click()
        self.assertFalse(duplicate._active)
        self.assertIn("deja utilise", duplicate.state.text())

        occupied_cfg = copy.deepcopy(bess_cfg)
        occupied_cfg["device_id"] = "occupied-port-check"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            occupied_cfg["dnp3"]["port"] = listener.getsockname()[1]
            occupied = self.der_window(occupied_cfg)
            occupied.start_button.click()
            self.wait(lambda: not occupied._active and "Ecoute" in occupied.state.text(), "occupied DNP3 port refusal")
            self.assertFalse(occupied.gateway.is_running())

        # Authentication and trust failures must remain errors, never bypasses.
        with self.assertRaises(ApiError):
            ApiClient("127.0.0.1", self.harness.api_port, token="incorrect-token", ca_cert=str(self.harness.cert)).devices()
        with self.assertRaises(ApiError):
            ApiClient("127.0.0.1", self.harness.api_port, token=self.harness.token, ca_cert="").devices()
        print("PASS GUI duplicate identity, occupied port, bounds, bearer and TLS errors", flush=True)

        bess.stop_button.click()
        self.wait(lambda: not bess._active and not bess.gateway.is_running() and not bess.simulator.is_running(),
                  "stop owns only BESS processes")
        self.assertTrue(generator.gateway.is_running())
        self.assertTrue(generator.simulator.is_running())
        self.assertTrue(master.process.is_running())
        self.command(master, generator, generator_cfg, "frequency_setpoint_hz", 59.25)
        self.read(master, generator_cfg, {"measured_frequency_hz": 59.25})
        self.wait(lambda: master.devices[bess_cfg["device_id"]].get("connection", {}).get("state") != "open",
                  "stopped BESS channel reported disconnected")
        print("PASS GUI stopping one DER preserves Master and second DER", flush=True)

        unknown_cfg = copy.deepcopy(bess_cfg)
        unknown_cfg.update(device_id="unseen-resource", name="Unknown configuration", der_type="CUSTOM")
        unknown_cfg["dnp3"].update(port=free_ports(1)[0], outstation_address=23)
        rename = {point["name"]: f"unseen_{index}" for index, point in enumerate(unknown_cfg["points"])}
        for index, point in enumerate(unknown_cfg["points"]):
            point["name"] = rename[point["name"]]
            point["alias"] = f"custom_alias_{index}"
            point["index"] = 20 + index
            if "feedback_point" in point:
                point["feedback_point"] = rename[point["feedback_point"]]
        unknown_cfg["points"][0].update(min=1e-8, max=2e-8)
        validate_config(unknown_cfg)
        unknown = self.der_window(unknown_cfg)
        unknown.start_button.click()
        self.wait(lambda: unknown._simulator_ready and unknown_cfg["device_id"] in master.devices,
                  "new DER type and unknown point names", timeout=45)
        self.select(master, unknown_cfg["device_id"])
        tiny_editor, tiny_button = master.command_editors["unseen_0"]
        self.assertEqual(tiny_editor.value(), 1e-8)
        results_before = len(master.results)
        tiny_editor.setText("invalid-number")
        tiny_button.click()
        self.assertEqual(len(master.results), results_before)
        tiny_editor.setText("nan")
        tiny_button.click()
        self.assertEqual(len(master.results), results_before)
        self.command(master, unknown, unknown_cfg, "unseen_0", 1.5e-8)
        self.command(master, unknown, unknown_cfg, "unseen_1", True)
        self.read(master, unknown_cfg, {"unseen_2": 1.5e-8, "unseen_4": True})
        print("PASS GUI entirely unknown AO/BO/AI/BI names, aliases and indices; exact tiny AO ranges and invalid numeric rejection", flush=True)

        from common.config import envelope

        device = generator_cfg["device_id"]
        before_measurements = copy.deepcopy(master.devices[device].get("latest_telemetry", {}))
        synthetic = envelope(device, "*", None, "read")
        master._track(synthetic)
        malformed = [
            (f"edgecs/{device}/telemetry", {"device_id": []}),
            (f"edgecs/{device}/telemetry", {"device_id": {}, "kind": "telemetry"}),
            (f"edgecs/{device}/command_result", {"device_id": device, "request_id": []}),
            (f"edgecs/{device}/read_result", {**envelope(device, "*", None, "read_result"),
                                            "request_id": synthetic["request_id"], "status": {"bad": True}}),
            (f"edgecs/{device}/telemetry", {**envelope(device, "temperature_c", 999, "telemetry"), "schema_version": True}),
            (f"edgecs/{device}/telemetry", {**envelope(device, "temperature_c", 999, "telemetry"), "timestamp": []}),
        ]
        for topic, payload in malformed:
            master._message(topic, payload)
        self.assertEqual(master.devices[device].get("latest_telemetry", {}), before_measurements)
        self.assertIn(synthetic["request_id"], master.pending)
        master.pending.pop(synthetic["request_id"])
        master.results.pop()
        master._history()
        self.harness.publish(f"edgecs/{device}/telemetry", [])
        self.wait(lambda: "Message MQTT invalide" in master.logs.toPlainText(), "malformed MQTT envelope error without crash")
        self.assertTrue(master.mqtt.is_connected())
        print("PASS GUI malformed MQTT JSON/envelope shapes do not mutate telemetry or complete pending requests", flush=True)

        unknown.gateway.process.kill()
        self.wait(lambda: not unknown._active and not unknown.simulator.is_running(),
                  "unexpected Gateway crash stops only its paired simulator")
        self.wait(lambda: master.devices[unknown_cfg["device_id"]].get("connection", {}).get("state") != "open",
                  "crashed Gateway is reported disconnected")
        self.assertTrue(master.process.is_running())
        self.assertTrue(generator.gateway.is_running())
        self.assertTrue(generator.simulator.is_running())
        self.assertIn("Erreur", unknown.state.text())
        self.command(master, generator, generator_cfg, "frequency_setpoint_hz", 60.25)
        self.read(master, generator_cfg, {"measured_frequency_hz": 60.25})
        print("PASS GUI Gateway crash reports disconnection and preserves the other DER", flush=True)

        self.harness.terminate(self.harness.processes[0])
        self.wait(lambda: not master._mqtt_ready and not generator._mqtt_ready and not generator._simulator_ready,
                  "active broker loss visible to both GUIs and simulator", timeout=15)
        self.assertTrue(master.process.is_running())
        self.assertTrue(generator.gateway.is_running())
        self.assertTrue(generator.simulator.is_running())
        self.select(master, generator_cfg["device_id"])
        self.assertFalse(master.read_button.isEnabled())
        self.assertTrue(all(not button.isEnabled() for _, button in master.command_editors.values()))
        self.harness.spawn("broker-restarted", ["mosquitto", "-c", self.harness.directory / "mosquitto.conf"])
        self.wait(lambda: master._mqtt_ready and master._engine_mqtt and generator._mqtt_ready and generator._simulator_ready,
                  "automatic broker reconnect and subscriptions restored", timeout=30)
        # Gateway, simulator and Master reconnect independently. GUI/simulator
        # SUBACK does not prove Gateway MQTT readiness. Confirm the entire
        # downstream path with a fresh simulator edit and an explicit DNP3 read
        # before asserting a command can traverse it again.
        marker_point = next(point for point in generator_cfg["points"] if point["name"] == "temperature_c")
        marker_editor = generator._editors[marker_point["name"]]
        downstream_deadline = time.monotonic() + 15
        while True:
            self.set_editor(marker_editor, 27.125)
            generator._set_measurement(marker_point, marker_editor)
            self.wait(lambda: not generator._pending, "reconnected simulator edit acknowledgement", timeout=5)
            self.pump(0.15)
            master.read_button.click()
            result = master.results[-1]
            self.wait(lambda: result["request"] not in master.pending, "downstream readiness manual read", timeout=5)
            self.assertIn("Lecture DNP3 terminée", result["status"])
            if master.devices[device].get("latest_telemetry", {}).get("temperature_c", {}).get("value") == 27.125:
                break
            self.assertLess(time.monotonic(), downstream_deadline, "Gateway MQTT did not resume telemetry reception")
            self.pump(0.2)
        self.command(master, generator, generator_cfg, "frequency_setpoint_hz", 62.25)
        self.read(master, generator_cfg, {"measured_frequency_hz": 62.25})
        print("PASS GUI active broker loss preserves processes, disables actions and reconnects for further commands/reads", flush=True)

        invalid = self.der_window(copy.deepcopy(unknown_cfg))
        filename = self.harness.directory / "malformed.json"
        filename.write_text('{"broken":')
        invalid.load_configuration(filename)
        self.assertIsNone(invalid._config)
        self.assertFalse(invalid.start_button.isEnabled())

        unreachable_cfg = copy.deepcopy(bess_cfg)
        unreachable_cfg["device_id"] = "unreachable-master-check"
        unreachable_cfg["dnp3"]["port"] = free_ports(1)[0]
        unreachable = self.der_window(unreachable_cfg)
        unreachable.api_port.setValue(free_ports(1)[0])
        unreachable.start_button.click()
        self.wait(lambda: not unreachable._active and "Master inaccessible" in unreachable.state.text(),
                  "unavailable Master visible refusal")
        self.assertFalse(unreachable.gateway.is_running())

        # A missing broker cannot start the C++ engine. Shorten only the UI's
        # deadline after observing a genuine refused MQTT connection attempt.
        no_broker = self.master_window()
        no_broker.api_port.setValue(free_ports(1)[0])
        no_broker.mqtt_port.setValue(free_ports(1)[0])
        no_broker.start_button.click()
        self.wait(lambda: "Broker MQTT inaccessible" in no_broker.logs.toPlainText(), "missing broker visible error", timeout=10)
        self.assertFalse(no_broker.process.is_running())
        no_broker._deadline = time.monotonic() - 1
        no_broker._tick()
        self.assertFalse(no_broker._starting)
        self.assertFalse(no_broker.process.is_running())
        print("PASS GUI malformed JSON, unavailable Master and unavailable broker", flush=True)

        for der in (generator, unknown):
            der.close()
        self.wait(lambda: all(not der.gateway.is_running() and not der.simulator.is_running()
                              for der in (generator, unknown)), "window close cleans owned processes")
        master.close()
        self.assertFalse(master.process.is_running())
        self.success = True


if __name__ == "__main__":
    unittest.main(verbosity=2)
