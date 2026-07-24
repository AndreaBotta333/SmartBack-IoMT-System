// Sincronizza stato e comandi della modalità notte con il backend.
import {smartbackDialog} from "./themed-dialog.js?v=3";

const body = document.body;
const form = document.getElementById("night-form");
const patient = body.dataset.patient;
let knownActive = body.dataset.active === "true";

if (knownActive && body.dataset.sessionId && body.dataset.sessionStartMs && window.parent !== window) {
  const dashboardUrl = new URL(window.parent.location.href);
  if (dashboardUrl.searchParams.get("night-session") !== body.dataset.sessionId) {
    dashboardUrl.searchParams.set("from", body.dataset.sessionStartMs);
    dashboardUrl.searchParams.set("to", "now");
    dashboardUrl.searchParams.set("night-session", body.dataset.sessionId);
    window.parent.location.replace(dashboardUrl.toString());
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!await smartbackDialog.confirm(
    body.dataset.confirmation,
    knownActive ? "Termina monitoraggio notturno" : "Attiva monitoraggio notturno",
  )) return;
  try {
    await fetch(form.action, {method: "POST", cache: "no-store"});
  } finally {
    window.location.reload();
  }
});

async function synchronizeNightState() {
  try {
    const response = await fetch(
      `/api/v1/grafana/patients/${encodeURIComponent(patient)}/night-monitoring/status`,
      {cache: "no-store"},
    );
    if (!response.ok) return;
    const state = await response.json();
    if (Boolean(state.active) !== knownActive) window.location.reload();
  } catch (_) {
    // Il successivo polling riproverà senza interrompere il pannello.
  }
}

setInterval(synchronizeNightState, 1000);
