# Serveur DERMS — centre de gestion sur site (section 8.1)

Centre de gestion sur site. Il connaît l'inventaire des DER, calcule les consignes
et les envoie aux passerelles en DNP3, puis suit les mesures en retour.

| Module | Rôle |
|---|---|
| `interface_ui/` | Application Web pour l'opérateur : état des DER, objectifs, horaires |
| `initialisation/` | Démarrage du système et inventaire des DER |
| `configuration/` | IP, ports, points DNP3, limites de fonctionnement |
| `planification/` | Profil de puissance, répartition entre les DER, écrêtage des pointes, contingences |
| `stockage/` | Stockage local : inventaire, horaires, journal |
| `dnp3_master/` | Client DNP3 (station maîtresse) : envoie les consignes, lit les mesures |
| `simulation_pcc/` | Réseau simulé : fournit la puissance au point de couplage commun (PCC) |

**Lancer :** depuis la racine du dépôt, `python -m derms.main`