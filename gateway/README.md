# Passerelle DER — nœud EDGE (sections 8.2 et 8.3)

Fait le lien entre le DERMS et une ou plusieurs DER. Elle reçoit les commandes DNP3,
les applique aux DER et renvoie leurs mesures, états et alarmes.

| Module | Rôle |
|---|---|
| `dnp3_outstation/` | Passerelle DNP3 (station semi-asservie) : écoute les commandes du DERMS (section 8.2) |
| `app_receptrice/` | Interprète les commandes et les achemine vers la bonne DER (section 8.3) |
| `journaux/` | Journalisation des événements de la passerelle |
| `simulation_der/` | Modèles logiciels des DER : BESS, génératrice, etc. (section 8.4) |

**Lancer :** depuis la racine du dépôt, `python -m gateway.main [port]`
(port 20000 par défaut ; 20001 et 20002 pour les autres passerelles)