"""!
@file modele_der.py
@brief Contrat commun à tous les modèles de DER simulées (PH-400, F-401 à F-404).
@author Flavio Zapata
@date 2026-11-19
@note Chaque type de DER implémente DerModel.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class OperationalState(StrEnum):
    """!
    @brief État opérationnel d'une DER (F-402, S-405).
    """

    ## La DER est arrêtée : elle n'applique aucune consigne et sa puissance est nulle.
    STOPPED = "stopped"

    ## La DER est en marche et peut appliquer une consigne de puissance.
    RUNNING = "running"


class ConnectionState(StrEnum):
    """!
    @brief État de connexion entre la DER et sa passerelle (F-402).
    """

    ## La DER échange des données avec sa passerelle.
    CONNECTED = "connected"

    ## La DER ne répond plus à sa passerelle.
    DISCONNECTED = "disconnected"


class AlarmState(StrEnum):
    """!
    @brief État d'alarme d'une DER (F-402).
    """

    ## Aucune alarme.
    NONE = "none"

    ## La puissance appliquée est réduite pour garder le SOC dans ses limites.
    SOC_LIMIT = "soc_limit"

    ## Le modèle de la DER a levé une erreur ; la DER n'est plus simulée.
    FAULT = "fault"


@dataclass(frozen=True)
class DerTelemetry:
    """!
    @brief Télémesures, états et alarme qu'une DER retourne à sa passerelle à un instant donné
           (PH-400, F-401, F-402, F-404).
    @note Convention de signe : P > 0 = injection vers le réseau, P < 0 = absorption.
    """

    ## Identifiant unique de la DER (F-401).
    der_id: str

    ## Type de la DER, tel que déclaré dans la configuration (F-401).
    der_type: str

    ## Module de la tension aux bornes, en pu (F-402).
    v_pu: float

    ## Angle de phase de la tension aux bornes, en degrés (F-402).
    v_angle_deg: float

    ## Fréquence aux bornes, en Hz (F-402).
    f_hz: float

    ## Puissance active, en kW (F-402).
    p_kw: float

    ## Puissance réactive, en kvar (F-402).
    q_kvar: float

    ## État de charge en %, ou None pour une DER sans stockage (F-404).
    soc_pct: float | None

    ## État opérationnel (F-402).
    operational_state: OperationalState

    ## État de connexion (F-402).
    connection_state: ConnectionState

    ## État d'alarme (F-402).
    alarm_state: AlarmState

    ## Moment de la mesure, en UTC (G-013).
    timestamp: datetime


@dataclass(frozen=True)
class CommandResult:
    """!
    @brief Résultat d'une commande envoyée à une DER : acceptée ou refusée (G-005).
    """

    ## Vrai si la commande est appliquée.
    accepted: bool

    ## Raison du refus, ou None si la commande est acceptée.
    reason: str | None


class DerModel(Protocol):
    """!
    @brief Contrat que tout modèle de DER simulée doit respecter (PH-400, F-403).
    @note Une classe le respecte en définissant ces méthodes, sans héritage.
    """

    def start(self) -> CommandResult:
        """!
        @brief Démarre la DER (F-403). Sans effet si elle est déjà en marche.
        @return Le résultat de la commande.
        """
        ...

    def stop(self) -> CommandResult:
        """!
        @brief Arrête la DER et remet sa consigne à 0 (F-403). Sans effet si elle est déjà arrêtée.
        @return Le résultat de la commande.
        """
        ...

    def set_active_power(self, p_kw: float) -> CommandResult:
        """!
        @brief Mémorise une consigne de puissance active (F-403).
        @param[in] p_kw Consigne en kW ; P > 0 = injection, P < 0 = absorption.
        @return Un refus avec sa raison si la consigne est non finie, hors des limites déclarées
                (G-011) ou si l'état de la DER ne le permet pas (S-405). Une consigne hors
                limites n'est jamais ramenée à la limite : le DERMS doit savoir qu'elle est
                refusée.
        """
        ...

    def step(self) -> None:
        """!
        @brief Avance le modèle d'un pas de simulation.
        @throw RuntimeError Si le modèle produit un état invalide (SOC hors limites, NaN).
        """
        ...

    def telemetry(self) -> DerTelemetry:
        """!
        @brief Donne les télémesures et les états à un instant donné (F-402).
        @return Les télémesures calculées par le dernier appel à step().
        """
        ...
