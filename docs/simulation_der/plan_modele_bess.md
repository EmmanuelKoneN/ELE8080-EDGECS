# Plan de réalisation : `gateway/simulation_der/modele_bess.py`

État au 2026-11-19, branche `feature/simulation`. Ce document détaille l'étape 3 du
[plan de simulation des DER](plan.md) : le modèle BESS et ses tests. Les codes D-xxx renvoient au
[journal des décisions](journal_decisions.md), et les exigences à [docs/exigences.md](../exigences.md).

Le fichier implémente le contrat `DerModel` de `modele_der.py` pour un BESS. Il enveloppe le modèle
`DER_BESS` d'EPRI OpenDER 2.2.0 (D-002).

## Vérifications faites sur OpenDER

Essai : 100 kW, 200 kWh, SOC de 10 à 90 %, décharge à 100 kW depuis 12 %, pas de 1 s.

- **Q vaut 0** avec les réglages par défaut. OpenDER renvoie `-0.0`, à convertir en `0.0`.
- **La courbe de puissance par SOC est plate.** Après `initialize_NP_BESS_P_MAX_BY_SOC()`, P reste
  à 100 kW jusqu'à SOC_min, puis tombe d'un coup à 0. OpenDER ne réduit pas la puissance
  progressivement près des limites : la réduction vient de notre garde de SOC (D-005).

## Décision : configuration en anglais

Les clés de `der.yaml` sont en anglais, comme les champs du code. Une clé correspond directement
à un champ de `BessConfig`, sans table de traduction.

```yaml
simulation:
  step_s: 1

ders:
  der1:
    type: bess
    discharge_max_kw: 100
    charge_max_kw: 100
    capacity_kwh: 200
    soc_min_pct: 10
    soc_max_pct: 90
    soc_initial_pct: 50
```

Les valeurs sont des exemples choisis par l'équipe, pas des valeurs du cahier des charges.

## Étapes

### 1. En-tête et constantes

- Docstring Doxygen `"""!` avec `@file`, `@brief`, `@author` et `@date`, comme dans `modele_der.py`.
- Constantes `Final` :

| Constante | Valeur | Rôle |
|---|---|---|
| `DER_TYPE` | `"bess"` | Type déclaré dans `der.yaml` et dans la télémétrie (F-401) |
| `NOMINAL_VOLTAGE_PU` | `1.0` | \|V\| appliqué aux bornes du modèle (D-006, D-013) |
| `NOMINAL_VOLTAGE_ANGLE_DEG` | `0.0` | ∠V, phase de référence (D-013) |
| `NOMINAL_FREQUENCY_HZ` | `60.0` | f appliquée aux bornes du modèle (D-006) |
| `REACTIVE_POWER_RATIO` | `0.44` | Q_max = 0,44 × S_max, sinon OpenDER avertit (D-011) |
| `W_PER_KW` | `1000` | Conversion kW → W et kWh → Wh |
| `PERCENT_PER_PU` | `100` | Conversion % → pu |
| `SECONDS_PER_HOUR` | `3600` | Conversion pour l'énergie d'un pas |

### 2. `BessConfig`

Une `@dataclass(frozen=True)` avec les champs `discharge_max_kw`, `charge_max_kw`, `capacity_kwh`,
`soc_min_pct`, `soc_max_pct` et `soc_initial_pct` (F-401, F-404).

`BessConfig.from_mapping(der_id, mapping)` lit la section de la DER dans `der.yaml`, sans la clé
`type`. Elle lève une `ValueError` qui nomme la DER et le champ (D-010) si :
- une clé manque ou est inconnue ;
- une valeur n'est pas un nombre (un `bool` est refusé) ;
- une puissance ou la capacité n'est pas strictement positive ;
- on n'a pas `0 ≤ soc_min_pct < soc_initial_pct < soc_max_pct ≤ 100`.

Aucune valeur par défaut implicite.

### 3. Création : `BessModel.__init__(der_id, config, step_s)`

- Fixe `DER.t_s = step_s` : le pas est commun à toutes les DER du processus (D-007).
- Crée `DER_BESS(**paramètres)` selon le tableau de D-011, puis appelle
  `der_file.initialize_NP_BESS_P_MAX_BY_SOC()` :

| `BessConfig` | `der_file` | Conversion |
|---|---|---|
| `discharge_max_kw` | `NP_P_MAX`, `NP_VA_MAX` | × 1000 (W, VA) |
| `charge_max_kw` | `NP_P_MAX_CHARGE`, `NP_APPARENT_POWER_CHARGE_MAX` | × 1000 (W, VA), positif |
| `capacity_kwh` | `NP_BESS_CAPACITY` | × 1000 (Wh) |
| `soc_min_pct`, `soc_max_pct`, `soc_initial_pct` | `NP_BESS_SOC_MIN`, `NP_BESS_SOC_MAX`, `SOC_INIT` | ÷ 100 (pu) |
| — | `NP_EFFICIENCY` | 1 |
| — | `NP_Q_MAX_INJ`, `NP_Q_MAX_ABS` | `REACTIVE_POWER_RATIO` × `NP_VA_MAX` |

