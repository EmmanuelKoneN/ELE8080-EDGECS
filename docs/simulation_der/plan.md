# Simulation des DER : plan de réalisation

État au 2026-11-03, branche `feature/simulation`. Les identifiants comme `F-403` renvoient au
Tableau 8.1 du cahier des charges (`assets/ELE8080 EDGECS Cahier des charges Rev01.pdf`).
Les choix et leurs raisons sont tenus dans [journal_decisions.md](journal_decisions.md). Toute
modification de ce plan y ajoute une entrée.

## 1. Objet et portée

La passerelle commande et supervise des DER simulées (section 8.4). Le MVP en réalise une seule,
un BESS fondé sur le modèle `DER_BESS` d'EPRI OpenDER. La structure doit permettre d'ajouter
d'autres DER et d'autres types sans toucher au code existant. C'est la condition pour atteindre
trois DER simultanées (G-001).

**Exigences couvertes :** G-001 (structure), G-003, G-011, PH-400, F-401, F-402, F-403, F-404, S-405.

**Hors portée :** outstation DNP3, application réceptrice, `points_dnp3.yaml`, simulation du
réseau au PCC, types de DER autres que le BESS.

## 2. Structure

```
gateway/
├── configuration/
│   └── der.yaml                     paramètres des DER (G-003)
├── simulation_der/
│   ├── modele_der.py                contrat commun à tous les types de DER
│   ├── fabrique_der.py              table type → classes, création depuis la configuration
│   ├── modele_bess.py               BessConfig et BessModel (enveloppe OpenDER)
│   └── module_simulation_der.py     cycle de vie et pas de temps de toutes les DER
└── main.py                          démarre le module
tests/gateway/simulation_der/        tests pytest
```

### Ajouter une DER

| Cas | Travail |
|---|---|
| Une DER d'un type existant (ex. un 2e BESS) | Une entrée dans `der.yaml`, et son identifiant dans `EDGECS_DER_IDS`. Aucun code. |
| Un nouveau type (ex. génératrice) | Un fichier `modele_<type>.py` qui implémente `DerModel` et une configuration `from_mapping()`, une ligne dans `DER_TYPES` de `fabrique_der.py`, ses tests. Aucun autre fichier modifié. |

## 3. Configuration : `gateway/configuration/der.yaml`

```yaml
simulation:
  pas_s: 1

ders:
  der1:
    type: bess
    p_decharge_max_kw: 100
    p_charge_max_kw: 100
    capacite_kwh: 200
    soc_min_pct: 10
    soc_max_pct: 90
    soc_initial_pct: 50
```

- La variable `EDGECS_DER_IDS` (liste séparée par des virgules, défaut `der1`) choisit les DER que
  simule cette passerelle. Le fichier est déjà copié dans l'image par `COPY gateway/`.
- Le pas de simulation est commun à toutes les DER d'un processus (journal D-007).
- La validation est stricte. Une `ValueError` nommant la DER et le champ arrête la passerelle au
  démarrage si :
  - un champ est manquant, inconnu ou de mauvais type ;
  - un type de DER est inconnu ;
  - un identifiant demandé est absent du fichier ;
  - une puissance, la capacité ou le pas n'est pas strictement positif ;
  - on n'a pas `0 ≤ soc_min < soc_initial < soc_max ≤ 100`.

  Aucune valeur par défaut implicite (journal D-010).

## 4. Contrat commun : `modele_der.py`

| Élément | Contenu |
|---|---|
| `OperationalState` | `STOPPED`, `RUNNING` |
| `ConnectionState` | `CONNECTED`, `DISCONNECTED` (le second servira avec un transport réel) |
| `Alarm` | `NONE`, `SOC_LIMIT` (puissance limitée par le SOC), `FAULT` (erreur du modèle) |
| `DerTelemetry` (figée) | `der_id`, `der_type`, `p_kw`, `soc_pct` (`None` hors stockage, F-404), `operational_state`, `connection_state`, `alarm`, `timestamp` UTC (F-401, F-402) |
| `CommandResult` (figée) | `accepted`, `reason` |
| `DerModel` (`Protocol`) | `start()`, `stop()` et `set_active_power(p_kw)`, qui retournent chacune un `CommandResult`, puis `step()` et `telemetry()` (PH-400, F-403) |

**Convention de signe (8.4) :** P > 0 = injection, P < 0 = absorption. OpenDER suit la même.

## 5. Fabrique : `fabrique_der.py`

- `DER_TYPES: Final[dict[str, ...]]` associe chaque type à sa classe de configuration et à sa
  classe de modèle (`"bess"` → `BessConfig`, `BessModel`).
- `create_ders(document, der_ids)` valide la section `simulation`, puis crée chaque DER demandée et
  retourne `dict[str, DerModel]`. C'est le seul endroit qui connaît les types concrets.

## 6. BESS : `modele_bess.py`

`BessConfig.from_mapping()` valide les champs de la section 3. `BessModel(der_id, config, pas_s)`
crée un `DER_BESS` avec les paramètres de `der_file` listés au journal D-011 (kW→W, kWh→Wh, %→pu).

**Commandes.** Les refus sont explicites, sans troncature silencieuse (journal D-004).
- `set_active_power(p_kw)` :
  - refusée si `p_kw` est non fini ou hors de `[-p_charge_max, +p_decharge_max]` (F-403, G-011) ;
  - refusée si l'état n'est pas `RUNNING` (S-405) ;
  - sinon, la consigne est mémorisée.
