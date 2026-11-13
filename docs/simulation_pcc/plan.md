# Simulation du réseau au PCC : plan de réalisation

État au 2026-11-13, branche `feature/simulation`. Les identifiants comme `F-107` renvoient au
Tableau 8.1 du cahier des charges (`assets/ELE8080 EDGECS Cahier des charges Rev01.pdf`).
Les choix et leurs raisons sont tenus dans [journal_decisions.md](journal_decisions.md). Toute
modification de ce plan y ajoute une entrée. Trois décisions sont encore **à valider** (section 4).

## 1. Objet et portée

Le module `derms/simulation_pcc/` réalise le bloc « Simulation du réseau (grid simulé) » de
l'architecture (section 8.1). Il simule la charge d'un site industriel et fournit au DERMS la
puissance appelée au réseau d'Hydro-Québec, au point de couplage commun (PCC). Sans ce module, la
planification n'a rien à écrêter et PF-109 ne peut pas être mesuré.

**Exigences couvertes :** F-107, F-137 (données), PF-109 (mesure), Q-115 (scénarios
reproductibles), G-003, G-013, et l'injection de la panne réseau pour F-108 et PF-112.

**Exigences servies sans être réalisées ici :** F-100 (le profil attendu est lu dans le même
fichier, mais c'est la planification qui l'exploite), F-108 et PF-112 (les plans de contingence
appartiennent à la planification).

**Hors portée :** algorithme d'écrêtage, seuil de l'opérateur (F-134), affichage (F-137 côté
interface), historique des mesures (stockage), tension et fréquence du réseau, scénario de perte de
communication avec une DER (il se provoque en arrêtant une passerelle).

## 2. Ce que représente le PCC

Le PCC est le point où le site se raccorde au réseau. Deux familles de grandeurs y sont mesurées :

| Grandeur | Comportement | Traitement |
|---|---|---|
| Tension, fréquence | Quasi constantes : le réseau principal est raide | Non simulées (journal D-007) |
| Puissance active P_PCC | Variable : c'est la puissance que le site tire du réseau | Objet du module |

La puissance au PCC est le bilan du site :

```
P_PCC(t) = P_charge(t) − Σ P_DER(t)
```

| Grandeur | Signe positif | Source |
|---|---|---|
| P_charge | consommation de l'usine | profil du scénario (section 6) |
| P_DER | injection (convention de la section 8.4) | télémesures des DER |
| P_PCC | importation depuis le réseau ; négative = exportation | bilan |

Sans gestion, Σ P_DER = 0 et P_PCC = P_charge. P_charge est donc aussi la courbe « sans
l'action des DER » demandée par F-137, et la référence de PF-109. Une seule exécution du scénario
suffit à comparer les deux pointes : pas besoin d'un essai séparé sans DERMS.

**P_PCC n'est pas constante.** Le réseau fournit à chaque instant ce que le site lui demande.
Le peak shaving ne rend pas P_PCC constante : il la plafonne au seuil fixé par l'opérateur
(F-134). Ce seuil est la seule grandeur constante. Exemple avec le scénario de la section 5 et un
seuil de 357 kW :

| Moment | P_charge (kW) | Σ P_DER (kW) | P_PCC sans DERMS (kW) | P_PCC avec DERMS (kW) |
|---|---|---|---|---|
| Creux | 150 | −60 (recharge) | 150 | 210 |
| Quart normal | 300 | 0 | 300 | 300 |
| Pointe | 450 | +93 | 450 | 357 |
| Pointe et écart | 510 | +153 | 510 | 357 |

La pointe au PCC passe de 510 à 357 kW, soit −30 % (PF-109). Pendant le creux, P_PCC est plus
haute que sans gestion : les batteries reprennent l'énergie qu'elles rendront pendant la pointe.

## 3. Entrées et sorties

### Entrées

| Entrée | Contenu | Exigence |
|---|---|---|
| Fichier de scénario | profil de la charge, écarts, pannes du réseau (section 5) | G-003, Q-115 |
| Mesures des DER (option A seulement) | par DER : `p_kw` et horodatage de la mesure, lus dans le client DNP3 | F-107 |
| Horloge | monotone pour le temps de scénario, UTC pour l'horodatage | G-013 |

### Sorties

`mesure() -> MesurePcc`, instantané figé, lu par la planification et l'interface :

