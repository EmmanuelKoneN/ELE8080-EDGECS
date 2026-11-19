# Simulation des DER : journal des décisions

Chaque décision touchant la simulation des DER est consignée ici, la plus récente en bas. Une
décision remplacée n'est pas effacée : son statut passe à « Remplacée par D-xxx ». Le plan
correspondant est [plan.md](plan.md).

Gabarit d'une entrée :

```
## D-xxx — Titre court
- Date : AAAA-MM-JJ
- Statut : Adoptée | À valider | Remplacée par D-xxx
- Exigences : F-xxx, G-xxx
- Décision : ce qui est retenu.
- Raison : pourquoi.
- Écartées : options considérées et motif du rejet.
```

---

## D-001 — MVP limité à une DER, un BESS
- Date : 2026-11-03
- Statut : Remplacée par D-012
- Exigences : G-001, F-404
- Décision : le MVP simule une seule DER, un BESS. La structure doit toutefois accepter plusieurs
  DER et d'autres types sans modification du code existant (voir D-008).
- Raison : le BESS couvre le comportement le plus riche de la section 8.4 de la Rév. 00 (charge,
  décharge, SOC) et y est la priorité du mandat.
- Écartées : trois DER dès le MVP (2 BESS + génératrice, exemple de la figure 8.1 de la Rév. 00),
  reporté. La composition finale n'était pas encore décidée.

## D-002 — Modèle BESS fourni par EPRI OpenDER, utilisé comme dépendance
- Date : 2026-11-03
- Statut : Adoptée
- Exigences : F-403, F-404
- Décision : on utilise `DER_BESS` du paquet `opender`, épinglé à `2.2.0`, enveloppé dans notre
  classe `BessModel`.
- Raison : modèle ouvert (BSD), maintenu par EPRI et conforme à IEEE 1547-2018. La version est
  épinglée parce que le paquet est en bêta.
- Écartées : réécrire un modèle inspiré d'OpenDER, rejeté pour ne pas maintenir un modèle
  maison. La compatibilité avec Python 3.11 / Linux reste à confirmer (étape 0 du plan).

## D-003 — Interface Python entre la passerelle et les DER, transport non choisi
- Date : 2026-11-03
- Statut : Adoptée
- Exigences : PH-400
- Décision : les DER exposent le contrat `DerModel`. L'application réceptrice l'appelle
  directement, dans le même processus.
- Raison : le cahier des charges n'impose pas de protocole passerelle ↔ DER, et l'équipe ne l'a pas
  encore choisi. Le contrat permettra de brancher plus tard un transport réel sans changer
  l'application réceptrice.
- Écartées : un service de simulation séparé (conteneur dédié, Modbus TCP ou HTTP), reporté
  jusqu'au choix du transport.

## D-004 — Consigne hors limites refusée, jamais tronquée
- Date : 2026-11-03
- Statut : Adoptée
- Exigences : F-403, G-011, S-405
- Décision : une consigne non finie, hors limites de puissance, ou reçue quand la DER est arrêtée
  est refusée avec une raison (`CommandResult`). L'état n'est pas modifié.
- Raison : le DERMS doit savoir que sa commande n'a pas été appliquée. Une troncature silencieuse
  masquerait une erreur de planification.
- Écartées : borner la consigne à la limite, rejeté parce que l'opérateur ne verrait pas l'écart.

## D-005 — Garde de SOC stricte dans l'enveloppe
- Date : 2026-11-03
- Statut : Adoptée
- Exigences : G-011, F-404
- Décision : à chaque pas, la puissance appliquée est bornée à l'énergie disponible jusqu'à
  `soc_min` ou `soc_max`. Le SOC atteint la limite sans la franchir, et `Alarm.SOC_LIMIT` est
  active tant que la garde réduit la consigne. La consigne reste acceptée.
- Raison : OpenDER réduit la puissance par paliers près des limites, mais ne garantit pas que le
  SOC reste dans `[SOCmin, SOCmax]`. La spec exige cette garantie.
