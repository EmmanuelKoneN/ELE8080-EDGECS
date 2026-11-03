# CLAUDE.md

DERMS sur site (Eaton ECS, ELE8080) : le DERMS (`derms/`) commande des DER simulées à travers des
passerelles (`gateway/`), en DNP3. Le projet est au stade du squelette : les modules confirment
seulement leur démarrage.

## À lire avant de coder

- `README.md` : architecture, MVP, Docker, équipe
- `CONTRIBUTING.md` : standard de programmation (règles 1 à 10), Git, CI
- `docs/serveur_derms.md` : fonctionnement du serveur, décisions prises et à prendre
- `assets/ELE8080 EDGECS Cahier des charges Rev00.pdf` : exigences (Tableau 8.1, section 8.5). En
  cas de divergence, le tableau a préséance sur le texte.

## Commandes

Tout se lance depuis la racine, dans Ubuntu (WSL), avec `source .venv/bin/activate` (Python 3.11).

```bash
ruff format .                 # formater
ruff check .                  # standard de programmation (CI)
doxygen Doxyfile              # doxygen/avertissements.txt doit rester vide (CI)
python -m derms.main          # DERMS sur http://127.0.0.1:8000/ (API : /api/sante)
python -m gateway.main 20000  # une passerelle
docker compose up --build     # tout le système
```

Aucun framework de test pour l'instant.

## Règles qui ne se voient pas d'un coup d'œil

- Docstrings Doxygen `"""!` ; `@file` obligatoire en haut de chaque fichier, et tout élément public
  documenté, sinon la CI échoue.
- Noms de code en anglais `snake_case` ; commentaires, docstrings et journaux en français.
- Constantes `Final` et nommées : pas de nombre magique (Ruff PLR2004). Annotations de type partout.
- Paramètres d'installation (adresses, ports, limites des DER) : jamais codés en dur. Ils viennent
  d'un fichier de configuration ou d'une variable `EDGECS_...` (G-003).
- Module du DERMS : `name`, `async start()` et `async stop()`. `start()` rend la main ; un calcul
  long passe par `asyncio.to_thread()`.
- `derms/` n'importe jamais `gateway/`, et l'inverse non plus : ils ne se parlent qu'en DNP3.
- `points_dnp3.yaml` est le contrat DERMS ↔ passerelle : on ne le modifie qu'avec l'accord du volet
  Communication.
- Git : branches `feature/`, `bugfix/` ou `poc/` ; jamais de poussée sur `main`. Une PR suit
  `.github/pull_request_template.md` et cite les exigences touchées (ex. F-107).

## Exigences

- Citer les codes d'exigence (G-0xx, F-1xx, PF-, S-, Q-, PH-) dans le code et les PR quand c'est utile.
- Ne jamais inventer de valeur chiffrée absente du cahier des charges. Une valeur choisie par
  l'équipe est présentée comme un exemple.
- Convention de signe : P > 0 = injection vers le réseau, P < 0 = absorption.
