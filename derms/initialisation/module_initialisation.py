"""!
@file module_initialisation.py
@brief Enregistrement des DER et tenue de leur inventaire.
@author Équipe EDGECS
@date 2026-10-30
@note Squelette : le module confirme seulement son démarrage.
"""


## @brief Enregistrement des DER et tenue de leur inventaire.
class InitialisationModule:
    ## Nom du module affiché dans le journal et sur /sante.
    name: str = "initialisation"

    ## @brief Démarre le module.
    async def start(self) -> None:
        pass

    ## @brief Arrête le module.
    async def stop(self) -> None:
        pass
