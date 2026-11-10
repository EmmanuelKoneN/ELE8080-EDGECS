"""Optional local TLS credentials shared by the two test applications."""
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess

LOCAL = Path(__file__).resolve().parents[1] / ".local"


def load_lab_settings():
    saved = {}
    manifest = LOCAL / "lab.json"
    if manifest.is_file():
        try:
            saved = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    names = {"token": "EDGECS_REGISTRATION_TOKEN", "cert": "EDGECS_TLS_CERT",
             "key": "EDGECS_TLS_KEY", "ca": "EDGECS_CA_CERT"}
    return {key: os.environ.get(env, saved.get(key, "")) for key, env in names.items()}


def prepare_lab(host="127.0.0.1"):
    """Create credentials once; never silently replace an existing trust anchor."""
    address = ipaddress.IPv4Address(host)
    if not (address.is_private or address.is_loopback) or address.is_unspecified:
        raise ValueError("Utilisez une adresse locale privée pour les essais.")
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    manifest = LOCAL / "lab.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        for name in ("cert", "key", "ca"):
            if not Path(saved[name]).is_file():
                raise ValueError(f"Accès locaux incomplets : {saved[name]}")
        return saved
    cert, key = LOCAL / "server.crt", LOCAL / "server.key"
    if cert.exists() or key.exists():
        raise ValueError("Certificat local partiel : choisissez d’autres accès ou examinez TestApps/.local.")
    # The child inherits a restrictive umask; private keys are never world-readable.
    result = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:3072", "-sha256", "-nodes",
         "-keyout", str(key), "-out", str(cert), "-days", "30",
         "-subj", "/CN=EDGECS laboratory",
         "-addext", f"subjectAltName=DNS:localhost,IP:127.0.0.1,IP:{address}"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, umask=0o077)
    if result.returncode:
        key.unlink(missing_ok=True)
        cert.unlink(missing_ok=True)
        raise ValueError("Création TLS impossible : " + result.stderr[-1500:])
    key.chmod(0o600)
    saved = dict(token=secrets.token_urlsafe(32), cert=str(cert), key=str(key), ca=str(cert))
    descriptor = os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(saved, stream)
    return saved
