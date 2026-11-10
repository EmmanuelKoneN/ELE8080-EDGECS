"""Configuration and wire-format helpers aligned with ``shared/common.cpp``.

This module intentionally has no Qt dependency, so configurations can also be
checked from scripts and tests without a desktop session.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[2]
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]+\Z", re.ASCII)


class ConfigError(ValueError):
    """An invalid configuration or a preventable local startup conflict."""


def validate_ipv4(value: str) -> str:
    if not isinstance(value, str):
        raise ConfigError("Adresse IPv4 attendue (ex. 127.0.0.1).")
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as exc:
        raise ConfigError(f"Adresse IPv4 invalide : {value!r}.") from exc


def validate_port(value) -> int:
    """Validate a port, allowing decimal text from a GUI input field."""
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        value = int(value)
    if type(value) is not int or not 1 <= value <= 65535:
        raise ConfigError("Le port doit etre un entier entre 1 et 65535.")
    return value


def _integer(value, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _number(value) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _keys(obj: dict, allowed: set[str], where: str) -> None:
    extra = obj.keys() - allowed
    if extra:
        raise ConfigError(f"Cle inconnue dans {where} : {sorted(extra)[0]}.")


def _identifier(value, field: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ConfigError(f"{field} doit contenir uniquement A-Z, a-z, 0-9, _ ou -.")


def validate_value(point: dict, value):
    """Require the same finite numbers/strict booleans and AO limits as C++."""
    kind = point.get("dnp3_type")
    name = point.get("name", "?")
    if kind in ("AI", "AO"):
        if not _number(value):
            raise ConfigError(f"Point {name} : nombre analogique fini attendu.")
        if kind == "AO" and not point["min"] <= value <= point["max"]:
            raise ConfigError(
                f"Point {name} : valeur hors limites [{point['min']}, {point['max']}]."
            )
    elif kind in ("BI", "BO"):
        if type(value) is not bool:
            raise ConfigError(f"Point {name} : booleen JSON attendu (true/false).")
    else:
        raise ConfigError(f"Point {name} : type DNP3 non pris en charge : {kind}.")
    return value


def validate_config(cfg: dict) -> dict:
    """Validate all structural and cross-point constraints enforced by C++."""
    if not isinstance(cfg, dict) or type(cfg.get("schema_version")) is not int or cfg["schema_version"] != 1:
        raise ConfigError("schema_version doit etre l'entier 1.")
    _keys(cfg, {"schema_version", "device_id", "name", "der_type", "dnp3", "mqtt",
                "master_api_host", "master_api_port", "points"}, "la racine JSON")
    _identifier(cfg.get("device_id"), "device_id")
    for field in ("name", "der_type"):
        if not isinstance(cfg.get(field), str) or not cfg[field]:
            raise ConfigError(f"{field} doit etre une chaine non vide.")
    dnp3 = cfg.get("dnp3")
    if not isinstance(dnp3, dict):
        raise ConfigError("Objet dnp3 manquant.")
    _keys(dnp3, {"host", "port", "master_address", "outstation_address"}, "dnp3")
    validate_ipv4(dnp3.get("host"))
    if not _integer(dnp3.get("port"), 65535) or dnp3["port"] == 0:
        raise ConfigError("dnp3.port doit etre un entier entre 1 et 65535.")
    for field in ("master_address", "outstation_address"):
        if not _integer(dnp3.get(field), 65519):
            raise ConfigError(f"dnp3.{field} doit etre un entier entre 0 et 65519.")
    if dnp3["master_address"] == dnp3["outstation_address"]:
        raise ConfigError("Les adresses logiques DNP3 Master et Outstation doivent differer.")
    if "mqtt" in cfg:
        mqtt = cfg["mqtt"]
        if not isinstance(mqtt, dict):
            raise ConfigError("mqtt doit etre un objet contenant host et port.")
        _keys(mqtt, {"host", "port"}, "mqtt")
        validate_ipv4(mqtt.get("host"))
        if not _integer(mqtt.get("port"), 65535) or mqtt["port"] == 0:
            raise ConfigError("mqtt.port doit etre un entier entre 1 et 65535.")
    if "master_api_host" in cfg:
        validate_ipv4(cfg["master_api_host"])
    if "master_api_port" in cfg and (
        not _integer(cfg["master_api_port"], 65535) or cfg["master_api_port"] == 0
    ):
        raise ConfigError("master_api_port doit etre un entier entre 1 et 65535.")
    points = cfg.get("points")
    if not isinstance(points, list) or not points:
        raise ConfigError("points doit etre une liste non vide.")
    names = set()
    indexes = set()
    aliases = set()
    for point in points:
        if not isinstance(point, dict):
            raise ConfigError("Chaque point doit etre un objet JSON.")
        _keys(point, {"name", "alias", "direction", "dnp3_type", "index", "unit",
                      "min", "max", "initial", "feedback_point"}, "un point")
        name = point.get("name")
        _identifier(name, "Le nom du point")
        if name in names:
            raise ConfigError(f"Nom de point duplique : {name}.")
        names.add(name)
        kind = point.get("dnp3_type")
        if kind not in ("AI", "BI", "AO", "BO"):
            raise ConfigError(f"Point {name} : type DNP3 invalide.")
        direction = "command" if kind in ("AO", "BO") else "telemetry"
        if point.get("direction") != direction:
            raise ConfigError(f"Point {name} : direction incompatible avec {kind}.")
        index = point.get("index")
        if not _integer(index, 65535):
            raise ConfigError(f"Point {name} : index doit etre un entier entre 0 et 65535.")
        if (kind, index) in indexes:
            raise ConfigError(f"Index DNP3 duplique : {kind}[{index}].")
        indexes.add((kind, index))
        if not isinstance(point.get("unit"), str):
            raise ConfigError(f"Point {name} : unit doit etre une chaine.")
        alias = point.get("alias", name)
        _identifier(alias, f"L'alias de {name}")
        if (direction, alias) in aliases:
            raise ConfigError(f"Alias duplique dans {direction} : {alias}.")
        aliases.add((direction, alias))
        if "feedback_point" in point and not isinstance(point["feedback_point"], str):
            raise ConfigError(f"Point {name} : feedback_point doit etre une chaine.")
        if kind == "AO":
            if not _number(point.get("min")) or not _number(point.get("max")) or point["min"] >= point["max"]:
                raise ConfigError(f"Point {name} : limites AO invalides (min < max requis).")
        elif "min" in point or "max" in point:
            raise ConfigError(f"Point {name} : min/max reserves aux commandes AO.")
        if direction == "telemetry":
            if "feedback_point" in point:
                raise ConfigError(f"Point {name} : feedback_point reserve aux commandes.")
            if "initial" in point:
                validate_value(point, point["initial"])
        elif "initial" in point:
            raise ConfigError(f"Point {name} : initial reserve aux telemesures.")
    by_name = {point["name"]: point for point in points}
    for point in points:
        target_name = point.get("feedback_point")
        if "feedback_point" in point:
            target = by_name.get(target_name)
            wanted = "AI" if point["dnp3_type"] == "AO" else "BI"
            if target is None or target["direction"] != "telemetry":
                raise ConfigError(f"Point {point['name']} : feedback_point inconnu : {target_name}.")
            if target["dnp3_type"] != wanted:
                raise ConfigError(f"Point {point['name']} : type du feedback_point incompatible.")
        alias = point.get("alias", point["name"])
        other = by_name.get(alias)
        if other is not None and other is not point and other["direction"] == point["direction"]:
            raise ConfigError(f"Alias identique au nom d'un autre point : {alias}.")
    return cfg


def _bad_constant(value: str):
    raise ConfigError(f"Nombre JSON non fini interdit : {value}.")


def load_config(path) -> dict:
    try:
        with open(path, encoding="utf-8") as stream:
            cfg = json.load(stream, parse_constant=_bad_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Configuration {path} : {exc}") from exc
    return validate_config(cfg)


def envelope(device: str, point: str, value, kind: str) -> dict:
    return {"schema_version": 1, "device_id": device, "point": point,
            "value": value, "kind": kind, "request_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}


def runtime_config(cfg: dict, master_host: str, gateway_host: str, dnp3_port,
                   mqtt_host: str, mqtt_port, api_port=8443) -> dict:
    """Return a validated deep copy; never mutate the user's selected JSON."""
    validate_config(cfg)
    result = copy.deepcopy(cfg)
    result["master_api_host"] = validate_ipv4(master_host)
    result["master_api_port"] = validate_port(api_port)
    result["dnp3"]["host"] = validate_ipv4(gateway_host)
    result["dnp3"]["port"] = validate_port(dnp3_port)
    result["mqtt"] = {"host": validate_ipv4(mqtt_host), "port": validate_port(mqtt_port)}
    return validate_config(result)


