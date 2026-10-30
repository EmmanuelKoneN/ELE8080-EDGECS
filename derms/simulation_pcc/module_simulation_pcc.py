"""!
@file module_simulation_pcc.py
@brief Réseau simulé qui fournit la puissance au PCC.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


class SimulationPccModule:
    """!
    @brief Réseau simulé qui fournit la puissance au PCC.
    """

    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "simulation_pcc"

    async def start(self) -> None:
        """!
        @brief Démarre le module.
        """

    async def stop(self) -> None:
        """!
        @brief Arrête le module.
        """
