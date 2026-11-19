"""!
@file donnees_partagees.py
@brief État central des dernières valeurs connues, partagées entre les modules.
@author Équipe EDGECS
@date 2026-11-20
"""

from dataclasses import dataclass
from datetime import datetime


## @brief Télémesure reçue, avec ses deux horodatages (G-013).
@dataclass(frozen=True, slots=True)
class Measurement:
    ## Valeur mesurée, dans l'unité du point.
    value: float

    ## Heure de la mesure donnée par la passerelle.
    source_time: datetime

    ## Heure de réception, lue sur l'horloge du DERMS.
    received_at: datetime


## @brief DER de type batterie, seul type du MVP (F-118, F-119).
@dataclass(frozen=True, slots=True)
class Der:
    ## Identifiant unique de la DER.
    der_id: int

    ## Nom affiché à l'opérateur.
    name: str

    ## Identifiant de la passerelle par laquelle la DER est jointe.
    gateway_id: int

    ## Puissance active minimale admise, en kW (négative en charge).
    min_power_kw: float

    ## Puissance active maximale admise, en kW.
    max_power_kw: float

    ## Dernier état de charge reçu, en % ; None tant qu'aucune mesure n'est arrivée.
    soc: Measurement | None

    ## Puissance active voulue par le DERMS, en kW ; None tant qu'aucune n'est décidée.
    desired_output_kw: float | None


## @brief Alarme à signaler à l'opérateur (G-007).
@dataclass(frozen=True, slots=True)
class Alarm:
    ## Nom du module qui a levé l'alarme.
    source: str
    ## Description lisible par l'opérateur.
    message: str
    ## DER concernée ; None si l'alarme ne vise pas une DER en particulier.
    der_id: int | None
    ## Heure à laquelle l'alarme a été levée.
    raised_at: datetime


## @brief Dernières valeurs connues du système, partagées par tous les modules du DERMS.
class SystemState:
    ## @brief Crée un état vide, sans aucune DER.
    def __init__(self) -> None:
        self._ders: dict[int, Der] = {}

    ## @brief Ajoute une DER, ou remplace celle qui a le même identifiant (F-121).
    ## @param[in] der DER à ajouter.
    def add_der(self, der: Der) -> None:
        self._ders[der.der_id] = der

    ## @brief Donne toutes les DER connues.
    ## @return Une copie de la liste des DER.
    def ders(self) -> list[Der]:
        return list(self._ders.values())
