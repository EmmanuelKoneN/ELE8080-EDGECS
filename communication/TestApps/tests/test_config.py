"""Offline validation and ownership checks; no Qt or network service required."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

APPS = Path(__file__).resolve().parents[1]
ROOT = APPS.parent
sys.path.insert(0, str(APPS))

from common.config import (
    ConfigError, DeviceLock, TemporaryConfig, envelope, find_executable,
    load_config, runtime_config, validate_config, validate_ipv4, validate_port,
    validate_value,
)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / "Gateway/config/outstation_config.json")

    def test_examples_and_unknown_device_category(self):
        for filename in ("outstation_config.json", "generator_config.json"):
            cfg = load_config(ROOT / "Gateway/config" / filename)
            cfg["der_type"] = "CUSTOM_LAB_RESOURCE"
            self.assertIs(validate_config(cfg), cfg)

    def test_runtime_copy_and_private_file_preserve_source(self):
        original = copy.deepcopy(self.config)
        cfg = runtime_config(self.config, "127.0.0.2", "127.0.0.3", "21000", "127.0.0.4", "1884", 8444)
        self.assertEqual(self.config, original)
        self.assertEqual(cfg["master_api_host"], "127.0.0.2")
        self.assertEqual(cfg["dnp3"]["host"], "127.0.0.3")
        self.assertEqual(cfg["mqtt"], {"host": "127.0.0.4", "port": 1884})
        with TemporaryConfig(cfg) as temporary:
            filename = Path(temporary.path)
            self.assertEqual(load_config(filename), cfg)
            self.assertEqual(filename.stat().st_mode & 0o777, 0o600)
            self.assertEqual(filename.parent.stat().st_mode & 0o777, 0o700)
        self.assertFalse(filename.exists())

    def test_reject_invalid_configuration_constraints(self):
        modifications = [
            lambda c: c.update(schema_version=True),
            lambda c: c.update(extra="unknown"),
            lambda c: c.update(device_id="bad/topic"),
            lambda c: c.update(name=""),
            lambda c: c["dnp3"].update(host="localhost"),
            lambda c: c["dnp3"].update(port="20000"),
            lambda c: c["dnp3"].update(master_address=True),
            lambda c: c["dnp3"].update(outstation_address=1),
            lambda c: c["mqtt"].update(port=65536),
            lambda c: c["points"][0].update(index=-1),
            lambda c: c["points"][0].update(index=True),
            lambda c: c["points"][0].update(min=float("nan")),
            lambda c: c["points"][0].update(max=-50),
            lambda c: c["points"][0].update(direction="telemetry"),
            lambda c: c["points"][0].update(feedback_point="running"),
            lambda c: c["points"][0].update(feedback_point="missing"),
            lambda c: c["points"][0].update(initial=0),
            lambda c: c["points"][1].update(min=0),
            lambda c: c["points"][2].update(initial=True),
            lambda c: c["points"][2].update(feedback_point="running"),
            lambda c: c["points"][3].update(index=0),
            lambda c: c["points"][3].update(alias="measured_power_kw"),
            lambda c: c["points"][3].update(alias="power"),
            lambda c: c["points"].append(copy.deepcopy(c["points"][0])),
        ]
        for index, modify in enumerate(modifications):
            with self.subTest(case=index):
                cfg = copy.deepcopy(self.config)
                modify(cfg)
                with self.assertRaises(ConfigError):
                    validate_config(cfg)

    def test_strict_values_and_bounds(self):
        ao = self.config["points"][0]
        for value in (-50, 0.0, 50):
            self.assertEqual(validate_value(ao, value), value)
        for value in (-50.1, 50.1, True, "12", float("nan"), float("inf"), 10**400):
            with self.subTest(value=str(value)[:30]), self.assertRaises(ConfigError):
                validate_value(ao, value)
        for value in (1, 0, "true", None):
            with self.assertRaises(ConfigError):
                validate_value(self.config["points"][1], value)
        self.assertIs(validate_value(self.config["points"][1], True), True)

    def test_addresses_and_ports(self):
        for value in ("127.0.0.1", "192.168.2.1", "0.0.0.0"):
            self.assertEqual(validate_ipv4(value), value)
        for value in ("localhost", "::1", "256.0.0.1", "127.00.0.1", None):
            with self.assertRaises(ConfigError):
                validate_ipv4(value)
        self.assertEqual(validate_port("1883"), 1883)
        for value in (0, 65536, -1, True, 1883.0, "1.5", None):
            with self.assertRaises(ConfigError):
                validate_port(value)

    def test_malformed_json_and_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "invalid.json"
            for text in ('{"broken":', '{"schema_version": NaN}'):
                filename.write_text(text)
                with self.assertRaises(ConfigError):
                    load_config(filename)

    def test_envelope_matches_cpp(self):
        msg = envelope("custom-der", "custom-point", 12.5, "command")
        self.assertEqual(set(msg), {"schema_version", "device_id", "point", "value", "kind", "request_id", "timestamp"})
        self.assertEqual(msg["schema_version"], 1)
        self.assertEqual(msg["value"], 12.5)
        self.assertTrue(msg["timestamp"].endswith("+00:00"))
        self.assertNotEqual(msg["request_id"], envelope("custom-der", "custom-point", 12.5, "command")["request_id"])
        json.dumps(msg, allow_nan=False)

    def test_device_lock_identity_and_release(self):
        device = f"python-check-{os.getpid()}"
        with DeviceLock("127.0.0.1", 1883, device):
            with self.assertRaisesRegex(ConfigError, "deja utilise"):
                DeviceLock("127.0.0.1", 1883, device).acquire()
            with DeviceLock("127.0.0.1", 1884, device):
                pass
            with DeviceLock("127.0.0.1", 1883, device + "-other"):
                pass
        with DeviceLock("127.0.0.1", 1883, device):
            pass

    def test_device_lock_released_on_process_exit(self):
        device = f"python-crash-{os.getpid()}"
        code = ("import os,sys;sys.path.insert(0,sys.argv[1]);"
                "from common.config import DeviceLock;"
                "lock=DeviceLock('127.0.0.1',1883,sys.argv[2]).acquire();os._exit(0)")
        subprocess.run([sys.executable, "-c", code, str(APPS), device], check=True, timeout=5)
        with DeviceLock("127.0.0.1", 1883, device):
            pass


if __name__ == "__main__":
    unittest.main()