- État initial : `STOPPED`, `CONNECTED`, consigne à 0, `AlarmState.NONE`. La télémétrie de départ
  a P = Q = 0 et le SOC initial.

### 4. Commandes

Chaque commande renvoie un `CommandResult`. Une consigne refusée ne modifie pas l'état (D-004).

- `set_active_power(p_kw)` est refusée, avec sa raison, si :
  - `p_kw` est non fini (NaN, infini) : OpenDER changerait un NaN en pleine charge (D-011) ;
  - `p_kw` est hors de `[−charge_max_kw, +discharge_max_kw]` (F-403, G-011) ;
  - la DER n'est pas `RUNNING` (S-405).

  Sinon, la consigne est mémorisée. Elle n'est jamais ramenée à la limite.
- `start()` passe à `RUNNING`.
- `stop()` passe à `STOPPED` et remet la consigne à 0.
- `start()` et `stop()` sont idempotentes : un second appel ne change rien.

### 5. `step()`

1. **Consigne effective** : la consigne mémorisée, ou 0 à l'arrêt.
2. **Garde de SOC** (D-005, G-011). OpenDER n'intègre la puissance d'un pas qu'au pas suivant
   (D-011). On calcule donc d'abord le SOC qu'il aura après avoir intégré la puissance du pas
   précédent, puis on borne la consigne pour que ce pas-ci ne fasse pas franchir la limite :
   - en décharge : `P ≤ (SOC − SOC_min) × capacité × 3600 / pas` ;
   - en charge : `P ≥ −(SOC_max − SOC) × capacité × 3600 / pas`.

   `SOC_LIMIT` est active si la garde a réduit la consigne, et retombe sinon. La consigne
   mémorisée reste inchangée.
3. **Modèle** : `update_der_input(v_pu=NOMINAL_VOLTAGE_PU, f=NOMINAL_FREQUENCY_HZ, p_dem_kw=…)`, puis
   `run()`. L'angle n'est pas passé à OpenDER (D-013).
4. **Invariant** : si P, Q ou le SOC est NaN ou infini, ou si le SOC sort de [SOC_min, SOC_max], on
   lève une `RuntimeError`.
5. **Télémétrie** : P (`p_out_kw`), Q (`q_out_kvar`) et SOC (`bess_soc` × 100) convertis en `float`,
   \|V\|, ∠V et f nominaux, horodatage UTC (G-013).

### 6. `telemetry()`

Retourne la télémétrie calculée par le dernier appel à `step()`.

### 7. Tests : `tests/gateway/simulation_der/test_modele_bess.py`

Ils appellent `step()` directement, sans temps réel, avec la configuration d'exemple ci-dessus.

| Sujet | Cas |
|---|---|
| Configuration | configuration valide acceptée ; chaque clé manquante ou inconnue, valeur non numérique ou `bool`, puissance ou capacité ≤ 0, SOC incohérent : `ValueError` qui nomme le champ |
| Commandes | consigne valide acceptée, P mesurée = consigne au pas suivant ; consigne hors limites, NaN ou envoyée à l'arrêt refusée, état inchangé ; `start`/`stop` idempotents |
| SOC | variation = `P × pas / capacité` à la tolérance près ; décharge et charge prolongées s'arrêtent pile à 10 % et 90 % sans les franchir ; `SOC_LIMIT` levée puis retombée quand la consigne s'inverse ; même chose avec `charge_max_kw ≠ discharge_max_kw` (défaut d'OpenDER, D-011) |
| Télémétrie (F-402) | Q = 0 ; \|V\| = 1,0 pu, ∠V = 0°, f = 60 Hz ; tous les champs finis |
| Arrêt | P = 0 dès le pas suivant |

Pour que pytest trouve le paquet `gateway`, ajouter `pythonpath = ["."]` dans
`[tool.pytest.ini_options]` de `pyproject.toml`.

### 8. Vérification et commit

1. `pytest` : tout passe.
2. `ruff format .` et `ruff check .` : propres.
3. `doxygen Doxyfile` : `doxygen/avertissements.txt` reste vide.
4. Commit sur `feature/simulation`.

## Question ouverte : qui met la DER en `FAULT`

Le [plan](plan.md) (section 7) dit que le module de simulation met une DER en `STOPPED` et
`FAULT` quand son `step()` lève une erreur. Mais le contrat `DerModel` n'offre aucune méthode
pour le faire : le module ne peut pas changer l'état interne d'un BESS.

Option envisagée : `step()` attrape sa propre erreur, passe la DER en `STOPPED` + `FAULT`, puis
relance l'erreur pour que le module la journalise. `start()` serait alors refusée en `FAULT`. Le
contrat ne changerait pas.

À trancher avant l'étape 5 du [plan](plan.md) (module de simulation). D'ici là, `step()` lève
seulement une `RuntimeError`, et les tests de défaut sont reportés.
