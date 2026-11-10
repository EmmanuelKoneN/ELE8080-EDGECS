"""Small, TLS-verified HTTPS client. Call methods from GUI worker threads."""

from __future__ import annotations

import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

from .config import validate_ipv4, validate_port


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        # Never forward the registration bearer token to a redirected endpoint.
        return None


class ApiClient:
    """Read-only discovery API with bounded requests and no TLS bypass.

    Instances have immutable request configuration and can be used by worker
    threads. No method performs Qt operations or starts a nested event loop.
    """

    def __init__(self, host: str, port=8443, token: str | None = None,
                 ca_cert: str | None = None, timeout: float = 4.0):
        self.base_url = f"https://{validate_ipv4(host)}:{validate_port(port)}"
        self.token = os.environ.get("EDGECS_REGISTRATION_TOKEN", "") if token is None else token
        self.ca_cert = os.environ.get("EDGECS_CA_CERT", "") if ca_cert is None else ca_cert
        if not isinstance(self.token, str) or "\r" in self.token or "\n" in self.token:
            raise ApiError("EDGECS_REGISTRATION_TOKEN invalide.")
        if not 0 < timeout <= 60:
            raise ApiError("Delai HTTPS invalide (0 < timeout <= 60 secondes).")
        self.timeout = timeout

    def _get(self, path: str, authenticated: bool = True):
        if authenticated and not self.token:
            raise ApiError("EDGECS_REGISTRATION_TOKEN manquant pour l'API HTTPS.")
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + self.token
        request = Request(self.base_url + path, headers=headers, method="GET")
        try:
            context = ssl.create_default_context(cafile=self.ca_cert or None)
            opener = build_opener(HTTPSHandler(context=context), _NoRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                body = response.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise ApiError("Reponse HTTPS trop volumineuse (limite : 4 Mio).")
            return json.loads(body.decode("utf-8"))
        except HTTPError as exc:
            try:
                detail = exc.read(1024).decode("utf-8", errors="replace")
            finally:
                exc.close()
            if exc.code == 401:
                detail = "Authentification refusee : verifiez EDGECS_REGISTRATION_TOKEN."
            raise ApiError(f"API HTTPS {exc.code} : {detail}", status=exc.code) from exc
        except (ssl.SSLError, ssl.CertificateError) as exc:
            raise ApiError(f"Erreur TLS : {exc}. Verifiez EDGECS_CA_CERT et le certificat du Master.") from exc
        except URLError as exc:
            if isinstance(exc.reason, ssl.SSLError):
                raise ApiError(f"Erreur TLS : {exc.reason}. Verifiez EDGECS_CA_CERT et l'adresse du certificat.") from exc
            raise ApiError(f"Master inaccessible ({self.base_url}) : {exc.reason}") from exc
        except (OSError, ValueError, UnicodeError) as exc:
            raise ApiError(f"Requete HTTPS impossible : {exc}") from exc

    def devices(self) -> list[dict]:
        response = self._get("/api/v1/outstations")
        if not isinstance(response, dict) or not isinstance(response.get("outstations"), list):
            raise ApiError("Reponse de registre invalide : liste outstations attendue.")
        if any(not isinstance(item, dict) for item in response["outstations"]):
            raise ApiError("Reponse de registre invalide : descripteurs d'Outstations attendus.")
        return response["outstations"]

    def device(self, device_id: str) -> dict:
        response = self._get("/api/v1/outstations/" + quote(device_id, safe=""))
        if not isinstance(response, dict):
            raise ApiError("Reponse de DER invalide : objet JSON attendu.")
        return response

    def health(self) -> dict:
        response = self._get("/health", authenticated=False)
        if not isinstance(response, dict) or response.get("status") != "ok":
            raise ApiError("Le Master n'annonce pas un statut operationnel.")
        return response
