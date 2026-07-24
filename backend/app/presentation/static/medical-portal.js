// Gestisce pazienti, inventario maglie e assegnazioni nella Home medica.
import {smartbackDialog} from "./themed-dialog.js?v=3";

const esc = (value) => String(value ?? "").replace(
  /[&<>"']/g,
  (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character],
);

let state = {patients: [], devices: [], discovered_devices: [], summary: {}};
const selectedShirts = new Map();
const patientDialog = document.getElementById("patientDialog");
const deviceDialog = document.getElementById("deviceDialog");
const patientError = document.getElementById("patientError");
const claimDeviceError = document.getElementById("claimDeviceError");
const deviceError = document.getElementById("deviceError");
const detectedDeviceName = document.getElementById("detectedDeviceName");
const deviceName = document.getElementById("deviceName");

function apiError(body) {
  if (Array.isArray(body?.detail)) {
    return body.detail
      .map((item) => String(item?.msg || "Dato non valido").replace(/^Value error,\s*/, ""))
      .join(" · ");
  }
  return typeof body?.detail === "string" ? body.detail : "Operazione non riuscita";
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
  });
  if (response.status === 401) window.location.href = "/grafana-login";
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Error(apiError(body));
  }
  return response.status === 204 ? null : response.json();
}

async function load() {
  state = await request("/api/v1/grafana/home");
  render();
}

function patientCard(patient) {
  const code = encodeURIComponent(patient.patient_code);
  const free = state.devices
    .filter((device) => device.available)
    .sort((left, right) => left.display_name.localeCompare(
      right.display_name,
      "it",
      {sensitivity: "base", numeric: true},
    ));
  const assigned = Boolean(patient.assigned_device);
  const canAssign = !assigned && free.length > 0;
  const selectedDevice = selectedShirts.get(patient.id);
  if (selectedDevice && !free.some((device) => device.device_id === selectedDevice)) {
    selectedShirts.delete(patient.id);
  }
  const shirtOptions = assigned
    ? "<option>Maglia già associata</option>"
    : free.length
      ? free.map((device) => (
        `<option value="${esc(device.device_id)}" ${
          device.device_id === selectedShirts.get(patient.id) ? "selected" : ""
        }>${esc(device.display_name)}</option>`
      )).join("")
      : "<option>Nessuna maglia disponibile</option>";
  const shirtAction = assigned
    ? `<button class="danger" data-action="release-shirt" data-device="${esc(patient.assigned_device)}">Libera maglia</button>`
    : `<button ${canAssign ? "" : "disabled"} data-action="assign-shirt" data-patient-id="${esc(patient.id)}" data-patient-code="${esc(patient.patient_code)}">Assegna maglia</button>`;
  return `<article class="card">
    <h3>${esc(patient.name)}</h3>
    <div class="muted">${esc(patient.fiscal_code)}</div>
    <p><span class="badge ${patient.account_registered ? "available" : ""}">${patient.account_registered ? "Account registrato" : "Account non registrato"}</span>
    ${assigned ? `<span class="badge assigned">${esc(patient.assigned_device_name || "Maglia associata")}</span>` : '<span class="badge">Nessuna maglia</span>'}</p>
    <div class="actions">
      <a class="button day-button" href="/grafana/d/smartback-overview/smartback-monitoraggio-paziente?var-patient_id=${code}&refresh=1s">DIURNO</a>
      <a class="button day-button" href="/grafana/d/smartback-history/smartback-storico-paziente?var-patient_id=${code}">STORICO D</a>
      <a class="button night-button" href="/grafana/d/smartback-night/smartback-monitoraggio-notturno?var-patient_id=${code}&refresh=1s">NOTTURNO</a>
      <a class="button night-button" href="/grafana/d/smartback-night-history/smartback-storico-notturno?var-patient_id=${code}">STORICO N</a>
    </div>
    <div class="patient-controls">
      <select class="shirt-select" id="shirt-${esc(patient.id)}" data-patient-id="${esc(patient.id)}" aria-label="Maglia da associare a ${esc(patient.name)}" ${canAssign ? "" : "disabled"}>${shirtOptions}</select>
      <div class="actions">${shirtAction}<button class="danger" data-action="remove-patient" data-patient-code="${esc(patient.patient_code)}" data-patient-name="${esc(patient.name)}">Rimuovi paziente</button></div>
    </div>
  </article>`;
}

function deviceCard(device) {
  const release = !device.available
    ? `<button class="danger" data-action="release-shirt" data-device="${esc(device.device_id)}">Libera maglia</button>`
    : "";
  return `<article class="device">
    <h3>${esc(device.display_name)}</h3>
    <div class="muted">ID ${esc(device.inventory_id)} · ${esc(device.device_id)}</div>
    <p><span class="badge ${device.connected ? "available" : ""}">${device.connected ? "Connessa" : "Non connessa"}</span>
    <span class="badge ${device.available ? "available" : "assigned"}">${device.available ? "Disponibile" : "Assegnata"}</span></p>
    ${device.patient_name ? `<div>Assegnata a: <b>${esc(device.patient_name)}</b></div>` : ""}
    <div class="actions">${release}<button class="danger" data-action="remove-device" data-device="${esc(device.device_id)}" data-device-name="${esc(device.display_name)}">Rimuovi maglia</button></div>
  </article>`;
}

