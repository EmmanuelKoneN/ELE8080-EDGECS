"""Offline TLS credential regressions; never read or write the user's .local."""

import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import lab


ENVIRONMENT = {
    "token": "EDGECS_REGISTRATION_TOKEN",
    "cert": "EDGECS_TLS_CERT",
    "key": "EDGECS_TLS_KEY",
    "ca": "EDGECS_CA_CERT",
}


class LaboratoryCredentialsTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("openssl"), "openssl is required to create laboratory certificates")
    def test_private_credentials_are_valid_for_both_ips_and_reused(self):
        with tempfile.TemporaryDirectory(prefix="edgecs-tls-test-") as directory:
            local = Path(directory) / "isolated-lab"
            with mock.patch.object(lab, "LOCAL", local), mock.patch.object(
                lab.secrets, "token_urlsafe", wraps=lab.secrets.token_urlsafe,
            ) as random_token:
                settings = lab.prepare_lab("127.0.0.2")
                random_token.assert_called_once_with(32)
                self.assertIsInstance(settings["token"], str)
                self.assertGreaterEqual(len(settings["token"]), 16)
                self.assertRegex(settings["token"], r"^[A-Za-z0-9_-]+$")
                self.assertEqual(local.stat().st_mode & 0o777, 0o700)
                self.assertEqual(Path(settings["key"]).stat().st_mode & 0o777, 0o600)
                manifest = local / "lab.json"
                self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(manifest.read_text(encoding="utf-8")), settings)

                # Validate trust, matching key material, and actual IP SANs
                # without creating listeners or depending on network services.
                server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                server_context.load_cert_chain(settings["cert"], settings["key"])
                client_context = ssl.create_default_context(cafile=settings["ca"])
                self.assertEqual(client_context.verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(client_context.check_hostname)
                self.assertTrue(client_context.get_ca_certs())
                for host in ("127.0.0.1", "127.0.0.2"):
                    with self.subTest(host=host):
                        checked = subprocess.run(
                            ["openssl", "x509", "-in", settings["cert"], "-noout", "-checkip", host],
                            capture_output=True, text=True, timeout=10, check=False,
                        )
                        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                        self.assertIn("does match certificate", checked.stdout,
                                      checked.stdout + checked.stderr)

                original_bytes = {path: Path(path).read_bytes() for path in
                                  (settings["cert"], settings["key"], str(manifest))}
                self.assertEqual(lab.prepare_lab("127.0.0.2"), settings)
                random_token.assert_called_once_with(32)
                for path, content in original_bytes.items():
                    self.assertEqual(Path(path).read_bytes(), content,
                                     "An existing trust anchor must not be replaced")

    def test_environment_overrides_saved_values_and_invalid_addresses_create_nothing(self):
        clean_environment = {key: value for key, value in os.environ.items()
                             if key not in ENVIRONMENT.values()}
        with tempfile.TemporaryDirectory(prefix="edgecs-lab-settings-test-") as directory:
            local = Path(directory) / "isolated-lab"
            with mock.patch.object(lab, "LOCAL", local), mock.patch.dict(
                os.environ, clean_environment, clear=True,
            ):
                for host in ("8.8.8.8", "0.0.0.0", "not-an-ip", "::1"):
                    with self.subTest(host=host), self.assertRaises(ValueError):
                        lab.prepare_lab(host)
                self.assertFalse(local.exists(), "Invalid addresses must not create credential files")
                saved = {name: "saved-" + name for name in ENVIRONMENT}
                local.mkdir(mode=0o700)
                (local / "lab.json").write_text(json.dumps(saved), encoding="utf-8")
                self.assertEqual(lab.load_lab_settings(), saved)
                explicit = {variable: "explicit-" + name for name, variable in ENVIRONMENT.items()}
                with mock.patch.dict(os.environ, explicit):
                    self.assertEqual(lab.load_lab_settings(),
                                     {name: "explicit-" + name for name in ENVIRONMENT})
                with mock.patch.dict(os.environ, {"EDGECS_REGISTRATION_TOKEN": "", "EDGECS_CA_CERT": "chosen-ca"}):
                    self.assertEqual(lab.load_lab_settings(), dict(saved, token="", ca="chosen-ca"))


if __name__ == "__main__":
    unittest.main()
