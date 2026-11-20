"""!
@file module_planification.py
@brief Planification et gestion de la puissance des DER.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage. update_soc sert aux essais de
l'état central.
"""

from dataclasses import replace
from datetime import UTC, datetime

from derms.live_data import Der, Measurement, SystemState


## @brief Enregistre un nouvel état de charge pour une DER.
## @details La fiche Der est figée : on en crée une copie modifiée, que l'état central range à la
## place de l'ancienne et transmet à ses abonnés.
## @param[in] state État central.
## @param[in] der_id Identifiant de la DER.
## @param[in] soc_pct Nouvel état de charge, en %.
## @return La DER mise à jour, ou None si elle n'existe pas.
def update_soc(state: SystemState, der_id: int, soc_pct: float) -> Der | None:
    der = state.der(der_id)
    if der is None:
        return None
    now = datetime.now(UTC)
    updated = replace(der, soc=Measurement(soc_pct, now, now))
    state.add_der(updated)
    return updated


## @brief Planification et gestion de la puissance des DER.
class PlanificationModule:
    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "planification"

    ## @brief Démarre le module.
    async def start(self) -> None:
        pass

    ## @brief Arrête le module.
    async def stop(self) -> None:
        pass