def check_bind(host: str, port) -> None:
    """Check that an IPv4 listener can bind locally; does not reserve the port."""
    host, port = validate_ipv4(host), validate_port(port)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((host, port))
    except OSError as exc:
        raise ConfigError(f"Ecoute {host}:{port} impossible (port occupe ou IP non locale) : {exc}") from exc


def find_executable(name: str) -> str:
    """Find an existing executable; explicit environment overrides take priority."""
    definitions = {
        "master": ("EDGECS_MASTER_BIN", "DERMS", ("edgecs_master",)),
        "gateway": ("EDGECS_GATEWAY_BIN", "Gateway", ("edgecs_gateway",)),
        "simulator": ("EDGECS_SIMULATOR_BIN", "Gateway", ("edgecs_bess_sim", "edgecs_der_sim")),
    }
    aliases = {"edgecs_master": "master", "edgecs_gateway": "gateway",
               "edgecs_bess_sim": "simulator", "edgecs_der_sim": "simulator"}
    name = aliases.get(name, name)
    if name not in definitions:
        raise ConfigError(f"Executable EDGECS inconnu : {name}.")
    variable, project, binaries = definitions[name]
    override = os.environ.get(variable)
    if override:
        candidate = Path(override).expanduser().resolve()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        raise ConfigError(f"{variable} ne designe pas un executable valide : {candidate}")
    directories = [ROOT / project / "build", ROOT / "build" / project, ROOT / "build"]
    directories.extend(sorted((ROOT / project).glob("build-*")))
    for directory in directories:
        for variant in (directory, directory / "Release", directory / "Debug"):
            for binary in binaries:
                candidate = variant / binary
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return str(candidate.resolve())
    for binary in binaries:
        candidate = shutil.which(binary)
        if candidate:
            return candidate
    raise ConfigError(f"Executable {binaries[0]} introuvable. Compilez {project} ou definissez {variable}.")


