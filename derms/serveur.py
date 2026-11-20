"""!
@file serveur.py
@brief Application Web du DERMS et supervision du cycle de vie de ses modules.
@details Le serveur ne fournit que des données JSON sous /api. L'interface opérateur est faite de
fichiers fixes qui lisent cette API depuis le navigateur.
@author Équipe EDGECS
@date 2026-10-30
@note Répond à F-144. Le contrat des modules n'est pas encore décidé par l'équipe : un module est
pour l'instant tout objet qui offre name, start() et stop().
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.sse import EventSourceResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from derms.configuration.module_configuration import ConfigurationModule
from derms.dnp3_master.module_dnp3_master import Dnp3MasterModule
from derms.etat_module import ModuleState
from derms.initialisation.module_initialisation import InitialisationModule
from derms.interface_ui.module_interface_ui import InterfaceUiModule, stream_der
from derms.live_data import SystemState
from derms.planification.module_planification import PlanificationModule
from derms.simulation_pcc.module_simulation_pcc import SimulationPccModule
from derms.stockage.module_stockage import StockageModule

## Chemin de l'API qui indique l'état du serveur en JSON.
HEALTH_API_PATH: Final[str] = "/api/sante"

## Chemin du flux d'événements (SSE) qui envoie une DER à chacun de ses changements.
DER_STREAM_API_PATH: Final[str] = "/api/der/{der_id}/flux"

## Dossier des fichiers fixes (HTML, CSS, JS) de l'interface opérateur, servis sur « / ».
INTERFACE_DIR: Final[Path] = Path(__file__).parent / "interface_ui" / "static"

## Consigne de cache envoyée avec les fichiers de l'interface : le navigateur peut les garder, mais
## doit vérifier auprès du serveur à chaque chargement qu'ils n'ont pas changé.
INTERFACE_CACHE_CONTROL: Final[str] = "no-cache"

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


## @brief Sert les fichiers de l'interface en obligeant le navigateur à revalider son cache.
## @details Sans consigne, le navigateur peut réutiliser une ancienne version d'index.html ou
## d'app.js après une mise à jour. Avec « no-cache », il redemande le fichier à chaque chargement ;
## le serveur répond 304 (sans renvoyer le fichier) s'il n'a pas changé.
class NoCacheStaticFiles(StaticFiles):
    ## @brief Prépare la réponse d'un fichier et y ajoute la consigne de cache.
    ## @param[in] full_path Chemin du fichier sur le disque.
    ## @param[in] stat_result Informations du fichier (taille, date de modification).
    ## @param[in] scope Description de la requête reçue.
    ## @param[in] status_code Code HTTP de la réponse.
    ## @return La réponse, avec l'en-tête Cache-Control.
    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = INTERFACE_CACHE_CONTROL ##eviter les maj non fonctionnel
        return response


## @brief Démarre et arrête les modules, et retient l'état de chacun.
## @details L'échec d'un module n'arrête pas le serveur : l'interface Web doit rester accessible
## pour signaler l'erreur à l'opérateur (PF-113).
class ModuleSupervisor:
    ## @brief Prépare la supervision des modules.
    ## @param[in] modules Modules, dans leur ordre de démarrage.
    def __init__(self, modules: list[Any]) -> None:
        self._modules = modules
        self._states = {module.name: ModuleState.NOT_STARTED for module in modules}

    ## @brief Donne l'état actuel des modules.
    ## @return Une copie de l'état de chaque module, par nom de module.
    @property
    def states(self) -> dict[str, ModuleState]:
        return dict(self._states)

    ## @brief Démarre les modules dans l'ordre, même si l'un d'eux échoue.
    async def start_all(self) -> None:
        for module in self._modules:
            await self._start(module)

    ## @brief Arrête les modules démarrés, dans l'ordre inverse du démarrage.
    async def stop_all(self) -> None:
        for module in reversed(self._modules):
            if self._states[module.name] is ModuleState.RUNNING:
                await self._stop(module)

    async def _start(self, module: Any) -> None:
        try:
            await module.start()
        except Exception:
            self._states[module.name] = ModuleState.FAILED
            _LOGGER.exception("Module %s : échec du démarrage", module.name)
            return

        self._states[module.name] = ModuleState.RUNNING
        _LOGGER.info("Module %s : démarré", module.name)

    async def _stop(self, module: Any) -> None:
        try:
            await module.stop()
        except Exception:
            self._states[module.name] = ModuleState.FAILED
            _LOGGER.exception("Module %s : échec de l'arrêt", module.name)
            return

        self._states[module.name] = ModuleState.STOPPED
        _LOGGER.info("Module %s : arrêté", module.name)


## @brief Crée les modules du DERMS.
## @return Les modules, dans leur ordre de démarrage.
def create_modules() -> list[Any]:
    return [
        ConfigurationModule(),
        StockageModule(),
        InitialisationModule(),
        Dnp3MasterModule(),
        SimulationPccModule(),
        PlanificationModule(),
        InterfaceUiModule(),
    ]


## @brief Démarre les modules avec le serveur et les arrête avec lui.
## @param[in] app Application dont l'état contient le superviseur.
## @return Un itérateur actif tant que le serveur fonctionne.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    supervisor = app.state.supervisor
    await supervisor.start_all()
    yield
    await supervisor.stop_all()


## @brief Indique l'état du serveur et de ses modules.
## @param[in] request Requête reçue, qui donne accès au superviseur.
## @return Le statut global et l'état de chaque module.
async def read_health(request: Request) -> dict[str, Any]:
    states = request.app.state.supervisor.states
    is_healthy = all(state is ModuleState.RUNNING for state in states.values())
    return {"statut": "ok" if is_healthy else "degrade", "modules": states}


## @brief Crée l'application Web du DERMS.
## @param[in] modules Modules à superviser, dans leur ordre de démarrage.
## @param[in] system_state État central partagé, gardé pour les futures routes de l'API.
## @return L'application prête à être servie.
def create_app(modules: list[Any], system_state: SystemState) -> FastAPI:
    app = FastAPI(title="DERMS EDGECS", lifespan=lifespan)
    app.state.supervisor = ModuleSupervisor(modules)
    app.state.system_state = system_state
    app.add_api_route(HEALTH_API_PATH, read_health)
    app.add_api_route(DER_STREAM_API_PATH, stream_der, response_class=EventSourceResponse)
    # Monté en dernier : « / » intercepterait sinon les routes de l'API.
    app.mount("/", NoCacheStaticFiles(directory=INTERFACE_DIR, html=True), name="interface")
    return app
