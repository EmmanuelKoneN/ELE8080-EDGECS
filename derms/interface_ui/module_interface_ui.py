"""!
@file module_interface_ui.py
@brief Application Web de l'opérateur.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


class InterfaceUiModule:
    """!
    @brief Application Web de l'opérateur.
    """

    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "interface_ui"

    async def start(self) -> None:
        """!
        @brief Démarre le module.
        """

    async def stop(self) -> None:
        """!
        @brief Arrête le module.
        """
