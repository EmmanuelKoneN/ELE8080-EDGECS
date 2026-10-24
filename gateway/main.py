"""!
@file main.py
@brief Point d'entrée de la passerelle DER (station semi-asservie DNP3).
@author Équipe EDGECS
@date 2026-10-24
@note Lancer depuis la racine du dépôt : python -m gateway.main [port]
"""

import sys
from typing import Final

## Adresse d'écoute de l'outstation DNP3.
LISTEN_ADDRESS: Final[str] = "127.0.0.1"

## Port DNP3 utilisé si aucun port n'est donné en argument.
DEFAULT_PORT: Final[int] = 20000

## Position du port dans les arguments de la ligne de commande.
PORT_ARGUMENT_INDEX: Final[int] = 1


def read_port(arguments: list[str]) -> int:
    """!
    @brief Détermine le port d'écoute de la passerelle.
    @param[in] arguments Arguments de la ligne de commande (sys.argv).
    @return Le port donné en premier argument, ou DEFAULT_PORT s'il est absent.
    @throw ValueError Si l'argument n'est pas un entier.
    """
    if len(arguments) <= PORT_ARGUMENT_INDEX:
        return DEFAULT_PORT

    return int(arguments[PORT_ARGUMENT_INDEX])


def main() -> None:
    """!
    @brief Démarre la passerelle et attend les commandes du DERMS.
    """
    port = read_port(sys.argv)
    print(f"Gateway : écoute DNP3 sur {LISTEN_ADDRESS}:{port} (à implémenter)")


if __name__ == "__main__":
    main()