- Écartées : refuser la consigne quand le SOC approche de la limite, rejeté parce qu'une consigne
  valide au moment de l'envoi le resterait pour le DERMS.

## D-006 — Tension et fréquence constantes en entrée du modèle
- Date : 2026-11-03
- Statut : Remplacée par D-013
- Exigences : —
- Décision : OpenDER reçoit `v = 1,0 pu` et `f = 60 Hz`, en constantes nommées.
- Raison : le couplage avec la simulation du réseau au PCC n'est pas encore conçu. Il remplacera
  ces constantes.
- Écartées : rendre ces valeurs configurables, rejeté parce qu'aucun besoin ne le justifie avant
  le couplage.

## D-007 — Un seul pas de simulation par processus
- Date : 2026-11-03
- Statut : Adoptée
- Exigences : G-003
- Décision : le pas (`simulation.pas_s`) est commun à toutes les DER d'une passerelle.
- Raison : OpenDER stocke le pas dans un attribut de classe (`DER.t_s`), partagé par tous ses
  objets du processus. Un pas par DER serait faux sans avertissement.
- Écartées : un pas par DER, impossible avec OpenDER sans un processus par DER.

## D-008 — Table de types pour ajouter des DER sans modifier le code existant
- Date : 2026-11-03
- Statut : Adoptée
- Exigences : G-001, G-003
- Décision : `fabrique_der.py` associe chaque `type` de `der.yaml` à sa classe de configuration et
  à sa classe de modèle. La passerelle simule les identifiants listés dans `EDGECS_DER_IDS`.
  - Ajouter une DER d'un type existant demande seulement de la configuration.
  - Ajouter un type demande un nouveau fichier et une ligne dans la table.
- Raison : atteindre trois DER (G-001) par ajouts, sans retoucher le BESS ni le module.
- Écartées :
  - une classe de base avec héritage, rejetée parce qu'un `Protocol` suffit et ne couple pas les
    types entre eux ;
  - la découverte automatique de plugins, superflue pour quelques types.

## D-009 — Une erreur de modèle isole la DER fautive
- Date : 2026-11-03
- Statut : Adoptée
- Exigences : F-402, G-006
- Décision : une exception dans le `step()` d'une DER est journalisée avec sa trace. Cette DER
  passe à `STOPPED` et `Alarm.FAULT` et n'est plus avancée. Les autres DER et la passerelle
  continuent.
- Raison : l'alarme doit rester visible à l'opérateur, et une DER défaillante ne doit pas arrêter
  les autres.
- Écartées : arrêter la passerelle, rejeté parce que l'alarme ne serait plus transmise.

## D-010 — Configuration invalide : la passerelle refuse de démarrer
- Date : 2026-11-03
- Statut : Adoptée
- Exigences : G-003, G-011
- Décision : toute erreur dans `der.yaml` lève une `ValueError` qui nomme la DER et le champ, et
  arrête la passerelle au démarrage. Il n'y a aucune valeur par défaut implicite.
- Raison : une DER simulée avec des limites erronées fausserait toute la démonstration sans
  signe visible.
- Écartées : ignorer la DER fautive et démarrer les autres, rejeté parce que l'erreur passerait
  inaperçue.