class TemporaryConfig:
    """A mode-0600 configuration in a private, instance-specific directory."""

    def __init__(self, cfg: dict):
        validate_config(cfg)
        self._directory = tempfile.TemporaryDirectory(prefix="edgecs-config-")
        self.path = str(Path(self._directory.name) / "outstation.json")
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(cfg, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
        except Exception:
            self.cleanup()
            raise

    def cleanup(self) -> None:
        self._directory.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()


class DeviceLock:
    """Prevent two local GUI instances from sharing a broker/device identity.

    Kernel locks are released on crashes. Lock files deliberately stay in place:
    unlinking a locked file would let another process lock a different inode.
    The Master registry remains responsible for conflicts on other machines.
    """

    def __init__(self, host: str, port, device: str):
        self.host = validate_ipv4(host)
        self.port = validate_port(port)
        _identifier(device, "device_id")
        self.device = device
        self._fd = None

    def acquire(self):
        if self._fd is not None:
            return self
        directory = Path(tempfile.gettempdir()) / f"edgecs-device-locks-{os.getuid()}"
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
            metadata = directory.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
                raise ConfigError(f"Dossier de verrous non securise : {directory}.")
            key = f"{self.host}:{self.port}:{self.device}".encode("utf-8")
            filename = hashlib.sha256(key).hexdigest() + ".lock"
            dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                fd = os.open(filename, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=dirfd)
            finally:
                os.close(dirfd)
            try:
                metadata = os.fstat(fd)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077 or metadata.st_nlink != 1:
                    raise ConfigError("Fichier de verrou non securise.")
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise ConfigError(
                        f"device_id deja utilise par une autre DER App : {self.device} "
                        f"sur {self.host}:{self.port}."
                    ) from exc
                os.ftruncate(fd, 0)
                os.write(fd, f"{os.getpid()}\n".encode("ascii"))
                self._fd = fd
            except Exception:
                os.close(fd)
                raise
        except OSError as exc:
            raise ConfigError(f"Verrou de device_id impossible : {exc}") from exc
        return self

    def release(self) -> None:
        if self._fd is not None:
            descriptor, self._fd = self._fd, None
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.release()