| Champ | Contenu | Exigence |
|---|---|---|
| `t_scenario_s` | temps écoulé depuis le début du scénario | Q-115 |
| `horodatage` | UTC | G-013 |
| `p_charge_kw` | puissance de la charge, écarts compris | F-137 (sans DER), PF-109 |
| `p_pcc_kw` | bilan au PCC (option A) ; absent en option B | F-107, F-137 (avec DER) |
| `der_perimees` | identifiants des DER dont la mesure est plus vieille que `mesure_perimee_s` (option A) | PF-110, PF-111 |
| `reseau_disponible` | `False` pendant une panne programmée | F-108, PF-112 |

Le journal (`logging`) trace le début et la fin de chaque panne et de chaque écart, et le passage
d'une DER à l'état périmé puis son retour.

## 4. Décisions à valider

### 4.1 Qui calcule P_PCC (journal D-003)

Les télémesures arrivent au DERMS par le client DNP3 (`dnp3_master`). La passerelle n'est qu'une
outstation : elle tient les points à jour, et la station maîtresse les lit (F-145).

| | **A. `simulation_pcc` fait le bilan** | **B. La planification fait le bilan** |
|---|---|---|
| Principe | lit les P_DER dans `dnp3_master`, fournit P_PCC | ne fournit que P_charge ; la planification soustrait les P_DER qu'elle lit déjà |
| F-107 | respecté à la lettre : la planification reçoit la puissance du réseau | respecté par interprétation : elle reçoit la charge et calcule la puissance du réseau |
| Fidélité | se comporte comme un compteur au PCC. Un simulateur externe ou un vrai compteur le remplacerait sans toucher à la planification | la planification calcule ce qu'un vrai site mesurerait |
| Dépendances | `simulation_pcc` dépend de `dnp3_master` | `simulation_pcc` ne dépend de rien |
| Télémesures périmées | traitées dans `simulation_pcc` (`der_perimees`) **et** dans la planification (F-105) | traitées à un seul endroit |
| Essais | il faut fournir de fausses mesures de DER | P_charge est une fonction du temps seul, triviale à tester |

**Recommandation : A.** Elle respecte F-107 sans interprétation et garde la planification
indépendante de la façon dont P_PCC est obtenue. Le couplage avec `dnp3_master` est limité à une
fonction injectée à la construction (section 7), ce qui garde les essais simples. B reste
défendable si l'équipe préfère un seul lecteur des télémesures.

### 4.2 Échelle de temps (journal D-004)

Le cahier des charges demande un profil journalier (8.1), mais une démonstration de 30 min
(G-006). Les DER de la passerelle intègrent leur SOC en temps réel (`pas_s`).
Les deux simulations doivent donc partager la même échelle de temps, sinon le bilan d'énergie
est faux. Par exemple, une pointe de 2 h jouée en 2,5 min viderait 48 fois moins la batterie.

| | **a. Temps réel, journée de démonstration** | **b. Accélération commune** |
|---|---|---|
| Principe | le profil a la forme d'une journée, mais dure `periode_min` (ex. 30 min). Les capacités des BESS sont réduites dans `der.yaml` pour que le SOC varie de façon visible | un facteur unique (ex. ×48) est lu par le DERMS et par chaque passerelle. Le profil et les capacités sont réalistes |
| Exigences temporelles (F-103, F-104, G-004, G-005) | respectées telles quelles | à réinterpréter : une minute réelle vaut 48 min simulées, soit 2 à 3 décisions de la planification pendant une pointe |
| Code existant | inchangé | `simulation_der` doit appliquer le facteur à son pas |
| Lisibilité | les valeurs d'énergie sont réduites | les valeurs sont celles d'un vrai site |

**Recommandation : a.** Elle ne demande aucune modification hors du module et respecte toutes les
exigences temporelles. À confirmer avec Eaton : une « journée » comprimée en 30 min est-elle
acceptable comme profil journalier ?

### 4.3 Écarts entre la charge réelle et le profil (journal D-005)

La planification lit le profil attendu (F-100). Si la charge réelle suit exactement ce profil,
l'écrêtage peut être entièrement calculé d'avance. La comparaison de F-105 ne détecte alors que les
défauts des DER (limite de SOC, perte d'une DER). Des écarts programmés dans le scénario (ex.
+60 kW pendant 1 min) montrent que le DERMS réagit à la mesure, et pas seulement à son plan.

**Recommandation :** prévoir les écarts dans le scénario `peak_shaving`. Le coût est faible
(une liste dans le fichier) et le résultat reste déterministe (Q-115).

## 5. Configuration : `derms/configuration/scenarios_pcc/`

Un fichier par scénario de démonstration (Q-115), complet en lui-même. La variable
`EDGECS_SCENARIO_PCC` (défaut `peak_shaving`) choisit le fichier. Le scénario de perte de
communication avec une DER réutilise `peak_shaving`.

`peak_shaving.yaml`, avec l'option a de 4.2 :

