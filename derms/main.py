"""!
@file main.py
@brief Point d'entrée du serveur DERMS (station maîtresse DNP3).
@author Équipe EDGECS
@date 2026-10-24
@note Lancer depuis la racine du dépôt : python -m derms.main
"""

import logging
from typing import Final

import uvicorn

from derms.serveur import create_app, create_modules

## Adresse de la passerelle DNP3 à joindre.
GATEWAY_ADDRESS: Final[str] = "127.0.0.1"

## Port DNP3 de la passerelle.
GATEWAY_PORT: Final[int] = 20000

## Adresse d'écoute de l'interface Web.
WEB_ADDRESS: Final[str] = "127.0.0.1"

## Port de l'interface Web.
WEB_PORT: Final[int] = 8000

## Format des lignes du journal, horodatées (G-013).
LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s : %(message)s"


def main() -> None:
    """!
    @brief Démarre le serveur DERMS et ses modules jusqu'à son arrêt (Ctrl+C).
    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    uvicorn.run(create_app(create_modules()), host=WEB_ADDRESS, port=WEB_PORT, log_config=None)


if __name__ == "__main__":
    main()