## D-011 — Étape 0 : OpenDER 2.2.0 validé sous Python 3.11 / Linux
- Date : 2026-11-03
- Statut : Adoptée
- Exigences : F-403, F-404, G-011
- Décision : `opender==2.2.0` est conservé (confirme D-002). `BessModel` crée le modèle par
  `DER_BESS(**paramètres)`, puis appelle `der_file.initialize_NP_BESS_P_MAX_BY_SOC()`. Sinon, la
  courbe de puissance par SOC garde les bornes 0–1 du fichier par défaut. Correspondance :

  | `der.yaml` | `der_file` | Conversion |
  |---|---|---|
  | `p_decharge_max_kw` | `NP_P_MAX`, `NP_VA_MAX` | × 1000 (W, VA) |
  | `p_charge_max_kw` | `NP_P_MAX_CHARGE`, `NP_APPARENT_POWER_CHARGE_MAX` | × 1000 (W, VA), positif |
  | `capacite_kwh` | `NP_BESS_CAPACITY` | × 1000 (Wh) |
  | `soc_min_pct`, `soc_max_pct`, `soc_initial_pct` | `NP_BESS_SOC_MIN`, `NP_BESS_SOC_MAX`, `SOC_INIT` | ÷ 100 (pu) |
  | — | `NP_EFFICIENCY` | fixé à 1 |
  | — | `NP_Q_MAX_INJ`, `NP_Q_MAX_ABS` | 0,44 × `NP_VA_MAX`, sinon OpenDER avertit dès que la puissance diffère des 100 kW du fichier par défaut |

  Le pas se règle par `DER.t_s`. La consigne passe par `update_der_input(p_dem_kw=…)`, et la
  mesure se lit dans `p_out_kw` et `bess_soc` (`numpy.float64`, à convertir en `float`).
- Raison : résultats des essais (Ex5 de la v2.2 et une configuration 100 kW / 200 kWh / 10–90 %
  au pas de 1 s) :
  - Ex5 tourne sans modification, figure enregistrée au lieu d'affichée. Rien n'est propre à
    Windows : les chemins passent par `pathlib`, les CSV sont inclus dans la roue.
  - Unités : puissances en W (`p_out_w`, aussi `p_out_kw`), capacité en Wh, SOC en pu. P > 0 en
    décharge.
  - Rendement : `NP_EFFICIENCY` (1 par défaut) ne s'applique qu'à la charge :
    `ΔSOC = (η·P_charge − P_décharge) / capacité · t_s / 3600`. Vérifié avec η = 0,9.
  - Retard d'un pas : `run()` intègre le SOC avec le `p_out` du pas précédent avant de calculer le
    nouveau. Après le pas k, `bess_soc` reflète les puissances jusqu'au pas k − 1. À l'arrêt, P
    tombe à 0 tout de suite, et le SOC bouge encore une fois.
  - Limite de SOC interne : exacte si `p_charge_max = p_decharge_max`. Une décharge et une charge
    prolongées à 100 kW s'arrêtent à 0,10 et 0,90 pile. Elle est fausse sinon : la limite de charge
    est en pu de `NP_P_MAX_CHARGE` mais comparée à une consigne en pu de `NP_P_MAX`
    (`p_funcs_bess.py`, éq. 3.7.3-8). Avec 50 kW en charge et 100 kW en décharge, le SOC dépasse
    0,90 et P oscille entre −40 et +40 kW : la batterie injecte alors qu'on lui demande de charger.
    Confirme D-005.
  - Une consigne NaN devient −100 kW (pleine charge) sans erreur. Confirme le refus de D-004.
  - Validation laxiste : un paramètre inconnu ne donne qu'un avertissement, un `SOC_INIT` hors
    `[0, 1]` est remplacé par 0,5, un `NP_EFFICIENCY` hors `[0, 1]` par 1. Confirme D-010.
  - `run()` lit `self.__class__.t_s` et le calcul du SOC lit `DER.t_s`. Confirme D-007.
  - `soc.py` écrit `logging.warning("BESS SoC reached max")` (ou `min`) sur le journal racine, à
    chaque pas passé en limite : 23 040 messages pendant l'essai.
  - `opender` dépend de `numpy`, `pandas` et `matplotlib`. Ce dernier n'est aujourd'hui que dans
    `requirements-dev.txt`. Il entrera dans l'image de la passerelle comme dépendance d'`opender`.
- Conséquences sur le plan (sections 6, 7 et 10 mises à jour) :
  - la garde de SOC part du SOC qui résultera de la puissance du pas précédent ;
  - le module filtre les avertissements de SOC d'OpenDER pour respecter « pas de journalisation
    périodique » ; l'alarme `SOC_LIMIT` les remplace ;
  - les tests tiennent compte du retard d'un pas.
