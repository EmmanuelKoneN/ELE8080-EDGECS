"""!
@file serveur.py
@brief Application Web du DERMS et supervision du cycle de vie de ses modules.
@author Équipe EDGECS
@date 2026-10-30
@note Répond à F-144. Le contrat des modules n'est pas encore décidé par l'équipe : un module est
pour l'instant tout objet qui offre name, start() et stop().
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from derms.configuration.module_configuration import ConfigurationModule
from derms.dnp3_master.module_dnp3_master import Dnp3MasterModule
from derms.etat_module import ModuleState
from derms.initialisation.module_initialisation import InitialisationModule
from derms.interface_ui.module_interface_ui import InterfaceUiModule
from derms.interface_ui.page_sante import render_health_page
from derms.planification.module_planification import PlanificationModule
from derms.simulation_pcc.module_simulation_pcc import SimulationPccModule
from derms.stockage.module_stockage import StockageModule

## Chemin de la page Web qui indique l'état du serveur.
HEALTH_PAGE_PATH: Final[str] = "/sante"

## Chemin de l'API qui indique l'état du serveur en JSON.
HEALTH_API_PATH: Final[str] = "/api/sante"

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


class ModuleSupervisor:
    """!
    @brief Démarre et arrête les modules, et retient l'état de chacun.
    @details L'échec d'un module n'arrête pas le serveur : l'interface Web doit rester accessible
    pour signaler l'erreur à l'opérateur (PF-113).
    """

    def __init__(self, modules: list[Any]) -> None:
        """!
        @brief Prépare la supervision des modules.
        @param[in] modules Modules, dans leur ordre de démarrage.
        """
        self._modules = modules
        self._states = {module.name: ModuleState.NOT_STARTED for module in modules}

    @property
    def states(self) -> dict[str, ModuleState]:
        """!
        @brief Donne l'état actuel des modules.
        @return Une copie de l'état de chaque module, par nom de module.
        """
        return dict(self._states)

    async def start_all(self) -> None:
        """!
        @brief Démarre les modules dans l'ordre, même si l'un d'eux échoue.
        """
        for module in self._modules:
            await self._start(module)

    async def stop_all(self) -> None:
        """!
        @brief Arrête les modules démarrés, dans l'ordre inverse du démarrage.
        """
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


def create_modules() -> list[Any]:
    """!
    @brief Crée les modules du DERMS.
    @return Les modules, dans leur ordre de démarrage.
    """
    return [
        ConfigurationModule(),
        StockageModule(),
        InitialisationModule(),
        Dnp3MasterModule(),
        SimulationPccModule(),
        PlanificationModule(),
        InterfaceUiModule(),
    ]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """!
    @brief Démarre les modules avec le serveur et les arrête avec lui.
    @param[in] app Application dont l'état contient le superviseur.
    @return Un itérateur actif tant que le serveur fonctionne.
    """
    supervisor = app.state.supervisor
    await supervisor.start_all()
    yield
    await supervisor.stop_all()


async def read_health(request: Request) -> dict[str, Any]:
    """!
    @brief Indique l'état du serveur et de ses modules.
    @param[in] request Requête reçue, qui donne accès au superviseur.
    @return Le statut global et l'état de chaque module.
    """
    states = request.app.state.supervisor.states
    is_healthy = all(state is ModuleState.RUNNING for state in states.values())
    return {"statut": "ok" if is_healthy else "degrade", "modules": states}


async def read_health_page(request: Request) -> str:
    """!
    @brief Présente l'état des modules dans une page Web lisible.
    @param[in] request Requête reçue, qui donne accès au superviseur.
    @return Le document HTML de la page.
    """
    return render_health_page(request.app.state.supervisor.states)


def create_app(modules: list[Any]) -> FastAPI:
    """!
    @brief Crée l'application Web du DERMS.
    @param[in] modules Modules à superviser, dans leur ordre de démarrage.
    @return L'application prête à être servie.
    """
    app = FastAPI(title="DERMS EDGECS", lifespan=lifespan)
    app.state.supervisor = ModuleSupervisor(modules)
    app.add_api_route(HEALTH_API_PATH, read_health)
    app.add_api_route(HEALTH_PAGE_PATH, read_health_page, response_class=HTMLResponse)
    return app
