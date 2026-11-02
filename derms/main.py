"""!
@file main.py
@brief Point d'entrée du serveur DERMS (station maîtresse DNP3).
@author Équipe EDGECS
@date 2026-10-24
@note Lancer depuis la racine du dépôt : python -m derms.main
"""

import logging
import os
from typing import Final

import uvicorn

from derms.serveur import create_app, create_modules

## Adresse de la passerelle DNP3 à joindre si GATEWAY_ADDRESS_VARIABLE n'est pas définie.
GATEWAY_ADDRESS: Final[str] = "127.0.0.1"

## Variable d'environnement qui remplace GATEWAY_ADDRESS (nom de la passerelle sous Docker).
GATEWAY_ADDRESS_VARIABLE: Final[str] = "EDGECS_GATEWAY_ADDRESS"

## Port DNP3 de la passerelle.
GATEWAY_PORT: Final[int] = 20000

## Adresse d'écoute de l'interface Web si WEB_ADDRESS_VARIABLE n'est pas définie.
WEB_ADDRESS: Final[str] = "127.0.0.1"

## Variable d'environnement qui remplace WEB_ADDRESS (0.0.0.0 sous Docker).
WEB_ADDRESS_VARIABLE: Final[str] = "EDGECS_WEB_ADDRESS"

## Port de l'interface Web.
WEB_PORT: Final[int] = 8000

## Format des lignes du journal, horodatées (G-013).
LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s : %(message)s"


def main() -> None:
    """!
    @brief Démarre le serveur DERMS et ses modules jusqu'à son arrêt (Ctrl+C).
    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    web_address = os.environ.get(WEB_ADDRESS_VARIABLE, WEB_ADDRESS)
    uvicorn.run(create_app(create_modules()), host=web_address, port=WEB_PORT, log_config=None)


if __name__ == "__main__":
    main()