```yaml
simulation:
  pas_s: 1
  mesure_perimee_s: 60

profil:
  periode_min: 30
  points_kw:          # [minute, kW] ; interpolation linéaire ; le profil se répète
    - [0, 150]
    - [6, 150]
    - [8, 300]
    - [12, 300]
    - [13, 450]
    - [17, 450]
    - [18, 300]
    - [24, 300]
    - [26, 150]

ecarts:               # minutes depuis le début du scénario, une seule fois
  - {debut_min: 15, fin_min: 16, delta_kw: 60}

pannes_reseau: []
```

`contingence_reseau.yaml` reprend le même profil, sans écarts, avec par exemple
`pannes_reseau: [{debut_min: 14, fin_min: 18}]`.

**Validation stricte.** Une `ValueError` nommant le fichier et le champ arrête le module au
démarrage si :
- un champ est manquant, inconnu ou de mauvais type ;
- `pas_s`, `mesure_perimee_s` ou `periode_min` n'est pas strictement positif ;
- les points ne commencent pas à 0, ne sont pas strictement croissants, ou dépassent `periode_min` ;
- une puissance n'est pas finie ou est négative ;
- un intervalle (écart ou panne) a `debut_min ≥ fin_min`, ou chevauche un autre intervalle de
  la même liste ;
- un écart rendrait P_charge négative.

Aucune valeur par défaut implicite (comme pour `der.yaml`).

## 6. Profil : calcul de P_charge(t)

`p_charge_kw(t_s)` est une fonction pure du temps de scénario :
1. `t_cycle = t_s mod (periode_min · 60)`.
2. Interpolation linéaire entre les points qui encadrent `t_cycle`. Entre le dernier point et
   `periode_min`, on interpole vers le premier point pour que la courbe reste continue d'un cycle à
   l'autre.
3. On ajoute `delta_kw` si `t_s` est dans un écart.

`p_attendu_kw(t_s)` donne la même valeur sans l'étape 3. C'est le profil P_profil(t) que la
planification utilise pour F-100.

Le profil se répète pour que le système tourne sans fin (G-006). Les écarts et les pannes, eux,
n'ont lieu qu'une fois : chaque scénario donne le même résultat d'une exécution à l'autre (Q-115).

## 7. Structure

```
derms/
├── configuration/
│   └── scenarios_pcc/
│       ├── peak_shaving.yaml
│       └── contingence_reseau.yaml
└── simulation_pcc/
    ├── scenario_pcc.py              ScenarioPcc.from_mapping() : lecture et validation
    ├── profil_charge.py             p_charge_kw(t), p_attendu_kw(t), reseau_disponible(t)
    ├── bilan_pcc.py                 MesureDer, MesurePcc, calcul du bilan (option A)
    └── module_simulation_pcc.py     cycle de vie, horloge du scénario, mesure()
tests/derms/simulation_pcc/          tests pytest
```

- `profil_charge.py` et `bilan_pcc.py` ne lisent ni l'horloge ni le réseau : tout se teste sans
  attendre.
- **Option A.** `SimulationPccModule(lire_mesures_der)` reçoit une fonction qui retourne
  `Mapping[str, MesureDer]`, avec `MesureDer(p_kw, horodatage)`. Le serveur lui passe celle de
  `dnp3_master` ; les tests lui passent un dictionnaire. Le module ne connaît pas le client DNP3.
- Le contrat des modules n'est pas encore décidé (PH-143, `docs/serveur_derms.md` section 5). Cette
  injection fonctionne quel que soit le choix.

## 8. Module : `module_simulation_pcc.py`

`SimulationPccModule` garde la forme actuelle (`name`, `async start()`, `async stop()`).

- `start()` lit et valide le scénario, note `t0` sur l'horloge monotone, puis lance une tâche
  périodique de période `pas_s`, à échéances absolues (`t0 + k·pas`).
- À chaque pas, la tâche :
  1. calcule `p_charge_kw` et `reseau_disponible` ;
  2. avec l'option A, lit les mesures des DER, marque périmées celles dont l'horodatage date de plus de
     `mesure_perimee_s`, et calcule P_PCC avec la dernière valeur connue de chaque DER ;
  3. remplace l'instantané `MesurePcc` ;
  4. journalise les transitions (panne, écart, DER périmée).
- `mesure()` retourne le dernier instantané, sans calcul.
- Une exception pendant un pas est journalisée avec sa trace. Le pas suivant est quand même tenté :
  le module ne doit pas priver la planification de mesure (PF-113).
- `stop()` annule la tâche et l'attend.

