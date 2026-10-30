# Standard de programmation EDGECS

Ce standard reprend les pratiques du cours ELE4205 (Git, Doxygen, clang-format et
standard de programmation C++17) et les adapte à Python, le langage principal du projet.

Chaque règle est **Obligatoire** (à respecter en tout temps) ou **Recommandée**
(peut être contournée si on l'explique dans la pull request). Entre parenthèses, l'objectif
visé : **L**isibilité, **M**aintenabilité, **R**obustesse.

Les règles marquées ✅ sont vérifiées automatiquement par Ruff (`ruff check .`).
Les autres sont vérifiées lors de la revue de code.

---

## 1. Outils

| Rôle | C++ (cours) | Python (EDGECS) |
|---|---|---|
| Formatage automatique | clang-format | `ruff format` (et clang-format pour le C++ éventuel) |
| Vérification du standard | revue de code | `ruff check` + revue de code |
| Documentation externe | Doxygen, `///` dans les `.h` | Doxygen, docstrings `"""!` |
| Configuration | `.clang-format`, `Doxyfile` | `pyproject.toml`, `.clang-format`, `Doxyfile` |

Le formatage se fait **automatiquement à l'enregistrement** dans VS Code.
Personne ne discute du style : l'outil décide.

---

## 2. Règles de programmation

### Règle 1 — Nommage — Obligatoire (L, M) ✅

| Élément | Convention | Exemple |
|---|---|---|
| Variables, fonctions, méthodes | `snake_case` | `read_measurement()`, `active_power_kw` |
| Classes et types | `UpperCamelCase` | `DnpMaster`, `PowerSchedule` |
| Constantes | `UPPER_CASE` | `DEFAULT_PORT` |
| Membres internes d'une classe | `_snake_case` | `self._message_count` |
| Modules et dossiers | `snake_case` | `dnp3_master/`, `simulation_pcc/` |

**Différence avec le cours :** le cours impose `lowerCamelCase` pour le C++. En Python, la
convention universelle (PEP 8) est `snake_case`. On la suit pour que notre code ressemble
à celui de toutes les bibliothèques Python que nous utilisons. Le `_` devant les membres
internes est conservé.

### Règle 2 — Tout le code dans des modules — Obligatoire (L, R)

L'équivalent Python des `namespace` : tout le code est dans un module d'un dossier
(`derms/…`, `gateway/…`). Aucun code ne s'exécute à l'importation d'un module, sauf la
définition de constantes, de fonctions et de classes. Le code de démarrage va dans
`main()`, appelé seulement par :

```python
if __name__ == "__main__":
    main()
```

### Règle 3 — Interdiction de `import *` — Obligatoire (L, R) ✅

L'équivalent de l'interdiction de `using namespace std;`. L'origine de chaque nom doit
être visible.

| À faire | À ne pas faire |
|---|---|
| `from derms.planification import schedule_peak_shaving` | `from derms.planification import *` |

### Règle 4 — Annotations de type et immuabilité — Obligatoire (L, M, R) ✅

L'équivalent du mot-clef `const`. Toute fonction a des annotations de type sur ses
paramètres et sa valeur de retour. Les constantes sont marquées `Final`, et une fonction
ne modifie pas les objets reçus en paramètre, sauf si c'est son rôle documenté
(`@param[out]`).

| À faire | À ne pas faire |
|---|---|
| `def print_value(value: str) -> None:` | `def print_value(value):` |
| `DEFAULT_PORT: Final[int] = 20000` | `DEFAULT_PORT = 20000` |

### Règle 5 — Pas d'arguments par défaut mutables — Obligatoire (R) ✅

En Python, une liste ou un dictionnaire comme valeur par défaut est partagé entre tous
les appels, ce qui crée des bogues difficiles à trouver.

| À faire | À ne pas faire |
|---|---|
| `def add_der(der_list: list[str] \| None = None) -> None:` | `def add_der(der_list: list[str] = []) -> None:` |

### Règle 6 — Pas de valeurs magiques — Obligatoire (L, M, R) ✅

L'équivalent de `constexpr` plutôt que `#define`. Les nombres et chaînes qui ont un sens
deviennent des constantes nommées ou des `Enum`.

| À faire | À ne pas faire |
|---|---|
| `if soc_pct < MIN_SOC_PCT:` | `if soc_pct < 20:` |
| `class DerState(Enum): ONLINE = 1` | `state = 1  # 1 = en ligne` |

### Règle 7 — Boucles modernes — Recommandée (L, M, R)

On parcourt directement les éléments (`for der in ders`), avec `enumerate()` ou `zip()`
si besoin, plutôt qu'avec un indice.

| À faire | À ne pas faire |
|---|---|
| `for der in ders:` | `for i in range(len(ders)):` |
| `for index, der in enumerate(ders):` | `der = ders[i]` |

### Règle 8 — Ressources gérées par `with` — Recommandée (M, R) ✅

L'équivalent des pointeurs intelligents plutôt que `new`/`delete`. Fichiers, sockets et
connexions sont ouverts avec `with`, ce qui garantit leur fermeture même en cas d'erreur.

| À faire | À ne pas faire |
|---|---|
| `with open(path) as file:` | `file = open(path)` … `file.close()` |

### Règle 9 — Annotations utiles, pas redondantes — Recommandée (L, M)

L'équivalent de `auto`. Les variables locales n'ont pas besoin d'annotation quand le type
est évident. On annote quand le type aide à comprendre.

| À faire | À ne pas faire |
|---|---|
| `ders = load_inventory()` | `ders: list[Der] = list[Der](load_inventory())` |

### Règle 10 — `None` plutôt que des codes magiques — Recommandée (L, R)

L'équivalent de `std::optional<T>`. Une fonction qui peut ne pas produire de valeur
retourne `T | None`, et l'appelant vérifie le résultat.

| À faire | À ne pas faire |
|---|---|
| `def read_temperature() -> float \| None:` | `def read_temperature() -> float:  # -1 si erreur` |

```python
temperature = read_temperature()
if temperature is not None:
    print(temperature)
```

---

## 3. Du bon code

Ces principes du cours ne sont pas obligatoires, mais ils guident les revues de code.

- **Code autodocumenté** : des noms explicites et de petites fonctions qui ont un seul rôle.
  Les commentaires expliquent le *pourquoi*, pas le *comment*.
- **Never nesting** : pas plus de deux niveaux d'indentation dans une fonction. On utilise
  des retours anticipés et on extrait des fonctions. Ruff signale les fonctions trop
  complexes ✅.
- **Organisation d'une fonction** : 1) préconditions et validations, 2) traitement
  principal, 3) valeur de retour.
