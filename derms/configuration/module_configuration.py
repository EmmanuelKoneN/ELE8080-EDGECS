"""!
@file module_configuration.py
@brief Lecture des IP, des ports, des points DNP3 et des limites (G-003).
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


class ConfigurationModule:
    """!
    @brief Lecture des IP, des ports, des points DNP3 et des limites (G-003).
    """

    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "configuration"

    async def start(self) -> None:
        """!
        @brief Démarre le module.
        """

    async def stop(self) -> None:
        """!
        @brief Arrête le module.
        """
