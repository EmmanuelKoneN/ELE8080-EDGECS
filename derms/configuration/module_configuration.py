"""!
@file module_configuration.py
@brief Lecture des IP, des ports, des points DNP3 et des limites (G-003).
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


## @brief Lecture des IP, des ports, des points DNP3 et des limites (G-003).
class ConfigurationModule:
    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "configuration"

    ## @brief Démarre le module.
    async def start(self) -> None:
        pass

    ## @brief Arrête le module.
    async def stop(self) -> None:
        pass
