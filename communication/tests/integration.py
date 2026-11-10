#!/usr/bin/env python3
"""Acceptance tests using real HTTPS registration, OpenDNP3 TCP and MQTT.

Requires already built binaries, mosquitto, mosquitto_pub/sub and openssl. No
Python packages, existing broker, pre-existing certificates or credentials are
needed. Every service listens on a temporary loopback port. Failed runs retain
their logs/configuration in the printed artifact directory.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def eventually(function, timeout=15):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            result = function()
            if result:
                return result
        except (OSError, urllib.error.URLError) as error:
            last = error
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {function.__name__}: {last}")


def free_ports(count):
    sockets = []
    try:
        for _ in range(count):
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            sockets.append(sock)
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def envelope(device, point, value, kind):
    return dict(schema_version=1, device_id=device, point=point, value=value,
                kind=kind, request_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"))


class Harness:
    def __init__(self, root, derms_build, gateway_build, keep):
        self.root, self.keep = root, keep
        self.directory = Path(tempfile.mkdtemp(prefix="edgecs-integration-"))
        self.derms_build, self.gateway_build = derms_build, gateway_build
        self.mqtt_port, self.api_port, self.bess_port, self.generator_port = free_ports(4)
        self.url = f"https://127.0.0.1:{self.api_port}"
        self.token = uuid.uuid4().hex
        self.processes, self.applications, self.logs = [], [], []
        self.messages = []
        self.condition = threading.Condition()
        self.cert = self.directory / "server.crt"
        self.key = self.directory / "server.key"
        self.env = dict(os.environ)
        for name in ("MQTT_USERNAME", "MQTT_PASSWORD", "EDGECS_CONFIG", "MASTER_REGISTER_URL"):
            self.env.pop(name, None)
        self.env.update(MQTT_HOST="127.0.0.1", MQTT_PORT=str(self.mqtt_port),
                        EDGECS_API_HOST="127.0.0.1", EDGECS_API_PORT=str(self.api_port),
                        EDGECS_REGISTRATION_TOKEN=self.token,
                        EDGECS_TLS_CERT=str(self.cert), EDGECS_TLS_KEY=str(self.key),
                        EDGECS_CA_CERT=str(self.cert), MASTER_REGISTER_URL=self.url + "/api/v1/outstations/register",
                        DNP3_BIND_HOST="127.0.0.1")

    def spawn(self, name, arguments, interactive=False, application=False):
        log = open(self.directory / (name + ".log"), "w", encoding="utf-8")
        self.logs.append(log)
        process = subprocess.Popen([str(arg) for arg in arguments], env=self.env,
                                   stdin=subprocess.PIPE if interactive else subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, text=True,
                                   cwd=self.directory)
        self.processes.append(process)
        if application:
            self.applications.append(process)
        return process

    def setup(self):
        for command in ("mosquitto", "mosquitto_pub", "mosquitto_sub", "openssl"):
            require(shutil.which(command), f"Missing executable: {command}")
        for binary in (self.derms_build / "edgecs_master",
                       self.gateway_build / "edgecs_gateway", self.gateway_build / "edgecs_der_sim"):
            require(binary.is_file(), f"Build this executable first: {binary}")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes",
                        "-keyout", str(self.key), "-out", str(self.cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.key.chmod(0o600)
        self.context = ssl.create_default_context(cafile=str(self.cert))
        config = self.directory / "mosquitto.conf"
        config.write_text(f"listener {self.mqtt_port} 127.0.0.1\nallow_anonymous true\npersistence false\n")
        self.spawn("broker", ["mosquitto", "-c", config])

        def broker_ready():
            with socket.create_connection(("127.0.0.1", self.mqtt_port), 0.2):
                return True
        eventually(broker_ready)
        observer_log = open(self.directory / "mqtt.jsonl", "w", encoding="utf-8")
        self.logs.append(observer_log)
        observer = subprocess.Popen(["mosquitto_sub", "-h", "127.0.0.1", "-p", str(self.mqtt_port),
                                     "-q", "1", "-t", "edgecs/#", "-F", "%t\t%p"],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, bufsize=1)
        self.processes.append(observer)

        def collect():
            for line in observer.stdout:
                topic, _, payload = line.rstrip("\n").partition("\t")
                try:
                    message = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                with self.condition:
                    self.messages.append((topic, message))
                    observer_log.write(json.dumps(dict(topic=topic, message=message)) + "\n")
                    observer_log.flush()
                    self.condition.notify_all()
        self.observer_thread = threading.Thread(target=collect, daemon=True)
        self.observer_thread.start()
        # SUBACK readiness is proven by a round trip, before launching services.
        ready = envelope("test", "observer_ready", True, "test")
        deadline = time.monotonic() + 5
        while True:
            self.publish("edgecs/test/observer", ready)
            try:
                self.wait_message("edgecs/test/observer", lambda msg: msg == ready, timeout=0.2)
                break
            except AssertionError:
                require(time.monotonic() < deadline, "MQTT observer did not subscribe")

    def api(self, path="/api/v1/outstations", body=None, authenticated=True, context=None):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(self.url + path, headers=headers,
                                         data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(request, context=context or self.context, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def publish(self, topic, message):
        subprocess.run(["mosquitto_pub", "-h", "127.0.0.1", "-p", str(self.mqtt_port),
                        "-q", "1", "-t", topic, "-s"], input=json.dumps(message), text=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=5)

    def mark(self):
        with self.condition:
            return len(self.messages)

    def wait_message(self, topic, predicate=lambda msg: True, start=0, timeout=12):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                for actual_topic, message in self.messages[start:]:
                    if actual_topic == topic and predicate(message):
                        return message
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(f"Missing MQTT message on {topic} after message {start}")
                self.condition.wait(remaining)

    def configs(self):
        bess = json.loads((self.root / "Gateway/config/outstation_config.json").read_text())
        generator = json.loads((self.root / "Gateway/config/generator_config.json").read_text())
        for cfg, port in ((bess, self.bess_port), (generator, self.generator_port)):
            cfg["dnp3"].update(host="127.0.0.1", port=port)
            cfg["mqtt"] = dict(host="127.0.0.1", port=self.mqtt_port)
            cfg["master_api_port"] = self.api_port
        # AI[1] means SOC in one device and frequency in the other.
        next(p for p in generator["points"] if p["name"] == "measured_frequency_hz")["index"] = 1
        return bess, generator

    def launch(self, configs, phase, on_master_ready=None):
        start = self.mark()
        self.spawn(phase + "-master", [self.derms_build / "edgecs_master"], application=True)
        eventually(lambda: self.api("/health")[0] == 200)
        if on_master_ready is not None:
            on_master_ready()
        self.simulators = {}
        for cfg in configs:
            device = cfg["device_id"]
            path = self.directory / f"{phase}-{device}.json"
            path.write_text(json.dumps(cfg, indent=2) + "\n")
            self.spawn(f"{phase}-{device}-gateway", [self.gateway_build / "edgecs_gateway", path], application=True)
            self.simulators[device] = self.spawn(f"{phase}-{device}-simulator",
                [self.gateway_build / "edgecs_der_sim", path], interactive=True, application=True)

        def registered_and_connected():
            status, body = self.api()
            devices = body.get("outstations", [])
            return status == 200 and {d["device_id"] for d in devices} == {c["device_id"] for c in configs} and all(
                d["connection"]["state"] == "open" for d in devices)
        eventually(registered_and_connected)
        for cfg in configs:
            for point in cfg["points"]:
                if point["direction"] == "telemetry":
                    self.wait_message(f"edgecs/{cfg['device_id']}/edge/telemetry",
                                      lambda msg, p=point: msg.get("point") == p["name"], start)

    def command(self, cfg, name_or_alias, value):
        device = cfg["device_id"]
        point = next(p for p in cfg["points"] if p["direction"] == "command" and
                     name_or_alias in (p["name"], p.get("alias")))
        request = envelope(device, name_or_alias, value, "command")
        start = self.mark()
        self.publish(f"edgecs/{device}/command", request)
        reply = self.wait_message(f"edgecs/{device}/command_result",
                                  lambda msg: msg.get("request_id") == request["request_id"], start)
        require(reply["status"] == "accepted_by_outstation", f"DNP3 rejected command: {reply}")
        require(reply["point"] == point["name"] and reply["dnp3_index"] == point["index"], "Wrong DNP3 dispatch")
        actual = self.wait_message(f"edgecs/{device}/edge/command",
                                  lambda msg: msg.get("point") == point["name"] and msg.get("value") == value, start)
        require(actual.get("schema_version") == 1 and actual.get("request_id") and actual.get("timestamp"),
                "Gateway command lost the protocol envelope")
        if "feedback_point" in point:
            self.wait_message(f"edgecs/{device}/edge/telemetry", lambda msg:
                              msg.get("point") == point["feedback_point"] and msg.get("value") == value, start)

    def read(self, cfg, expected):
        device = cfg["device_id"]
        deadline = time.monotonic() + 12
        while True:
            request = envelope(device, "*", None, "read")
            start = self.mark()
            self.publish(f"edgecs/{device}/read", request)
            self.wait_message(f"edgecs/{device}/read_result", lambda msg:
                              msg.get("request_id") == request["request_id"] and msg.get("status") == "read_completed", start)
            matches = True
            for point in cfg["points"]:
                if point["direction"] != "telemetry":
                    continue
                value = expected.get(point["name"], point.get("initial", False if point["dnp3_type"] == "BI" else 0))
                message = self.wait_message(f"edgecs/{device}/telemetry", lambda msg, p=point:
                                            msg.get("point") == p["name"], start)
                require(message["dnp3_index"] == point["index"] and message["dnp3_type"] == point["dnp3_type"],
                        "Wrong telemetry index or type")
                matches = matches and message["value"] == value
            if matches:
                break
            # Observing the simulator's MQTT publication does not acknowledge
            # that the Gateway has applied it. Retry real on-demand READs.
            require(time.monotonic() < deadline, f"DNP3 values did not reach expected state: {expected}")
            time.sleep(0.05)
        status, descriptor = self.api(f"/api/v1/outstations/{device}")
        require(status == 200, "Device detail discovery failed")
        for name, value in expected.items():
            latest = descriptor["latest_telemetry"][name]
            require(latest["value"] == value and "quality_flags" in latest and "received_at" in latest,
                    f"Registry telemetry missing value/quality/time: {latest}")
        return descriptor

    def reject_command(self, device, point, value):
        request = envelope(device, point, value, "command")
        start = self.mark()
        self.publish(f"edgecs/{device}/command", request)
        reply = self.wait_message(f"edgecs/{device}/command_result",
                                  lambda msg: msg.get("request_id") == request["request_id"], start)
        require(reply.get("status") == "rejected_by_master" and reply.get("reason"), f"Expected useful rejection: {reply}")

    def invalid_registrations(self, cfg):
        require(self.api(authenticated=False)[0] == 401, "Discovery must require authentication")
        require(self.api("/api/v1/outstations/missing-device")[0] == 404, "Unknown device detail must return 404")
        require(self.api("/api/v1/outstations/missing-device/telemetry")[0] == 404, "Unknown device telemetry must return 404")
        status, telemetry = self.api(f"/api/v1/outstations/{cfg['device_id']}/telemetry")
        require(status == 200 and telemetry.get("device_id") == cfg["device_id"] and
                "latest_telemetry" in telemetry and "connection" in telemetry,
                "Telemetry discovery endpoint is incomplete")
        require(self.api("/api/v1/outstations/register", cfg, authenticated=False)[0] == 401,
                "Registration must require authentication")
        try:
            self.api(context=ssl.create_default_context())
        except urllib.error.URLError:
            pass
        else:
            raise AssertionError("An untrusted self-signed certificate was accepted")
        require(self.api("/api/v1/outstations/register", cfg)[1].get("status") == "already_registered",
                "Identical registration is not idempotent")
        cases = []
        changed = copy.deepcopy(cfg)
        changed["name"] += " changed"
        cases.append(changed)
        endpoint = copy.deepcopy(cfg)
        endpoint["device_id"] = "endpoint-conflict"
        cases.append(endpoint)
        duplicate = copy.deepcopy(cfg)
        duplicate["device_id"] = "duplicate-point"
        duplicate["points"].append(copy.deepcopy(duplicate["points"][0]))
        duplicate["points"][-1]["name"] = "duplicate_index"
        duplicate["points"][-1].pop("alias", None)
        cases.append(duplicate)
        malformed = copy.deepcopy(cfg)
        malformed["device_id"] = "malformed-point"
        del malformed["points"][0]["dnp3_type"]
        cases.append(malformed)
        invalid_type = copy.deepcopy(cfg)
        invalid_type["device_id"] = "bad-index-type"
        invalid_type["points"][0]["index"] = "3"
        cases.append(invalid_type)
        for invalid in cases:
            status, response = self.api("/api/v1/outstations/register", invalid)
            require(status == 400 and response.get("error"), f"Invalid registration accepted: {response}")

    @staticmethod
    def terminate(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=7)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stdin:
            process.stdin.close()

    def stop_applications(self):
        for process in reversed(self.applications):
            self.terminate(process)
        self.applications.clear()

    def run(self):
        self.setup()
        binaries = [self.derms_build / "edgecs_master", self.gateway_build / "edgecs_gateway",
                    self.gateway_build / "edgecs_der_sim"]
        hashes = {path: hashlib.sha256(path.read_bytes()).digest() for path in binaries}
        bess, generator = self.configs()
        self.launch((bess, generator), "initial")
        for cfg in (bess, generator):
            descriptor = self.api(f"/api/v1/outstations/{cfg['device_id']}")[1]
            require(len(descriptor["commands"]) == 2 and len(descriptor["telemetry"]) == 3,
                    "Capabilities unavailable to other DERMS components")
            require(descriptor["latest_telemetry"] == {}, "Master acquired telemetry without READ")
        self.command(bess, "power", 30)
        self.command(bess, "enable", True)
        self.command(generator, "frequency", 60.5)
        self.command(generator, "start", True)
        # Observe longer than the previous 3-second polling interval.
        time.sleep(3.5)
        require(not any(topic in ("edgecs/bess-01/telemetry", "edgecs/generator-01/telemetry")
                        for topic, _ in self.messages), "Unrequested automatic DNP3 telemetry")
        self.read(bess, dict(measured_power_kw=30, soc_pct=65, running=True))
        self.read(generator, dict(measured_frequency_hz=60.5, generator_running=True, temperature_c=26))
        # Reading unchanged values must still report fresh samples.
        self.read(bess, dict(measured_power_kw=30, soc_pct=65, running=True))
        self.invalid_registrations(bess)
        self.reject_command("bess-01", "unknown_command", 1)
        self.reject_command("bess-01", 123, 1)
        self.reject_command("bess-01", "power", "invalid-number")
        self.reject_command("bess-01", "power", 100000)
        self.reject_command("bess-01", "enable", 1)
        self.reject_command("unknown-device", "power", 1)
        # Wrong identity, unknown measurement and wrong JSON types must not alter the database.
        self.publish("edgecs/generator-01/edge/telemetry", envelope("bess-01", "measured_frequency_hz", 99, "telemetry"))
        self.publish("edgecs/generator-01/edge/telemetry", envelope("generator-01", "unknown_measurement", 99, "telemetry"))
        self.publish("edgecs/generator-01/edge/telemetry", envelope("generator-01", "measured_frequency_hz", True, "telemetry"))
        self.read(generator, dict(measured_frequency_hz=60.5, generator_running=True))
        start = self.mark()
        self.simulators["generator-01"].stdin.write("temp 29\n")
        self.simulators["generator-01"].stdin.flush()
        self.wait_message("edgecs/generator-01/edge/telemetry", lambda msg:
                          msg.get("point") == "temperature_c" and msg.get("value") == 29, start)
        self.read(generator, dict(measured_frequency_hz=60.5, temperature_c=29, generator_running=True))
        print("PASS: BESS + generator registration, discovery, AO/BO, aliases, real DNP3/MQTT paths, isolation, errors, TLS/auth", flush=True)
        self.stop_applications()
        modified = copy.deepcopy(bess)
        modified["der_type"] = "THERMAL_STORE"
        command = next(p for p in modified["points"] if p["name"] == "power_setpoint_kw")
        command.update(name="dispatch_target", alias="target", index=23, feedback_point="observed_output")
        measurement = next(p for p in modified["points"] if p["name"] == "measured_power_kw")
        measurement.update(name="observed_output", alias="observed", index=17)
        def check_empty_registry():
            require(self.api()[1]["outstations"] == [], "New Master should initially have an empty registry")

        self.launch((modified, generator), "reconfigured", on_master_ready=check_empty_registry)
        self.command(modified, "target", -12.75)
        self.read(modified, dict(observed_output=-12.75, soc_pct=65, running=False))
        self.reject_command("bess-01", "power_setpoint_kw", 1)
        self.command(generator, "frequency", 59.75)
        self.read(generator, dict(measured_frequency_hz=59.75, generator_running=False))
        require(all(hashlib.sha256(path.read_bytes()).digest() == hashes[path] for path in binaries),
                "An executable changed between configuration tests")
        print("PASS: restarted the same binaries with a new DER type, renamed points/aliases and changed AO/AI indices", flush=True)

    def cleanup(self, success):
        for process in reversed(self.processes):
            self.terminate(process)
        if hasattr(self, "observer_thread"):
            self.observer_thread.join(timeout=2)
        for log in self.logs:
            log.close()
        if success and not self.keep:
            shutil.rmtree(self.directory)
        else:
            print(f"Artifacts: {self.directory}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--derms-build", type=Path, default=root / "DERMS/build")
    parser.add_argument("--gateway-build", type=Path, default=root / "Gateway/build")
    parser.add_argument("--keep-artifacts", action="store_true")
    arguments = parser.parse_args()
    harness = Harness(root, arguments.derms_build.resolve(), arguments.gateway_build.resolve(), arguments.keep_artifacts)
    success = False
    try:
        harness.run()
        success = True
    finally:
        harness.cleanup(success)


if __name__ == "__main__":
    main()
