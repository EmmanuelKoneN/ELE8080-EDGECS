# Simulation du réseau au PCC : journal des décisions

Chaque décision touchant la simulation du réseau au PCC est consignée ici, la plus récente en bas.
Une décision remplacée n'est pas effacée : son statut passe à « Remplacée par D-xxx ». Le plan
correspondant est [plan.md](plan.md). Les numéros sont propres à ce journal ; une décision de la
simulation des DER est citée sous la forme « simulation_der D-xxx ».

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

## D-001 — La charge simulée fait partie de `simulation_pcc`
- Date : 2026-11-13
- Statut : Adoptée
- Exigences : F-107, F-137
- Décision : le modèle de la charge du site est réalisé dans `derms/simulation_pcc/`, avec le
  bilan au PCC.
- Raison : le cahier des charges ne prévoit aucun bloc « charge » distinct. Le seul bloc de
  simulation côté DERMS est « Simulation du réseau (grid simulé) », qui sort la puissance au PCC.
  La charge n'est pas une DER : elle n'est ni commandée ni reliée à une passerelle.
- Écartées : un module `simulation_charge` séparé, rejeté parce qu'il ajouterait une interface sans
  exigence qui le demande ; la charge dans `gateway/simulation_der`, rejetée parce qu'elle
  passerait par DNP3 sans être une DER.

## D-002 — Un profil cyclique par scénario, dans un fichier de configuration
- Date : 2026-11-13
- Statut : À valider (avec la planification, pour F-100)
- Exigences : F-100, G-003, G-006, Q-115
- Décision : chaque scénario de démonstration est un fichier YAML complet en lui-même : profil
  défini par points et interpolé linéairement, écarts, pannes. Le profil se répète. La
  planification lit le même profil comme puissance attendue.
- Raison : le cahier des charges demande un profil journalier défini, et pas plusieurs profils.
  Un fichier versionné est reproductible. Une seule source évite que le profil attendu et la
  charge simulée divergent par erreur.
- Écartées : plusieurs profils types (usine, commerce, résidentiel), rejetés faute d'exigence ;
  un profil aléatoire, rejeté pour Q-115 ; un fichier de profil partagé et des fichiers
  d'événements séparés, rejeté parce que l'indirection coûte plus que la copie de quelques lignes.

## D-003 — Calcul de P_PCC dans `simulation_pcc` (option A)
- Date : 2026-11-13
- Statut : À valider
- Exigences : F-107, F-105, PF-110, PF-111
- Décision proposée : `simulation_pcc` lit les P_DER mesurées dans `dnp3_master`, par une fonction
  injectée, et fournit `P_PCC = P_charge − Σ P_DER`.
- Raison : F-107 demande que la planification reçoive la puissance du réseau. Le module se
  comporte comme un compteur au PCC. Un simulateur externe ou un compteur réel pourrait le
  remplacer sans toucher à la planification.
- Écartées : option B, `simulation_pcc` ne fournit que P_charge et la planification fait le bilan.
  Elle n'est pas rejetée : elle est plus simple (aucune dépendance, un seul lecteur des
  télémesures), mais F-107 n'y est respecté que par interprétation. Comparaison dans le plan,
  section 4.1.

## D-004 — Temps réel et journée de démonstration (option a)
- Date : 2026-11-13
- Statut : À valider (avec Eaton)
- Exigences : G-006, F-103, F-104, G-004, G-005
- Décision proposée : tout le prototype fonctionne en temps réel. Le profil a la forme d'une
  journée, mais dure `periode_min` (ex. 30 min). Les capacités des BESS sont réduites en
  conséquence dans `der.yaml`.
- Raison : les DER intègrent leur SOC en temps réel. Accélérer seulement la charge fausserait le
  bilan d'énergie. Cette option respecte les exigences temporelles telles qu'écrites et ne
  modifie pas `simulation_der`.
- Écartées : option b, un facteur d'accélération commun au DERMS et aux passerelles. Ses valeurs
  sont réalistes, mais il faut modifier `simulation_der` et réinterpréter F-103 et F-104. Elle est
  à reconsidérer si Eaton refuse une journée comprimée.

## D-005 — Écarts programmés entre la charge réelle et le profil
- Date : 2026-11-13
- Statut : À valider
- Exigences : F-105, F-106, Q-115
- Décision proposée : le scénario peut décrire des écarts `{debut_min, fin_min, delta_kw}` qui
  s'ajoutent à la charge réelle, mais pas au profil attendu. Ils n'ont lieu qu'une fois.
- Raison : sans écart, l'écrêtage peut être calculé entièrement d'avance. Les écarts montrent
  que le DERMS réagit à la mesure et restent déterministes.
- Écartées : un bruit aléatoire à graine fixe, rejeté parce qu'il est moins lisible en
  démonstration et ajoute un paramètre ; aucun écart, possible si l'équipe juge que les défauts
  des DER suffisent à exercer F-105 et F-106.

## D-006 — Panne réseau signalée, sans modèle d'îlotage
- Date : 2026-11-13
- Statut : À valider (avec la planification, pour F-102)
- Exigences : F-108, PF-112
- Décision proposée : une panne programmée dans le scénario met `reseau_disponible` à `False`
  pendant son intervalle et est journalisée. La valeur de P_PCC et la charge non servie pendant la
  panne seront définies avec les plans de contingence.
- Raison : l'injection de la panne appartient au réseau simulé, mais la réaction appartient à la
  planification. Fixer maintenant le comportement électrique de l'îlot reviendrait à décider des
  plans de contingence à leur place.
- Écartées : une injection manuelle par l'interface ou l'API, rejetée parce qu'elle n'est pas
  reproductible (Q-115) et n'est demandée par aucune exigence.

## D-007 — Tension et fréquence au PCC non simulées
- Date : 2026-11-13
- Statut : Adoptée
- Exigences : —
- Décision : le module ne produit ni tension ni fréquence.
- Raison : aucune exigence du DERMS ne les utilise. Le réseau principal est raide, et les DER
  reçoivent déjà des valeurs nominales constantes (simulation_der D-006).
- Écartées : produire V et f pour les passer aux DER, rejeté parce que cela ajoute un échange par
  DNP3 sans exigence qui le justifie.