- **SOLID — S** : une classe ou une fonction n'a qu'une seule responsabilité.
- **SOLID — I** : une classe n'implémente pas de méthodes dont elle n'a pas besoin.
- **Fichiers et dossiers** : on regroupe par fonctionnalité et on découpe les fichiers trop
  gros. L'arborescence fait partie de la documentation.

---

## 4. Documentation (Doxygen)

### Où documenter

- **Tous les éléments publics** : modules, classes, fonctions et constantes utilisées par
  d'autres modules. C'est la documentation externe, générée par Doxygen.
- Les éléments internes (nom qui commence par `_`) sont documentés par des commentaires
  normaux, seulement si c'est utile.

### Format

En Python, la documentation Doxygen s'écrit dans une docstring qui commence par `"""!`.
Pour une constante, on utilise `##` sur la ligne au-dessus.

**Attention :** sans `@file` en haut du fichier, Doxygen ne documente pas le fichier,
exactement comme en C++.

```python
"""!
@file planification.py
@brief Calcul des consignes de puissance envoyées aux DER.
@author Prénom Nom
@date 2026-10-24
@note Fait partie du module de planification du DERMS (section 8.1).
"""

from typing import Final

## Puissance maximale importée au PCC avant l'écrêtage, en kW.
PEAK_LIMIT_KW: Final[float] = 150.0


class PeakShaver:
    """!
    @brief Calcule les consignes d'écrêtage des pointes.
    @details Répartit la puissance excédentaire au PCC entre les DER disponibles,
    en respectant les limites de chacune.
    """

    def compute_setpoints(self, pcc_power_kw: float) -> dict[str, float]:
        """!
        @brief Calcule la consigne de chaque DER pour ramener la puissance sous la limite.
        @param[in] pcc_power_kw Puissance mesurée au PCC, en kW.
        @return Consigne de puissance active par identifiant de DER, en kW.
        @throw ValueError Si la puissance mesurée est négative.
        @note Les DER hors ligne sont ignorées.
        """
```

### Mots-clefs principaux

| Mot-clef | Description |
|---|---|
| `@file` | Description générale du fichier (obligatoire) |
| `@brief` | Résumé court |
| `@details` | Description plus longue |
| `@param[in]` / `@param[out]` | Argument d'entrée / modifié par la fonction |
| `@return` | Valeur de retour |
| `@throw` | Exceptions levées |
| `@note` | Remarque importante |
| `@see` | Référence vers un autre élément |

### Bonnes pratiques

- Décrire l'**intention et l'utilisation**, pas l'implémentation.
- Une documentation **stable** : si changer quelques lignes de code oblige à la modifier,
  elle décrit trop de détails.

### Générer la documentation

```bash
doxygen Doxyfile
```

Ouvrir ensuite `doxygen/html/index.html`. Les éléments publics non documentés sont listés
dans `doxygen/avertissements.txt`. Ce fichier doit être vide avant une pull request.

---

## 5. Git

### Nomenclature des branches

| Branche | Usage |
|---|---|
| `main` | Code stable. Protégée : on n'y pousse jamais directement. |
| `feature/nom` | Nouvelle fonctionnalité (ex. `feature/dnp3-master`) |
| `bugfix/nom` | Correction d'un bogue (ex. `bugfix/port-gateway`) |
| `poc/nom` | Expérimentation, preuve de concept (ex. `poc/yadnp3`) |

### Flux de travail

1. Créer une branche à partir de `main` à jour (`git checkout -b feature/nom`).
2. Développer la fonctionnalité, avec des commits clairs.
3. Fusionner `main` dans la branche et régler les conflits **localement**
   (jamais de conflit dans `main`).
4. Ouvrir une pull request.
5. Commentaires, corrections et tests.
6. Fusionner la branche dans `main` après approbation, puis la supprimer.

Une branche dont le travail dure plus d'une journée est poussée sur GitHub chaque jour.

### Ce qui ne va jamais dans le dépôt

Les dossiers générés (`doxygen/`, `build/`, `__pycache__/`), les configurations
personnelles et les fichiers propres à votre machine. Seuls les réglages d'équipe de
`.vscode/` sont partagés.
