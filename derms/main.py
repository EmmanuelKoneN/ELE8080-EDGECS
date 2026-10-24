"""!
@file main.py
@brief Point d'entrée du serveur DERMS (station maîtresse DNP3).
@author Équipe EDGECS
@date 2026-10-24
@note Lancer depuis la racine du dépôt : python -m derms.main
"""

from typing import Final

## Adresse de la passerelle DNP3 à joindre.
GATEWAY_ADDRESS: Final[str] = "127.0.0.1"

## Port DNP3 de la passerelle.
GATEWAY_PORT: Final[int] = 20000


def main() -> None:
    """!
    @brief Démarre le DERMS et se connecte à la passerelle.
    """
    print(f"DERMS : connexion à la gateway {GATEWAY_ADDRESS}:{GATEWAY_PORT} (à implémenter)")


if __name__ == "__main__":
    main()
