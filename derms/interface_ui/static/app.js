// Interface opérateur du DERMS : lit l'API JSON du serveur et met la page à jour.
// Le serveur décide du statut ; ce fichier ne fait que l'afficher.

"use strict";

const HEALTH_API_PATH = "/api/sante";

// Intervalle entre deux lectures de l'API. Les délais du cahier des charges se comptent
// en dizaines de secondes (G-004, G-005) : quelques secondes suffisent.
const REFRESH_PERIOD_MS = 2000;

// Libellés des valeurs de ModuleState (derms/live_data.py).
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

// ---------- Essai de l'état central : DER 1 en direct ----------
// La page s'abonne au flux d'événements (SSE) du serveur : il envoie la DER à chaque changement,
// sans que la page ait à la redemander. EventSource se reconnecte seul si le serveur redémarre.

const DER_STREAM_PATH = "/api/der/1/flux";

function renderDer(der) {
  document.getElementById("der-nom").textContent = `${der.name} - en direct`;
  document.getElementById("der-soc").textContent =
    der.soc === null ? "Pas encore de mesure" : `${der.soc.value} %`;
  document.getElementById("der-puissance").textContent =
    der.desired_output_kw === null ? "Non décidée" : `${der.desired_output_kw} kW`;
  document.getElementById("der-recu").textContent =
    der.soc === null ? "—" : new Date(der.soc.received_at).toLocaleTimeString("fr-CA");
  const status = document.getElementById("der-flux");
  status.textContent = "Abonné : mise à jour à chaque changement";
  status.className = "ok";
}

function renderDerStreamLost() {
  const status = document.getElementById("der-flux");
  status.textContent = "Flux interrompu : reconnexion en cours…";
  status.className = "injoignable";
}

const derStream = new EventSource(DER_STREAM_PATH);
derStream.onmessage = (event) => renderDer(JSON.parse(event.data));
derStream.onerror = renderDerStreamLost;