function render() {
  const summary = state.summary;
  document.getElementById("stats").innerHTML = [
    ["Pazienti", summary.patients],
    ["Maglie totali", summary.devices_total],
    ["Maglie disponibili", summary.devices_available],
    ["Maglie assegnate", summary.devices_assigned],
  ].map(([label, value]) => `<div class="stat"><span class="muted">${label}</span><b>${value}</b></div>`).join("");

  document.getElementById("patients").innerHTML = state.patients.length
    ? state.patients.map(patientCard).join("")
    : '<div class="card muted empty-state">Nessun paziente associato.</div>';
  document.getElementById("devices").innerHTML = state.devices.length
    ? state.devices.map(deviceCard).join("")
    : '<div class="device muted empty-state">Nessuna maglia registrata.</div>';
  document.querySelectorAll(".shirt-select[data-patient-id]").forEach((select) => {
    select.addEventListener("change", () => {
      selectedShirts.set(select.dataset.patientId, select.value);
    });
  });

  const detected = state.discovered_devices || [];
  const detectedDevice = document.getElementById("detectedDevice");
  detectedDevice.innerHTML = detected.length
    ? detected.map((device) => `<option value="${esc(device.device_id)}">${esc(device.device_id)}</option>`).join("")
    : '<option value="">Nessuna maglia rilevata</option>';
  document.getElementById("claimDeviceButton").disabled = !detected.length;
  detectedDevice.disabled = !detected.length;
  document.getElementById("detectedDeviceName").disabled = !detected.length;
}

async function assign(patientId, patientCode) {
  const device = document.getElementById(`shirt-${patientId}`).value;
  await request(`/api/v1/grafana/devices/${encodeURIComponent(device)}/assignment`, {
    method: "PUT",
    body: JSON.stringify({patient_code: patientCode}),
  });
  selectedShirts.delete(patientId);
  await load();
}

async function releaseShirt(device) {
  if (!await smartbackDialog.confirm(
    "Liberare questa maglia? Lo storico precedente resterà associato al paziente.",
    "Libera maglia",
  )) return;
  await request(`/api/v1/grafana/devices/${encodeURIComponent(device)}/assignment`, {method: "DELETE"});
  await load();
}

async function removePatient(code, name) {
  if (!await smartbackDialog.confirm(
    `Rimuovere ${name} dalla lista dei pazienti? La maglia verrà liberata, ma account e storico resteranno conservati.`,
    "Rimuovi paziente",
  )) return;
  await request(`/api/v1/grafana/patients/${encodeURIComponent(code)}`, {method: "DELETE"});
  await load();
}

async function removeDevice(device, name) {
  if (!await smartbackDialog.confirm(
    `Rimuovere ${name} dall'inventario? Le assegnazioni e lo storico resteranno conservati.`,
    "Rimuovi maglia",
  )) return;
  await request(`/api/v1/grafana/devices/${encodeURIComponent(device)}`, {method: "DELETE"});
  await load();
}

document.getElementById("add-patient").addEventListener("click", () => patientDialog.showModal());
document.getElementById("add-device").addEventListener("click", () => deviceDialog.showModal());
document.querySelector("main").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  try {
    if (action === "assign-shirt") {
      await assign(button.dataset.patientId, button.dataset.patientCode);
    } else if (action === "release-shirt") {
      await releaseShirt(button.dataset.device);
    } else if (action === "remove-patient") {
      await removePatient(button.dataset.patientCode, button.dataset.patientName);
    } else if (action === "remove-device") {
      await removeDevice(button.dataset.device, button.dataset.deviceName);
    }
  } catch (error) {
    await smartbackDialog.message(error.message, "Operazione non riuscita");
  }
});
document.querySelectorAll(".close-dialog").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog").close());
});

const fiscalCode = document.getElementById("fiscalCode");
fiscalCode.addEventListener("input", () => {
  fiscalCode.value = fiscalCode.value.toUpperCase().replace(/\s/g, "");
});

document.getElementById("patientForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  patientError.textContent = "";
  try {
    await request("/api/v1/grafana/patients", {
      method: "POST",
      body: JSON.stringify({fiscal_code: fiscalCode.value}),
    });
    patientDialog.close();
    event.target.reset();
    await load();
  } catch (error) {
    patientError.textContent = error.message;
  }
});

document.getElementById("claimDeviceForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  claimDeviceError.textContent = "";
  const code = detectedDevice.value;
  if (!code || !await smartbackDialog.confirm(
    `Acquisire la maglia rilevata ${code} nel proprio inventario?`,
    "Acquisisci maglia",
  )) return;
  try {
    await request(`/api/v1/grafana/devices/discovered/${encodeURIComponent(code)}/claim`, {
      method: "POST",
      body: JSON.stringify({display_name: detectedDeviceName.value}),
    });
    deviceDialog.close();
    event.target.reset();
    await load();
  } catch (error) {
    claimDeviceError.textContent = error.message;
  }
});

document.getElementById("deviceForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  deviceError.textContent = "";
  try {
    await request("/api/v1/grafana/devices", {
      method: "POST",
      body: JSON.stringify({display_name: deviceName.value}),
    });
    deviceDialog.close();
    event.target.reset();
    await load();
  } catch (error) {
    deviceError.textContent = error.message;
  }
});

load().catch((error) => {
  document.querySelector("main").innerHTML = `<p>${esc(error.message)}</p>`;
});
setInterval(() => {
  if (!document.querySelector("dialog[open]")) load().catch(() => {});
}, 5000);