**Pendant une panne réseau.** Le module se contente de signaler la panne par
`reseau_disponible = False`. Ce que deviennent P_PCC et la charge non servie dépend des plans de
contingence (F-102). On le définira avec la planification ; ce point est à valider (journal D-006).

## 9. Dimensionnement du profil (PF-109)

Le profil n'est utile que si trois DER peuvent réduire sa pointe d'au moins 30 %. Avec un seuil
`S = 0,7 · max(P_charge)` :

1. **Puissance :** `max(P_charge) − S ≤ Σ p_decharge_max`.
2. **Énergie :** l'énergie au-dessus de `S` sur une pointe doit être au plus
   `Σ (soc_initial − soc_min) · capacité`. Les creux doivent ensuite laisser le temps de recharger
   avant la pointe suivante.

Exemple de la section 5, avec 3 BESS de 100 kW : la pointe vaut 510 kW avec l'écart, donc
`S` ≈ 357 kW et l'excédent maximal 153 kW ≤ 300 kW. L'énergie au-dessus de `S` est d'environ
8 kWh sur le premier cycle. Pour que le SOC varie nettement en 30 min, les capacités de `der.yaml` doivent être
de l'ordre de 10 à 20 kWh par BESS. Ce réglage est à faire avec la configuration des trois DER.

## 10. Exigences en lien

| Exigence | Ce que le module fait | Ce qui reste ailleurs |
|---|---|---|
| F-100 | le profil attendu est dans le scénario, lisible par `p_attendu_kw()` | la planification le définit comme objectif |
| F-105, F-106 | les écarts programmés créent un besoin de correction | comparaison et commandes : planification |
| F-107 | fournit P_PCC (A) ou P_charge (B) | — |
| F-108, PF-112 | injecte la panne réseau, signale `reseau_disponible` | plans de contingence : planification |
| PF-109 | fournit P_charge (sans gestion) et P_PCC (avec) sur la même exécution | historique et calcul de la réduction : stockage, essais |
| PF-110, PF-111 | signale les DER dont la mesure est périmée (A) | redistribution : planification |
| F-137 | fournit les deux puissances | affichage : interface |
| Q-115 | scénarios déterministes, versionnés, choisis par une variable | résultats documentés : essais |
| G-003 | tout paramètre vient du fichier de scénario | — |
| G-013 | instantanés et journal horodatés en UTC | horloge de référence commune : déploiement |

## 11. Étapes de réalisation

0. **Faire valider** les décisions D-003 à D-006 par l'équipe, et D-004 par Eaton. Mettre à jour
   ce plan et le journal.
1. Écrire `scenario_pcc.py` et ses tests.
2. Écrire `profil_charge.py` et ses tests.
3. Écrire `bilan_pcc.py` et ses tests (option A).
4. Écrire `module_simulation_pcc.py` et ses tests.
5. Écrire les deux scénarios et vérifier le dimensionnement de la section 9 avec `der.yaml`.
6. Brancher `lire_mesures_der` sur `dnp3_master` quand celui-ci exposera les télémesures (option A).
7. **Documentation.** Docstrings Doxygen `"""!` sur tout élément public ; mettre à jour
   `derms/simulation_pcc/README.md`, ce plan et le journal.

## 12. Tests

Sans temps réel : le module reçoit le temps de scénario, ou les tests appellent directement les
fonctions pures.

| Sujet | Cas |
|---|---|
| Profil | valeur exacte sur chaque point ; interpolation entre deux points ; continuité au passage d'un cycle au suivant ; `t` sur plusieurs cycles |
| Écarts, pannes | actifs sur `[debut, fin[` seulement ; une seule fois, pas à chaque cycle ; `p_attendu_kw` ignore les écarts |
| Configuration | chaque cas de la liste de validation de la section 5 donne une `ValueError` qui nomme le champ |
| Bilan (A) | `P_PCC = P_charge − Σ P_DER` ; exportation négative ; DER périmée signalée mais comptée avec sa dernière valeur ; DER retirée de l'inventaire absente du bilan |
| Reproductibilité | deux exécutions donnent la même suite de `MesurePcc`, à l'horodatage près |
| Module | une exception injectée pendant un pas est journalisée, et le pas suivant produit une mesure ; `stop()` se termine proprement |

## 13. Vérification

1. `pytest` : tout passe.
2. `ruff format --check --diff .` et `ruff check .` : propres.
3. `doxygen Doxyfile` : `doxygen/avertissements.txt` est vide.
4. `python -m derms.main` : `simulation_pcc` est à l'état `demarre` sur `/api/sante`, et le journal
   indique le scénario chargé. Un scénario volontairement invalide met le module `en_echec` avec un
   message qui nomme le champ.
