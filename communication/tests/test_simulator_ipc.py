#!/usr/bin/env python3
"""Exercise the real C++ simulator's optional GUI IPC and MQTT boundary.

Run after building Gateway: python3 tests/test_simulator_ipc.py
Uses a private temporary Mosquitto broker and free loopback ports. No Python
packages, Master, Gateway, pre-existing broker, or desktop session are required.
"""
import argparse
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import uuid

from integration import envelope, eventually, free_ports


class JsonStream:
    def __init__(self, process, ipc=False, merged=False):
        self.process, self.ipc, self.merged = process, ipc, merged
        self.messages, self.errors = [], []
        self.condition = threading.Condition()
        self.reader = threading.Thread(target=self.collect, daemon=True)
        self.reader.start()

    def collect(self):
        for line in self.process.stdout:
            try:
                if self.ipc:
                    if not line.startswith("EDGECS_GUI "):
                        if self.merged:
                            continue
                        raise ValueError(f"Unexpected simulator stdout: {line!r}")
                    value = json.loads(line[len("EDGECS_GUI "):])
                else:
                    topic, _, payload = line.rstrip("\n").partition("\t")
                    value = (topic, json.loads(payload))
                with self.condition:
                    self.messages.append(value)
                    self.condition.notify_all()
            except (ValueError, json.JSONDecodeError) as error:
                with self.condition:
                    self.errors.append(str(error))
                    self.condition.notify_all()

    def wait(self, predicate, start=0, timeout=10):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                if self.errors:
                    raise AssertionError("; ".join(self.errors))
                for message in self.messages[start:]:
                    if predicate(message):
                        return message
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(f"Expected event missing; received: {self.messages[start:]}")
                self.condition.wait(remaining)

    def mark(self):
        with self.condition:
            return len(self.messages)


