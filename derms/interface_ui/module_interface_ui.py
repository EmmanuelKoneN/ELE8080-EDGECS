"""!
@file module_interface_ui.py
@brief Application Web de l'opérateur.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage. stream_der sert aux essais de
l'état central.
"""

from collections.abc import AsyncIterator

from fastapi import Request

from derms.live_data import Der


## @brief Envoie une DER à la page Web dès l'ouverture, puis à chacun de ses changements.
## @details La page devient abonnée de l'état central le temps de sa connexion. Quand elle se
## ferme, FastAPI arrête cette fonction et l'abonnement est retiré.
## @param[in] request Requête reçue, qui donne accès à l'état central.
## @param[in] der_id Identifiant de la DER, pris dans l'adresse de la requête.
## @return Un flux d'événements, une DER par événement.
async def stream_der(request: Request, der_id: int) -> AsyncIterator[Der]:
    state = request.app.state.system_state
    queue = state.subscribe()
    try:
        current = state.der(der_id)
        if current is not None:
            yield current
        while True:
            der = await queue.get()
            if der.der_id == der_id:
                yield der
    finally:
        state.unsubscribe(queue)


## @brief Application Web de l'opérateur.
class InterfaceUiModule:
    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "interface_ui"

    ## @brief Démarre le module.
    async def start(self) -> None:
        pass

    ## @brief Arrête le module.
    async def stop(self) -> None:
        pass
