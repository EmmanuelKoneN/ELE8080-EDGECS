"""!
@file page_sante.py
@brief Page Web qui présente l'état des modules du DERMS.
@author Équipe EDGECS
@date 2026-10-30
@note La page n'utilise aucune ressource externe : elle fonctionne sans Internet (G-002).
"""

from html import escape
from typing import Final

from derms.etat_module import ModuleState

_STATE_LABELS: Final[dict[ModuleState, str]] = {
    ModuleState.NOT_STARTED: "… Non démarré",
    ModuleState.RUNNING: "✓ Démarré",
    ModuleState.FAILED: "✗ En échec",
    ModuleState.STOPPED: "■ Arrêté",
}

_PAGE_STYLE: Final[str] = """
:root { color-scheme: light dark; --ok: #1a7f37; --alerte: #cf222e; --neutre: #6e7781; }
body { font-family: system-ui, sans-serif; max-width: 32rem; margin: 2rem auto; padding: 0 1rem; }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid var(--neutre); padding: 0.5rem; text-align: left; }
.demarre { color: var(--ok); }
.en_echec { color: var(--alerte); }
.non_demarre, .arrete { color: var(--neutre); }
"""


def render_health_page(states: dict[str, ModuleState]) -> str:
    """!
    @brief Construit la page HTML de l'état des modules.
    @param[in] states État de chaque module, par nom de module.
    @return Le document HTML complet.
    """
    running_count = sum(state is ModuleState.RUNNING for state in states.values())
    summary_state = ModuleState.RUNNING if running_count == len(states) else ModuleState.FAILED
    rows = "".join(
        f'<tr><td>{escape(name)}</td><td class="{state}">{_STATE_LABELS[state]}</td></tr>'
        for name, state in states.items()
    )
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>État du DERMS</title><style>{_PAGE_STYLE}</style></head><body>"
        "<h1>État du serveur DERMS</h1>"
        f'<p class="{summary_state}">{running_count} modules démarrés sur {len(states)}</p>'
        f"<table><tr><th>Module</th><th>État</th></tr>{rows}</table>"
        "</body></html>"
    )
