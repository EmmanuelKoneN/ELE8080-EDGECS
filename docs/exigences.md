# Exigences du projet EDGECS

Transcription du Tableau 8.1 (section 8.5) du cahier des charges, **Rév. 01 du 2026-11-05**
(`assets/ELE8080 EDGECS Cahier_des_charges_Rev01.pdf`). Le PDF fait foi ; ce fichier doit être
mis à jour à chaque nouvelle révision du tableau.

## Lecture

- **Numéro** : 0xx général (s'applique à tous les sous-systèmes), 1xx DERMS, 2xx passerelle DNP3,
  3xx nœud EDGE, 4xx DER.
- **Préfixe** : G générale, PH physique (forme, environnement, entrées et sorties), F fonctionnelle,
  PF performance (délai, fréquence, durée, précision), S sécurité (usagers, équipements, données),
  Q qualité (critères d'acceptation et preuve).
- **Validation** : O observation ou inspection, M mesure lors d'essais, A analyse de simulation,
  D démonstration de fonctionnement.
- **Spécification** : valeur cible si l'exigence est quantitative, sinon « — ».
- La colonne Notes du cahier est vide dans la Rév. 01 ; elle n'est pas reproduite.

## 0xx — Exigences générales

| Réf. | Exigence | Spécification | Valid. |
|---|---|---|---|
| G-001 | Le prototype doit faire fonctionner au moins trois DER simultanément. | N_DER ≥ 3 | D |
| G-002 | L'ensemble du prototype (DERMS, passerelle, nœud EDGE, DER simulées) doit fonctionner sur un réseau local isolé, sans accès à Internet ni service infonuagique public. | — | D |
| G-003 | Les paramètres propres à une installation (adresses IP, ports, adresses DNP3, correspondance des points, identifiants et limites des DER) doivent être lus à partir de fichiers de configuration dans tous les composants. | 0 paramètre codé en dur | O |
| G-004 | L'intervalle entre deux mises à jour de la télémesure d'une DER telle qu'affichée dans l'interface ne doit pas dépasser 30 s. | T_maj ≤ 30 s | M |
| G-005 | Le résultat du traitement d'une commande (acceptation ou refus) doit être retourné au DERMS. Le délai d'exécution de la commande peut varier selon sa nature et le type de DER. | T_reponse ≤ 30 s | M |
| G-006 | Chaque composant doit fonctionner en continu pendant la durée de démonstration, sans redémarrage, sans perte de journal et sans saturation de ses ressources. | ≥ 10 min | M |
| G-007 | Toute perte de communication entre deux composants (DERMS, passerelle, DER) doit être détectée et signalée à l'opérateur par une alarme. | T_alarme ≤ 60 s | M |
| G-009 | Une interruption de communication, un arrêt ou un redémarrage d'un composant ne doit provoquer l'exécution d'aucune commande involontaire ou en double. | 0 commande involontaire | D |
| G-010 | Après un redémarrage, chaque composant doit retrouver sa configuration et ses données (inventaire, horaires, journaux) sans nouvelle saisie. | 0 donnée perdue | D |
| G-011 | Aucune consigne hors des limites déclarées d'une DER ne doit être appliquée. Chaque commande doit être validée avant sa transmission. | P_set et SOC dans les limites déclarées | D |
| G-012 | Sur chaque composant, seuls les ports réseau utilisés par le prototype (DNP3, interface Web, administration) doivent être ouverts, et leur liste doit figurer dans la documentation. | Ports ouverts = ports documentés | O |
| G-013 | Chaque composant doit journaliser ses événements (commandes, réponses, changements d'état, alarmes, pertes de communication) avec un horodatage issu d'une même horloge de référence. | — | D |
| G-014 | Chaque composant doit pouvoir être installé sur une machine vierge à partir du dépôt de code et des notes de déploiement, et la démonstration doit pouvoir être reproduite sans l'aide de l'équipe. | — | D |
| G-015 | Le code source doit être livré dans un dépôt Git versionné, commenté et structuré pour faciliter la revue par Eaton ECS. | — | O |
| G-016 | Les points de supervision et de commande retenus doivent s'appuyer sur le modèle d'information IEEE 1547-2018. Leur correspondance avec les points DNP3, selon le profil IEEE 1815.2, doit être documentée et identique dans le DERMS et la passerelle. | 100 % des points retenus documentés et vérifiés | O |

G-008 n'existe plus dans la Rév. 01 (en Rév. 00 : rétablissement automatique de la liaison DNP3,
T_reconnexion ≤ 60 s).

## 1xx — DERMS

### Gestion et planification

| Réf. | Exigence | Spécification | Valid. |
|---|---|---|---|
| F-100 | Le module doit définir le profil de puissance active attendu pour la charge simulée. | P_profil(t) défini | D |
| F-101 | Le module doit répartir la puissance exigée entre les DER en fonction de leurs capacités et limites déclarées dans l'inventaire, sans hypothèse et règles codées explicitement pour des types spécifiques. | — | D |
| F-102 | Le module doit définir des stratégies de contingence en cas de panne du réseau principal, de perte de connexion avec une ou plusieurs DER ou lorsque la puissance disponible est insuffisante pour atteindre l'objectif de gestion énergétique. | — | D |
| F-103 | Le module doit coordonner les DER afin que la puissance réellement fournie suive la puissance attendue dans un délai maximal de 30 secondes, lorsque la consigne est réalisable. | T_suivi ≤ 30 s | M |
| F-104 | Le module doit déterminer la puissance exigée de chaque DER au moins une fois par minute et recalculer la répartition lorsqu'un objectif de puissance ou la disponibilité d'une DER est modifié. | T_repartition ≤ 60 s | M |
| F-105 | Le module doit comparer périodiquement la puissance nécessaire, issue de la planification, à la puissance actuellement fournie par les DER. Cette comparaison doit également être effectuée lors d'une modification de consigne. | — | M |
| F-106 | Le module doit compenser le déficit ou le surplus de puissance constaté en émettant des commandes aux DER. | — | D |
| F-107 | Le module doit prendre en entrée la puissance du réseau simulée. | — | D |
| F-108 | Le module doit appliquer les stratégies de contingence définies lors d'une panne du réseau principal ou de l'indisponibilité d'une ou plusieurs DER, en tenant compte de la puissance restante disponible. | — | D |
| PF-109 | Le module doit limiter la puissance active appelée au point de couplage commun (PCC) selon un seuil maximal configurable par l'opérateur, lorsque les capacités des DER disponibles permettent d'atteindre cet objectif. | P_PCC(t) ≤ P_seuil pour les scénarios réalisables | M |
| PF-110 | En cas de retrait ou de perte de communication avec une ou plusieurs DER, le module doit poursuivre son fonctionnement avec les ressources restantes selon une répartition réalisable. Si la puissance disponible est insuffisante pour respecter le seuil demandé, le module doit signaler cette limitation à l'opérateur. | — | D |
| PF-111 | Le système doit demeurer fonctionnel et réactif en cas de perte de connexion avec une ou plusieurs DER, en suivant la logique planifiée dans les délais énoncés préalablement. | Essai par injection de défaut | D |
| PF-112 | Le système doit demeurer fonctionnel et réactif en cas de perte de connexion avec le réseau principal, en suivant la logique planifiée dans les délais énoncés préalablement. | Essai par injection de défaut | D |
| PF-113 | En cas de défaillance de la partie données du serveur (stockage, client DNP3 ou logique de gestion), l'interface Web doit demeurer accessible et signaler cette erreur à l'opérateur. | Essai par injection de défaut | D |
| S-114 | La logique de contingence doit éviter de surcharger le réseau ou les DER lors d'une reprise après panne. | Essai par injection de défaut | D |
| Q-115 | Chaque scénario de démonstration (peak shaving, contingence réseau, perte de communication avec une DER) doit être reproductible et produire des résultats documentés et comparables. | — | D |
| Q-116 | En fonctionnement normal, la gestion des DER doit se faire automatiquement par l'outil, sans intervention des développeurs ni de l'opérateur ; l'opérateur doit toutefois pouvoir reprendre la main en urgence par une commande manuelle prioritaire. | — | D |

### Initialisation (inventaire des DER)

| Réf. | Exigence | Spécification | Valid. |
|---|---|---|---|
| PH-117 | Le module d'initialisation doit être entièrement logiciel et s'exécuter sur le serveur du DERMS. | — | O |
| F-118 | Le module doit enregistrer chaque DER avec son identifiant, son type, ses puissances nominales, ses limites et ses modes de fonctionnement et, pour une DER de stockage, sa capacité énergétique et ses limites de SOC. | — | D |
| F-119 | Le module doit associer chaque DER à sa passerelle et à son adresse DNP3. | — | D |
| F-120 | Le module doit refuser l'enregistrement d'une DER dont la configuration est incomplète ou incohérente et indiquer la cause du refus à l'opérateur. | 100 % des cas invalides essayés refusés | D |
| F-121 | Le DERMS doit permettre l'ajout ou la modification d'une DER pendant que le système fonctionne ; la DER doit être intégrée à l'inventaire et prise en compte par la logique de planification et de gestion sans redémarrage du système ni recompilation du code. | 0 redémarrage | D |
| F-122 | Le DERMS doit permettre le retrait d'une DER pendant que le système fonctionne ; la DER retirée doit cesser d'être considérée par la logique de planification et de gestion et ne plus recevoir aucune commande, sans redémarrage du système. | 0 commande transmise | D |
| F-123 | Au démarrage, le module doit faire passer chaque DER par la séquence configuration, connexion à la passerelle, lecture de l'état initial, avant de la déclarer disponible. | — | D |
| PF-124 | Le module doit rendre disponibles toutes les DER configurées, au moins trois, après le démarrage du serveur. | T_init ≤ 60 s | M |
| PF-125 | Si une passerelle ne répond pas au démarrage, le module doit poursuivre l'initialisation des autres DER et marquer la DER concernée comme hors ligne. | — | D |
| S-126 | Une DER ne doit être présentée comme commandable qu'après la validation de ses paramètres et la lecture de son état initial. | — | D |
| S-127 | Les limites déclarées d'une DER doivent être consultables et modifiables depuis l'interface UI, et chaque modification doit être journalisée. | — | D |
| Q-128 | Les essais doivent démontrer l'enregistrement, la modification et le retrait d'une DER, ainsi que le refus d'une configuration invalide. | — | D |
| Q-129 | Les essais doivent démontrer le démarrage du système lorsqu'une passerelle est hors ligne. | — | D |
| Q-130 | Le format des fichiers de configuration doit être documenté, avec un exemple pour chaque type de DER retenu. | — | O |

### Interface UI

| Réf. | Exigence | Spécification | Valid. |
|---|---|---|---|
| PH-131 | L'interface UI doit être une application Web accessible depuis un navigateur courant, sur un poste du réseau local, sans installation de logiciel client. | — | D |
| F-132 | L'interface utilisateur doit être organisée en plusieurs pages distinctes afin de séparer les fonctions de supervision, de commande et de gestion des DER. Elle doit permettre de consulter la liste des DER, leur état opérationnel, leur état de connexion, leurs alarmes et leurs dernières télémesures horodatées. | Interface multipage | D |
| F-133 | L'interface doit permettre d'enregistrer, de modifier et de retirer une DER par l'intermédiaire du module d'initialisation. | — | D |
| F-134 | L'interface doit permettre à l'opérateur de définir et de modifier le seuil maximal de puissance appelée au réseau, exprimé en kW, pour l'écrêtage des pointes. | — | D |
| F-135 | L'interface doit permettre de créer, de modifier et de supprimer un horaire de répartition sur une plage horaire définie. | — | D |
| F-136 | L'interface doit permettre à l'opérateur d'émettre une commande manuelle, prioritaire sur les commandes de l'algorithme, et d'afficher son acceptation ou son refus, avec la raison du refus. | — | D |
| F-137 | L'interface doit afficher la puissance appelée au réseau simulé, avec et sans l'action des DER. | — | D |
| F-138 | L'interface doit permettre de consulter et d'exporter le journal des événements. | — | D |
| S-139 | Chaque action de l'opérateur effectuée dans l'interface doit être journalisée. | — | D |
| S-140 | Une commande manuelle doit être confirmée explicitement par l'opérateur, puis validée par le module de gestion selon l'état et les limites de la DER, avant d'être transmise. | — | D |

### Serveur

| Réf. | Exigence | Spécification | Valid. |
|---|---|---|---|
| PH-141 | Le serveur doit être un hôte Linux installé sur site, doté d'une interface Ethernet. | — | O |
| PH-142 | Le serveur doit communiquer avec les passerelles en DNP3 sur TCP/IP, en tant que station maîtresse, par un réseau Ethernet local. | — | D |
| PH-143 | Le logiciel du serveur doit être découpé en modules dont les interfaces sont documentées. | — | O |
| F-144 | Le serveur doit démarrer l'ensemble des modules du DERMS par une procédure documentée. | — | D |
| F-145 | Le serveur doit intégrer le client DNP3, qui envoie les commandes aux passerelles et reçoit les télémesures et les états des DER. | — | D |
| F-146 | Le serveur doit conserver l'inventaire des DER, les horaires et le journal des événements dans un stockage local. | — | D |
| S-147 | Le journal des événements ne doit pas pouvoir être modifié depuis l'interface UI. | — | D |

## 2xx — Passerelle DNP3

| Réf. | Exigence | Spécification | Valid. |
|---|---|---|---|
| F-200 | La passerelle doit établir une communication DNP3 avec le DERMS. | Connexion établie | D |
| F-201 | La passerelle doit établir une communication avec la DER simulée ou représentative au moyen d'une interface adaptée à la DER utilisée. | Connexion établie | D |
| F-202 | La passerelle doit acheminer une commande ou une consigne émise par le DERMS jusqu'au DER. | Commande reçue | D |
| F-203 | La passerelle doit transmettre vers le DERMS les télémesures, les états, les alarmes et les informations de diagnostic nécessaires à la supervision du DER. | Données transmises | D |
| S-204 | La passerelle doit détecter et signaler les commandes invalides et les états anormaux. | Erreur signalée | D |

## 3xx — EDGE

| Réf. | Exigence | Spécification | Valid. |
|---|---|---|---|
| PH-300 | Le nœud EDGE doit être un environnement Linux capable d'exécuter Docker, sur une machine physique ou virtuelle. | — | O |
| PH-301 | Le nœud EDGE doit disposer d'une interface réseau physique ou virtuelle permettant de communiquer avec le DERMS. | — | O |
| PH-302 | L'application réceptrice doit pouvoir être déployée sur n'importe quelle plateforme Linux. L'application peut être déployée sur l'Edge AP d'Eaton si elle est rendue disponible par le client ou sur un Raspberry Pi. | 0 modification du code | D |
| F-303 | Le nœud doit permettre de construire l'image de l'application réceptrice à partir du Dockerfile fourni. | 1 commande | D |
| F-304 | Les conteneurs pourraient démarrer automatiquement à la mise sous tension ou au redémarrage du nœud. | 0 intervention manuelle | D |
| PF-305 | Après une mise sous tension ou un redémarrage, le nœud peut rendre la passerelle disponible sans intervention manuelle. | T_dispo ≤ 60 s | M |
| Q-306 | Les scripts d'essai fournis doivent s'exécuter avec succès sur le nœud. | 100 % des scripts réussis | D |

## 4xx — DER

| Réf. | Exigence | Spécification | Valid. |
|---|---|---|---|
| PH-400 | Chaque DER doit pouvoir échanger des commandes et des données avec sa passerelle. | — | D |
| F-401 | Chaque DER doit avoir un identifiant unique, un type et des limites de puissance configurées. | — | D |
| F-402 | Chaque DER doit transmettre les grandeurs électriques suivantes : la tension en module et en angle de phase, la fréquence, la puissance active et la puissance réactive. Elle doit également transmettre son état opérationnel, son état de connexion et son état d'alarme. | \|V\|, ∠V, f, P, Q | D |
| F-403 | Chaque DER, quel que soit son type, doit accepter une consigne de puissance active ainsi que les commandes de démarrage et d'arrêt applicables à son type. | P_min ≤ P_set ≤ P_max | D |
| F-404 | Toute DER de stockage, quelle que soit sa technologie, doit transmettre son état de charge (SOC). | SOC_min ≤ SOC ≤ SOC_max | D |
| S-405 | Une DER ne doit appliquer une consigne de puissance que si son état le permet (par exemple, une génératrice démarrée et prête à produire). | 0 consigne appliquée hors état permis | D |
