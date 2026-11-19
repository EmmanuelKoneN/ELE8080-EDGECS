"""!
@file module_dnp3_master.py
@brief Client DNP3 (station maîtresse) du DERMS.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


## @brief Client DNP3 (station maîtresse) du DERMS.
class Dnp3MasterModule:
    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "dnp3_master"

    ## @brief Démarre le module.
    async def start(self) -> None:
        pass

    ## @brief Arrête le module.
    async def stop(self) -> None:
        pass
