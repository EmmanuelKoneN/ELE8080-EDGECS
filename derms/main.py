"""!
@file main.py
@brief Point d'entrée du serveur DERMS (station maîtresse DNP3).
@author Équipe EDGECS
@date 2026-10-24
@note Lancer depuis la racine du dépôt : python -m derms.main
"""

import asyncio
import logging
import os
from dataclasses import replace
from typing import Final

import uvicorn
from fastapi import FastAPI

from derms.live_data import Der, SystemState
from derms.planification.module_planification import update_soc
from derms.serveur import create_app, create_modules

## Adresse d'écoute de l'interface Web si WEB_ADDRESS_VARIABLE n'est pas définie.
WEB_ADDRESS: Final[str] = "127.0.0.1"

## Variable d'environnement qui remplace WEB_ADDRESS (0.0.0.0 sous Docker).
WEB_ADDRESS_VARIABLE: Final[str] = "EDGECS_WEB_ADDRESS"

## Port de l'interface Web.
WEB_PORT: Final[int] = 8000

## Format des lignes du journal, horodatées (G-013).
LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s : %(message)s"

## Délai laissé aux connexions ouvertes (flux de la page) à l'arrêt du serveur, en secondes.
SHUTDOWN_GRACE_S: Final[int] = 1

## DER dont le SOC varie pendant l'essai (EXEMPLE TEMPORAIRE).
TEST_DER_ID: Final[int] = 1

## SOC atteint avant de redescendre, en % (EXEMPLE TEMPORAIRE).
SOC_MAX_PCT: Final[float] = 100.0

## SOC atteint avant de remonter, en % (EXEMPLE TEMPORAIRE).
SOC_MIN_PCT: Final[float] = 0.0

## Variation du SOC à chaque pas, en % (EXEMPLE TEMPORAIRE).
SOC_STEP_PCT: Final[float] = 1.0

## Délai entre deux pas du SOC, en secondes (EXEMPLE TEMPORAIRE).
SOC_STEP_PERIOD_S: Final[float] = 1.0

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


## INTERDIT LES FOCNTIONS DANS LE MAIN PENSE Y
## @brief Exemple d'ajout : range trois batteries dans l'état central.
## @param[in] state État central.
def add_example_batteries(state: SystemState) -> None:
    state.add_der(Der(1, "Batterie 1", 1, -50.0, 50.0, None, None))
    state.add_der(Der(2, "Batterie 2", 1, -30.0, 30.0, None, None))
    state.add_der(Der(3, "Batterie 3", 2, -40.0, 40.0, None, None))


## @brief Exemple de modification avec contrôle : fixe la puissance voulue d'une DER.
## @param[in] state État central.
## @param[in] der_id Identifiant de la DER.
## @param[in] power_kw Puissance active voulue, en kW.
## @return La DER mise à jour, ou None si elle n'existe pas ou si la puissance est refusée.
def set_desired_output(state: SystemState, der_id: int, power_kw: float) -> Der | None:
    der = state.der(der_id)
    if der is None:
        return None
    if not der.min_power_kw <= power_kw <= der.max_power_kw:
        return None
    updated = replace(der, desired_output_kw=power_kw)
    state.add_der(updated)
    return updated


## @brief Exemple de lecture de toutes les DER : les affiche dans le journal.
## @param[in] state État central.
def log_ders(state: SystemState) -> None:
    for der in state.ders():
        soc = "inconnu" if der.soc is None else f"{der.soc.value} %"
        _LOGGER.info(
            "DER %d « %s » (passerelle %d) : SOC %s, puissance voulue %s kW",
            der.der_id,
            der.name,
            der.gateway_id,
            soc,
            der.desired_output_kw,
        )


## @brief Enchaîne les exemples au démarrage, pour voir l'état central fonctionner.
## @param[in] state État central.
def run_examples(state: SystemState) -> None:
    add_example_batteries(state)
    update_soc(state, 1, 80.0)
    set_desired_output(state, 1, 20.0)
    set_desired_output(state, 2, 500.0)  # hors limites : refusée, la batterie 2 reste inchangée
    log_ders(state)


## @brief Fait monter le SOC d'une DER de 1 % par seconde jusqu'au maximum, puis redescendre
## jusqu'au minimum, sans fin (EXEMPLE TEMPORAIRE, pour voir la page en direct).
## @param[in] state État central.
## @param[in] der_id Identifiant de la DER dont le SOC varie.
async def ramp_soc(state: SystemState, der_id: int) -> None:
    soc = SOC_MIN_PCT
    step = SOC_STEP_PCT
    while True:
        update_soc(state, der_id, soc)
        if soc >= SOC_MAX_PCT:
            step = -SOC_STEP_PCT
        elif soc <= SOC_MIN_PCT:
            step = SOC_STEP_PCT
        soc += step
        await asyncio.sleep(SOC_STEP_PERIOD_S)


## @brief Fait tourner le serveur Web et la rampe de SOC dans la même boucle asyncio.
## @details uvicorn.run() garderait la main jusqu'à l'arrêt : on lance donc le serveur nous-mêmes,
## avec la rampe comme tâche à côté de lui.
## @param[in] app Application Web du DERMS.
## @param[in] host Adresse d'écoute de l'interface Web.
## @param[in] state État central.
async def serve(app: FastAPI, host: str, state: SystemState) -> None:
    config = uvicorn.Config(
        app,
        host=host,
        port=WEB_PORT,
        log_config=None,
        timeout_graceful_shutdown=SHUTDOWN_GRACE_S,
    )
    ramp = asyncio.create_task(ramp_soc(state, TEST_DER_ID))  # EXEMPLE TEMPORAIRE
    await uvicorn.Server(config).serve()
    ramp.cancel()


## @brief Démarre le serveur DERMS et ses modules jusqu'à son arrêt (Ctrl+C).
def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
    web_address = os.environ.get(WEB_ADDRESS_VARIABLE, WEB_ADDRESS)
    # Seul état central du DERMS : créé ici une fois, puis partagé par tous les modules.
    live_data = SystemState()
    run_examples(live_data)
    app = create_app(create_modules(), live_data)
    asyncio.run(serve(app, web_address, live_data))


if __name__ == "__main__":
    main()
