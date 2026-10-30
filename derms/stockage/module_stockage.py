"""!
@file module_stockage.py
@brief Stockage local de l'inventaire, des horaires et du journal.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


class StockageModule:
    """!
    @brief Stockage local de l'inventaire, des horaires et du journal.
    """

    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "stockage"

    async def start(self) -> None:
        """!
        @brief Démarre le module.
        """

    async def stop(self) -> None:
        """!
        @brief Arrête le module.
        """
