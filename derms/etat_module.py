"""!
@file etat_module.py
@brief États possibles d'un module du DERMS.
@author Équipe EDGECS
@date 2026-10-30
"""

from enum import StrEnum


class ModuleState(StrEnum):
    """!
    @brief État d'un module du DERMS.
    """

    ## Le module n'a pas encore été démarré.
    NOT_STARTED = "non_demarre"

    ## Le démarrage du module s'est terminé sans erreur.
    RUNNING = "demarre"

    ## Le démarrage ou l'arrêt du module a levé une exception.
    FAILED = "en_echec"

    ## L'arrêt du module s'est terminé sans erreur.
    STOPPED = "arrete"