- `start()` passe à `RUNNING`.
- `stop()` passe à `STOPPED` et remet la consigne à 0. Les deux sont idempotentes.

**Pas de temps : `step()`**
1. La consigne effective est la consigne mémorisée, ou 0 à l'arrêt.
2. **Garde de SOC** (journal D-005). La puissance est bornée à l'énergie disponible jusqu'à la
   limite sur un pas : `(soc − soc_min) · capacité / pas` en décharge, et l'équivalent en charge.
   Le `soc` est celui qui résultera de la puissance du pas précédent, qu'OpenDER n'intègre qu'au
   pas suivant (journal D-011). Le SOC atteint la limite sans la franchir (G-011). `Alarm.SOC_LIMIT` est active tant que la
   garde réduit la consigne. La consigne reste acceptée.
3. Appel de `update_der_input(v_pu=NOMINAL_VOLTAGE_PU, f=NOMINAL_FREQUENCY_HZ, p_dem_pu=…)` puis
   `run()` (journal D-006).
4. **Invariant.** Si le SOC sort des bornes, ou si une sortie est NaN ou infinie, on lève une
   `RuntimeError`.

`telemetry()` retourne l'instantané courant (P en kW, SOC en %).

## 7. Module : `module_simulation_der.py`

`SimulationDerModule` suit la forme des modules du DERMS (`name`, `async start()`,
`async stop()`) et expose `ders: dict[str, DerModel]` pour l'application réceptrice.

- `start()` lit `der.yaml`, crée les DER par la fabrique, puis lance une tâche de pas.
- La tâche fait des pas à échéances absolues (`t0 + k·pas`, horloge monotone), sans dérive.
- Une exception dans le `step()` d'une DER est journalisée avec sa trace. Cette DER passe à
  `STOPPED` et `Alarm.FAULT` et n'est plus avancée. Les autres DER et la passerelle continuent
  (journal D-009).
- `stop()` annule la tâche et l'attend.
- Le journal (`logging`) trace les commandes acceptées ou refusées avec leur raison, et les
  changements d'alarme. Pas de journalisation périodique : un filtre écarte les avertissements
  de SOC qu'OpenDER émet à chaque pas en limite (journal D-011).

## 8. `gateway/main.py`

`main()` passe à `asyncio.run(...)` :
1. Démarrer `SimulationDerModule`.
2. Garder la ligne DNP3 existante.
3. Attendre l'arrêt, puis appeler `stop()` du module sur `SIGTERM` ou Ctrl+C.

## 9. Étapes de réalisation

0. **Vérifier OpenDER sous Python 3.11 / Linux.** Fait, résultats au journal D-011. Ses métadonnées ne déclarent que Python 3.7 sous
   Windows. Installer `opender==2.2.0` dans `.venv` et exécuter l'exemple Ex5 (BESS, SOC). Relever :
   - les unités (W, Wh) et l'échelle de `bess_soc` ;
   - un éventuel rendement dans l'intégration du SOC ;
   - les noms exacts des attributs de `der_file`.

   Consigner les résultats dans le journal. En cas d'échec, revenir vers l'équipe.
1. **Dépendances.** `opender==2.2.0` dans `requirements.txt` (journal D-002). `pytest` dans
   `requirements-dev.txt`. `[tool.pytest.ini_options] testpaths = ["tests"]` dans `pyproject.toml`.
2. Écrire `modele_der.py`.
3. Écrire `modele_bess.py` et ses tests.
4. Écrire `fabrique_der.py`, `der.yaml` et leurs tests.
5. Écrire `module_simulation_der.py` et ses tests.
6. Modifier `gateway/main.py`.
7. **CI.** Étape `pytest` dans `.github/workflows/qualite.yml`, après `ruff check`.
8. **Documentation.**
   - Docstrings Doxygen `"""!` sur tout élément public.
   - Mettre à jour `gateway/simulation_der/README.md` et la section « Modèles DER » de
     `gateway/README.md`, en retirant les TODO correspondants.
   - Mettre à jour ce plan et le journal.

## 10. Tests

Ils appellent `step()` directement, sans temps réel. Le SOC suit la puissance avec un pas de
retard (journal D-011).

| Sujet | Cas |
|---|---|
| Commandes | consigne valide acceptée, P mesurée = consigne ; consigne hors limites, NaN ou envoyée à l'arrêt refusée, état inchangé ; `start`/`stop` idempotents |
| SOC | variation = `P·pas/capacité` à la tolérance près ; charge et décharge prolongées atteignent exactement `soc_max`/`soc_min` sans les franchir ; `SOC_LIMIT` levée puis retombée quand la consigne s'inverse ; même chose avec `p_charge_max ≠ p_decharge_max` (défaut d'OpenDER, D-011) |
| Arrêt | P = 0 dès le pas suivant, SOC figé à partir du second |
| Configuration | chaque champ manquant, inconnu ou incohérent, type inconnu, identifiant absent : `ValueError` |
| Fabrique | deux BESS dans `der.yaml` donnent deux modèles indépendants (G-001) |
| Module | une exception injectée dans une DER donne `FAULT` pour elle seule, les autres continuent ; `stop()` se termine proprement |

## 11. Vérification

1. `pytest` : tout passe.
2. `ruff format --check --diff .` et `ruff check .` : propres.
3. `doxygen Doxyfile` : `doxygen/avertissements.txt` est vide.
4. `docker compose up --build` : `passerelle1` journalise le démarrage de `der1`. Une configuration
   volontairement invalide l'arrête avec un message qui nomme le champ.
