"""!
@file module_initialisation.py
@brief Enregistrement des DER et tenue de leur inventaire.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


class InitialisationModule:
    """!
    @brief Enregistrement des DER et tenue de leur inventaire.
    """

    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "initialisation"

    async def start(self) -> None:
        """!
        @brief Démarre le module.
        """

    async def stop(self) -> None:
        """!
        @brief Arrête le module.
        """
