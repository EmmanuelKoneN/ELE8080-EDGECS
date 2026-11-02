# Interface UI — application Web opérateur

Le serveur (`derms/serveur.py`) ne fournit que des données JSON, sous `/api/`. L'interface est faite
de fichiers fixes dans `static/`, servis sur `http://127.0.0.1:8000/` :

| Fichier | Rôle |
|---|---|
| `static/index.html` | Structure de la page |
| `static/app.js` | Lit l'API toutes les 2 s et met la page à jour |
| `static/style.css` | Présentation |

Aucune compilation ni ressource externe : la page fonctionne sans Internet (G-002). Une
bibliothèque (par exemple pour les courbes) se copie dans `static/` plutôt que de venir d'un CDN.
