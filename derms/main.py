"""!
@file main.py
@brief Point d'entrée du serveur DERMS (station maîtresse DNP3).
@author Équipe EDGECS
@date 2026-10-24
@note Lancer depuis la racine du dépôt : python -m derms.main
"""

import logging
import os
from dataclasses import replace
from datetime import UTC, datetime
from typing import Final

import uvicorn

from derms.donnees_partagees import Der, Measurement, SystemState
from derms.serveur import create_app, create_modules

## Adresse d'écoute de l'interface Web si WEB_ADDRESS_VARIABLE n'est pas définie.
WEB_ADDRESS: Final[str] = "127.0.0.1"

## Variable d'environnement qui remplace WEB_ADDRESS (0.0.0.0 sous Docker).
WEB_ADDRESS_VARIABLE: Final[str] = "EDGECS_WEB_ADDRESS"

## Port de l'interface Web.
WEB_PORT: Final[int] = 8000

## Format des lignes du journal, horodatées (G-013).
LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s : %(message)s"

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


## @brief Exemple d'ajout : range trois batteries dans l'état central.
## @param[in] state État central.
def add_example_batteries(state: SystemState) -> None:
    state.add_der(Der(1, "Batterie 1", 1, -50.0, 50.0, None, None))
    state.add_der(Der(2, "Batterie 2", 1, -30.0, 30.0, None, None))
    state.add_der(Der(3, "Batterie 3", 2, -40.0, 40.0, None, None))


## @brief Exemple de lecture : cherche une DER par son identifiant.
## @param[in] state État central.
## @param[in] der_id Identifiant de la DER cherchée.
## @return La DER, ou None si aucune DER n'a cet identifiant.
def find_der(state: SystemState, der_id: int) -> Der | None:
    for der in state.ders():
        if der.der_id == der_id:
            return der
    return None


## @brief Exemple de modification : enregistre un nouvel état de charge.
## @param[in] state État central.
## @param[in] der_id Identifiant de la DER.
## @param[in] soc_pct Nouvel état de charge, en %.
## @return La DER mise à jour, ou None si elle n'existe pas.
def update_soc(state: SystemState, der_id: int, soc_pct: float) -> Der | None:
    der = find_der(state, der_id)
    if der is None:
        return None
    now = datetime.now(UTC)
    updated = replace(der, soc=Measurement(soc_pct, now, now))
    state.add_der(updated)
    return updated


## @brief Exemple de modification avec contrôle : fixe la puissance voulue d'une DER.
## @param[in] state État central.
## @param[in] der_id Identifiant de la DER.
## @param[in] power_kw Puissance active voulue, en kW.
## @return La DER mise à jour, ou None si elle n'existe pas ou si la puissance est refusée.
def set_desired_output(state: SystemState, der_id: int, power_kw: float) -> Der | None:
    der = find_der(state, der_id)
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


## @brief Démarre le serveur DERMS et ses modules jusqu'à son arrêt (Ctrl+C).
def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
    web_address = os.environ.get(WEB_ADDRESS_VARIABLE, WEB_ADDRESS)
    # Seul état central du DERMS : créé ici une fois, puis partagé par tous les modules.
    state = SystemState()
    run_examples(state)  # EXEMPLE TEMPORAIRE : à retirer avant la PR
    app = create_app(create_modules(), state)
    uvicorn.run(app, host=web_address, port=WEB_PORT, log_config=None)


if __name__ == "__main__":
    main()
