// Interface opérateur du DERMS : lit l'API JSON du serveur et met la page à jour.
// Le serveur décide du statut ; ce fichier ne fait que l'afficher.

"use strict";

const HEALTH_API_PATH = "/api/sante";

// Intervalle entre deux lectures de l'API. Les délais du cahier des charges se comptent
// en dizaines de secondes (G-004, G-005) : quelques secondes suffisent.
const REFRESH_PERIOD_MS = 2000;

// Libellés des valeurs de ModuleState (derms/etat_module.py).
const STATE_LABELS = {
  non_demarre: "… Non démarré",
  demarre: "✓ Démarré",
  en_echec: "✗ En échec",
  arrete: "■ Arrêté",
};

// Libellés du statut global calculé par le serveur.
const STATUS_LABELS = {
  ok: "Tous les modules sont démarrés",
  degrade: "Fonctionnement dégradé : au moins un module n'est pas démarré",
};

function renderSummary(status) {
  const summary = document.getElementById("resume");
  summary.textContent = STATUS_LABELS[status] ?? status;
  summary.className = status;
}

function renderModules(modules) {
  // textContent plutôt qu'innerHTML : un nom de module ne peut pas injecter de HTML.
  const rows = Object.entries(modules).map(([name, state]) => {
    const row = document.createElement("tr");
    const nameCell = row.insertCell();
    const stateCell = row.insertCell();
    nameCell.textContent = name;
    stateCell.textContent = STATE_LABELS[state] ?? state;
    stateCell.className = state;
    return row;
  });
  document.getElementById("modules").replaceChildren(...rows);
}

function renderUnreachable() {
  const summary = document.getElementById("resume");
  summary.textContent = "Serveur injoignable : dernières données affichées";
  summary.className = "injoignable";
}

async function refresh() {
  try {
    const response = await fetch(HEALTH_API_PATH, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const health = await response.json();
    renderSummary(health.statut);
    renderModules(health.modules);
    document.getElementById("mise-a-jour").textContent =
      `Mis à jour à ${new Date().toLocaleTimeString("fr-CA")}`;
  } catch {
    renderUnreachable();
  }
}

refresh();
setInterval(refresh, REFRESH_PERIOD_MS);