class SimulatorIPC(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]
    gateway_build = root / "Gateway/build"

    @classmethod
    def setUpClass(cls):
        for command in ("mosquitto", "mosquitto_pub", "mosquitto_sub"):
            if not shutil.which(command):
                raise unittest.SkipTest(f"Missing executable: {command}")
        cls.binary = cls.gateway_build / "edgecs_bess_sim"
        if not cls.binary.is_file():
            raise unittest.SkipTest(f"Build executable first: {cls.binary}")
        cls.directory = tempfile.TemporaryDirectory(prefix="edgecs-simulator-ipc-")
        cls.port = free_ports(1)[0]
        config = Path(cls.directory.name) / "mosquitto.conf"
        config.write_text(f"listener {cls.port} 127.0.0.1\nallow_anonymous true\npersistence false\n")
        cls.broker_log = open(Path(cls.directory.name) / "broker.log", "w", encoding="utf-8")
        cls.broker = subprocess.Popen(["mosquitto", "-c", str(config)],
                                      stdout=cls.broker_log, stderr=subprocess.STDOUT)

        def ready():
            with socket.create_connection(("127.0.0.1", cls.port), 0.2):
                return True
        eventually(ready)

    @classmethod
    def tearDownClass(cls):
        cls.broker.terminate()
        cls.broker.wait(timeout=5)
        cls.broker_log.close()
        cls.directory.cleanup()

    def setUp(self):
        self.processes, self.logs = [], []
        self.cfg = json.loads((self.root / "Gateway/config/outstation_config.json").read_text())
        self.cfg["device_id"] = "ipc-" + uuid.uuid4().hex
        self.cfg["mqtt"] = dict(host="127.0.0.1", port=self.port)
        self.cfg["points"] = [
            dict(name="unfamiliar_target", alias="custom", direction="command",
                 dnp3_type="AO", index=73, unit="widgets", min=-7, max=11,
                 feedback_point="unfamiliar_actual"),
            dict(name="unfamiliar_switch", direction="command", dnp3_type="BO",
                 index=37, unit="bool", feedback_point="unfamiliar_flag"),
            dict(name="unfamiliar_actual", alias="actual", direction="telemetry",
                 dnp3_type="AI", index=19, unit="widgets", initial=3.5),
            dict(name="unfamiliar_flag", alias="flag", direction="telemetry",
                 dnp3_type="BI", index=21, unit="bool", initial=False),
        ]
        self.observer_process = subprocess.Popen(
            ["mosquitto_sub", "-h", "127.0.0.1", "-p", str(self.port), "-q", "1",
             "-t", "edgecs/#", "-F", "%t\t%p"], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.processes.append(self.observer_process)
        self.observer = JsonStream(self.observer_process)
        # Prove SUBACK with a round trip before starting any simulator.
        ready = envelope(self.cfg["device_id"], "observer", True, "test")
        deadline = time.monotonic() + 5
        while True:
            self.publish(self.cfg, ready, suffix="observer")
            try:
                self.observer.wait(lambda item: item[1] == ready, timeout=0.2)
                break
            except AssertionError:
                if time.monotonic() > deadline:
                    raise
        self.gui = self.start_simulator(self.cfg)

    def tearDown(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                if process.stdin:
                    try:
                        process.stdin.write('{"op":"quit"}\n')
                        process.stdin.flush()
                        process.wait(timeout=6)
                    except (OSError, subprocess.TimeoutExpired):
                        process.terminate()
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()
        for log in self.logs:
            log.close()

    def start_simulator(self, cfg, merged=False):
        path = Path(self.directory.name) / (cfg["device_id"] + ".json")
        path.write_text(json.dumps(cfg))
        log = open(path.with_suffix(".log"), "w", encoding="utf-8")
        self.logs.append(log)
        environment = dict(os.environ)
        environment.pop("MQTT_USERNAME", None)
        environment.pop("MQTT_PASSWORD", None)
        process = subprocess.Popen([str(self.binary), str(path), "--gui"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT if merged else log,
                                   env=environment, text=True, bufsize=1)
        self.processes.append(process)
        stream = JsonStream(process, ipc=True, merged=merged)
        stream.wait(lambda event: event.get("kind") == "snapshot")
        stream.wait(lambda event: event.get("kind") == "status" and
                    event.get("state") == "connected" and event.get("mqtt_subscribed"))
        return stream

    def request(self, request, stream=None):
        stream = stream or self.gui
        stream.process.stdin.write((request if isinstance(request, str) else json.dumps(request)) + "\n")
        stream.process.stdin.flush()

    def snapshot(self, stream=None):
        stream = stream or self.gui
        request_id = uuid.uuid4().hex
        self.request(dict(op="snapshot", request_id=request_id), stream)
        event = stream.wait(lambda event: event.get("kind") == "snapshot" and
                            event.get("request_id") == request_id)
        return {item["point"]: item for item in event["measurements"]}

    def publish(self, cfg, message, suffix="edge/command"):
        subprocess.run(["mosquitto_pub", "-h", "127.0.0.1", "-p", str(self.port),
                        "-q", "1", "-t", f"edgecs/{cfg['device_id']}/{suffix}", "-s"],
                       input=json.dumps(message), text=True, check=True, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def test_initial_snapshot_and_manual_set_remain_simulator_owned(self):
        values = self.snapshot()
        actual = values["unfamiliar_actual"]
        self.assertEqual((actual["value"], actual["index"], actual["source"]), (3.5, 19, "initial"))
        datetime.fromisoformat(actual["updated_at"])
        for point, value in (("unfamiliar_actual", 9.25), ("unfamiliar_flag", True)):
            request_id = uuid.uuid4().hex
            marker = self.observer.mark()
            self.request(dict(op="set", point=point, value=value, request_id=request_id))
            event = self.gui.wait(lambda event: event.get("kind") == "measurement" and
                                  event.get("request_id") == request_id)
            self.assertEqual((event["point"], event["value"], event["source"]), (point, value, "manual"))
            self.assertFalse(event["simulated"])
            topic, message = self.observer.wait(
                lambda item: item[0] == f"edgecs/{self.cfg['device_id']}/edge/telemetry" and
                item[1].get("point") == point and item[1].get("value") == value, marker)
            self.assertEqual(message["kind"], "telemetry")
            self.assertEqual(self.snapshot()[point]["value"], value)

    def test_invalid_ipc_preserves_values_and_timestamps(self):
        original = self.snapshot()
        invalid = ["{bad", "[]", '{"op":"set","point":"unfamiliar_actual","value":1e999}',
                   dict(op="unknown"), dict(op="snapshot", request_id=1),
                   dict(op="set", point="unfamiliar_actual", value=True),
                   dict(op="set", point="unfamiliar_actual", value="4.0"),
                   dict(op="set", point="unfamiliar_flag", value=1),
                   dict(op="set", point="does_not_exist", value=1),
                   dict(op="set", point="unfamiliar_target", value=5)]
        for request in invalid:
            marker = self.gui.mark()
            self.request(request)
            self.gui.wait(lambda event: event.get("kind") == "error", marker)
            self.assertEqual(self.snapshot(), original, request)

    def test_mqtt_commands_validate_limits_and_label_simulated_feedback(self):
        original = self.snapshot()
        for point, value in (("custom", 12), ("unfamiliar_target", True), ("unfamiliar_switch", 1)):
            request = envelope(self.cfg["device_id"], point, value, "command")
            self.publish(self.cfg, request)
            error = self.gui.wait(lambda event: event.get("kind") == "error" and
                                  event.get("request_id") == request["request_id"])
            self.assertEqual(error["op"], "command")
            self.assertEqual(self.snapshot(), original)
        for point, value, canonical, feedback in (("custom", 11, "unfamiliar_target", "unfamiliar_actual"),
                                                  ("unfamiliar_switch", True, "unfamiliar_switch", "unfamiliar_flag")):
            request = envelope(self.cfg["device_id"], point, value, "command")
            self.publish(self.cfg, request)
            result = self.gui.wait(lambda event: event.get("kind") == "command_result" and
                                   event.get("request_id") == request["request_id"])
            self.assertEqual((result["point"], result["status"]), (canonical, "accepted_by_simulator"))
            self.assertTrue(result["feedback_simulated"])
            datetime.fromisoformat(result["received_at"])
            changed = self.gui.wait(lambda event: event.get("kind") == "measurement" and
                                    event.get("request_id") == request["request_id"])
            self.assertEqual((changed["point"], changed["source"], changed["value"]), (feedback, "feedback", value))
            self.assertTrue(changed["simulated"])

    def test_multiple_simulators_are_isolated_and_quit_independently(self):
        second_cfg = copy.deepcopy(self.cfg)
        second_cfg["device_id"] += "-second"
        second = self.start_simulator(second_cfg)
        original = self.snapshot(second)
        request = envelope(self.cfg["device_id"], "custom", -6, "command")
        self.publish(self.cfg, request)
        self.gui.wait(lambda event: event.get("kind") == "measurement" and
                      event.get("request_id") == request["request_id"])
        self.assertEqual(self.snapshot(second), original)
        self.request(dict(op="quit"))
        self.assertEqual(self.gui.process.wait(timeout=6), 0)
        self.assertIsNone(second.process.poll())
        self.request(dict(op="set", point="unfamiliar_actual", value=5, request_id="independent"), second)
        second.wait(lambda event: event.get("kind") == "measurement" and
                     event.get("request_id") == "independent")
        self.assertEqual(self.snapshot(second)["unfamiliar_actual"]["value"], 5)

    def test_terminal_interface_remains_available(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["device_id"] += "-console"
        path = Path(self.directory.name) / (cfg["device_id"] + ".json")
        path.write_text(json.dumps(cfg))
        result = subprocess.run([str(self.binary), str(path)],
                                input="actual 2.25\nflag on\nstatus\nquit\n",
                                capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unfamiliar_actual = 2.25", result.stdout)
        self.assertIn("unfamiliar_flag = true", result.stdout)
        self.assertNotIn("EDGECS_GUI ", result.stdout)

    def test_ipc_stays_framed_when_qt_merges_human_logs(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["device_id"] += "-merged"
        merged = self.start_simulator(cfg, merged=True)
        request = envelope(cfg["device_id"], "custom", 2, "command")
        self.publish(cfg, request)
        merged.wait(lambda event: event.get("kind") == "measurement" and
                     event.get("request_id") == request["request_id"])
        self.assertEqual(self.snapshot(merged)["unfamiliar_actual"]["value"], 2)

    def test_concurrent_snapshots_and_changes_preserve_publication_order(self):
        device = self.cfg["device_id"]
        topic = f"edgecs/{device}/edge/telemetry"
        self.observer.wait(lambda item: item[0] == topic and item[1].get("point") == "unfamiliar_flag")
        mqtt_marker, gui_marker = self.observer.mark(), self.gui.mark()
        prefix = uuid.uuid4().hex
        errors = []

        def commands():
            try:
                for index in range(16):
                    request = envelope(device, "custom", -index / 10, "command")
                    request["request_id"] = f"{prefix}-command-{index}"
                    self.publish(self.cfg, request)
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=commands)
        thread.start()
        for index in range(16):
            self.request(dict(op="set", point="unfamiliar_actual", value=20 + index,
                              request_id=f"{prefix}-set-{index}"))
            self.request(dict(op="snapshot", request_id=f"{prefix}-snapshot-{index}"))
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors, errors)
        for index in range(16):
            for kind in ("set", "command"):
                self.gui.wait(lambda event, key=f"{prefix}-{kind}-{index}":
                              event.get("kind") == "measurement" and event.get("request_id") == key)
        final = self.snapshot()["unfamiliar_actual"]["value"]
        expected = [event["value"] for event in self.gui.messages[gui_marker:]
                    if event.get("kind") == "measurement"]

        def all_telemetry_arrived():
            with self.observer.condition:
                return len([item for item in self.observer.messages[mqtt_marker:]
                            if item[0] == topic and item[1].get("point") == "unfamiliar_actual"]) >= 32
        eventually(all_telemetry_arrived)
        actual = [item[1]["value"] for item in self.observer.messages[mqtt_marker:]
                  if item[0] == topic and item[1].get("point") == "unfamiliar_actual"]
        self.assertEqual(actual, expected)
        self.assertEqual(actual[-1], final)
        latest = 3.5
        for event in self.gui.messages[gui_marker:]:
            if event.get("kind") == "measurement":
                latest = event["value"]
            elif event.get("kind") == "snapshot":
                value = next(item["value"] for item in event["measurements"] if item["point"] == "unfamiliar_actual")
                self.assertEqual(value, latest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-build", type=Path, default=SimulatorIPC.gateway_build)
    arguments, unittest_arguments = parser.parse_known_args()
    SimulatorIPC.gateway_build = arguments.gateway_build.resolve()
    unittest.main(argv=[__file__] + unittest_arguments)
