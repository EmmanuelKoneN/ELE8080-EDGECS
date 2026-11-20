"""!
@file live_data.py
@brief État central des dernières valeurs connues, partagées entre les modules.
@author Équipe EDGECS
@date 2026-11-20
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Final

## Nombre de changements gardés pour un abonné lent ; au-delà, les plus anciens sont perdus.
SUBSCRIBER_QUEUE_SIZE: Final[int] = 100


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
## @details À n'utiliser que depuis la boucle asyncio : les écritures ne contiennent aucun await,
## ce qui les rend sûres sans verrou.
class SystemState:
    ## @brief Crée un état vide, sans aucune DER ni abonné.
    def __init__(self) -> None:
        self._ders: dict[int, Der] = {}
        self._subscribers: list[asyncio.Queue[Der]] = []

    ## @brief Ajoute une DER, ou remplace celle qui a le même identifiant (F-121).
    ## @details Chaque abonné reçoit la DER ajoutée dans sa file.
    ## @param[in] der DER à ajouter.
    def add_der(self, der: Der) -> None:
        self._ders[der.der_id] = der
        self._publish(der)

    ## @brief Donne toutes les DER connues.
    ## @return Une copie de la liste des DER.
    def ders(self) -> list[Der]:
        return list(self._ders.values())

    ## @brief Donne une DER par son identifiant.
    ## @param[in] der_id Identifiant de la DER.
    ## @return La DER, ou None si aucune DER n'a cet identifiant.
    def der(self, der_id: int) -> Der | None:
        return self._ders.get(der_id)

    ## @brief Abonne un lecteur aux changements des DER.
    ## @return Une file qui recevra chaque DER ajoutée ou modifiée.
    def subscribe(self) -> asyncio.Queue[Der]:
        queue: asyncio.Queue[Der] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.append(queue)
        return queue

    ## @brief Désabonne un lecteur, par exemple quand une page Web se ferme.
    ## @param[in] queue File reçue de subscribe().
    def unsubscribe(self, queue: asyncio.Queue[Der]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    # Dépose la DER dans la file de chaque abonné ; une file pleine perd son plus ancien avis.
    def _publish(self, der: Der) -> None:
        for queue in self._subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(der)