- Écartées : régler les attributs de `der_file` après la construction, rejeté parce que
  `SOC_INIT` est lu à la création du modèle et qu'il faudrait ensuite appeler `reset_soc()`.

## D-012 — Rév. 01 : configuration de référence fixée, MVP toujours limité à un BESS
- Date : 2026-11-19
- Statut : Adoptée
- Exigences : G-001, F-404
- Décision : le MVP simule une seule DER, un BESS fondé sur OpenDER (D-002). La structure de D-008
  doit mener à la configuration de référence de la Rév. 01 (section 8.4, figure 8.1) : deux BESS,
  le second par configuration seulement, et une génératrice, par un nouveau type.
- Raison : la Rév. 01 du cahier des charges (2026-11-05) fixe la composition à deux BESS et une
  génératrice ; la Rév. 00 la laissait ouverte. Le BESS avec OpenDER a reçu le feu vert de
  l'équipe. Il couvre le comportement le plus riche (charge, décharge, SOC) et compte pour deux
  des trois DER.
- Écartées : réaliser les trois DER dès le MVP, reporté. La génératrice n'a pas encore de modèle
  choisi.

## D-013 — Télémétrie électrique complète (F-402, Rév. 01)
- Date : 2026-11-19
- Statut : Adoptée
- Exigences : F-402
- Décision : `DerTelemetry` contient |V| (`v_pu`), ∠V (`v_angle_deg`), f (`f_hz`), P (`p_kw`) et
  Q (`q_kvar`), en plus du SOC et des trois états.
  - P et Q sont lues dans `p_out_kw` et `q_out_kvar` d'OpenDER.
  - |V|, ∠V et f sont les valeurs appliquées aux bornes du modèle. Ce sont des constantes nommées :
    `NOMINAL_VOLTAGE_PU` (1,0), `NOMINAL_VOLTAGE_ANGLE_DEG` (0, phase de référence) et
    `NOMINAL_FREQUENCY_HZ` (60), comme dans D-006.
  - L'angle n'est pas transmis à OpenDER. Le modèle est triphasé par défaut (`NP_PHASE = THREE`), et
    son entrée `theta` attend alors une liste de trois angles en radians. Sans `theta`, le modèle
    garde ses angles par défaut.
- Raison : la Rév. 01 étend F-402 à |V|, ∠V, f, P et Q (figure 8.3). La Rév. 00 ne demandait que
  P. Tant que le couplage au réseau du PCC n'existe pas, les grandeurs aux bornes sont celles
  qu'on impose au modèle. Le couplage remplacera ces constantes sans changer le contrat.
- Écartées :
  - omettre |V|, ∠V et f jusqu'au couplage, rejeté parce que F-402 les exige dès maintenant ;
  - lire V et f dans les attributs internes d'OpenDER, rejeté parce qu'ils ne font que refléter
    nos entrées et que leurs noms ne font pas partie de l'interface publique.
- Hors portée : le passage de ces champs aux points DNP3 (`points_dnp3.yaml`) relève du volet
  Communication.

## D-014 — Clés de configuration en anglais
- Date : 2026-11-19
- Statut : Adoptée
- Exigences : G-003
- Décision : les clés de `der.yaml` sont en anglais et portent le même nom que les champs du code.
  Les clés citées dans D-007 et D-011 sont renommées ainsi :

  | Ancienne clé | Nouvelle clé |
  |---|---|
  | `simulation.pas_s` | `simulation.step_s` |
  | `p_decharge_max_kw` | `discharge_max_kw` |
  | `p_charge_max_kw` | `charge_max_kw` |
  | `capacite_kwh` | `capacity_kwh` |

  `soc_min_pct`, `soc_max_pct` et `soc_initial_pct` ne changent pas.
- Raison : les noms de code du projet sont en anglais. Une clé identique au champ se lit
  directement dans `BessConfig`, sans table de traduction à maintenir.
- Écartées : clés en français traduites vers des champs en anglais, rejeté pour éviter cette
  table.
