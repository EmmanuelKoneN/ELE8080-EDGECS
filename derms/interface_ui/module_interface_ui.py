"""!
@file module_interface_ui.py
@brief Application Web de l'opérateur.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


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
