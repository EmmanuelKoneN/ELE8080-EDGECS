"""!
@file module_simulation_pcc.py
@brief Réseau simulé qui fournit la puissance au PCC.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


## @brief Réseau simulé qui fournit la puissance au PCC.
class SimulationPccModule:
    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "simulation_pcc"

    ## @brief Démarre le module.
    async def start(self) -> None:
        pass

    ## @brief Arrête le module.
    async def stop(self) -> None:
        pass
