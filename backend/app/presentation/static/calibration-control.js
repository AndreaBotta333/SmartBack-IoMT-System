// Gestisce acquisizione live e inserimento manuale della calibrazione.
const endpoint = `/api/v1/grafana/patients/${encodeURIComponent(document.body.dataset.patient)}`;

async function errorMessage(response) {
  const body = await response.json().catch(() => ({}));
  return body.detail || "Operazione non riuscita";
}

function parseItalianNumber(input) {
  const normalized = input.value.trim().replace(",", ".");
  if (!/^-?\d+(?:\.\d+)?$/.test(normalized)) return null;
  const value = Number(normalized);
  const min = Number(input.dataset.min);
  const max = Number(input.dataset.max);
  return Number.isFinite(value) && value >= min && value <= max ? value : null;
}

function formatItalianNumber(input) {
  const value = parseItalianNumber(input);
  if (value !== null) input.value = value.toFixed(1).replace(".", ",");
}

for (const input of document.querySelectorAll('input[inputmode="decimal"]')) {
  input.value = input.value.replace(".", ",");
  input.addEventListener("input", () => {
    const cursor = input.selectionStart;
    input.value = input.value.replace(/\./g, ",").replace(/[^0-9,-]/g, "");
    if ((input.value.match(/,/g) || []).length > 1) {
      const first = input.value.indexOf(",");
      input.value = input.value.slice(0, first + 1) + input.value.slice(first + 1).replace(/,/g, "");
    }
    if (input.value.includes("-")) {
      input.value = (input.value.startsWith("-") ? "-" : "") + input.value.replace(/-/g, "");
    }
    input.setSelectionRange(Math.min(cursor, input.value.length), Math.min(cursor, input.value.length));
  });
  input.addEventListener("blur", () => formatItalianNumber(input));
}

document.getElementById("auto").addEventListener("click", async () => {
  const snapshot = await fetch(`${endpoint}/calibration-snapshot`, {method: "POST"});
  if (!snapshot.ok) {
    alert(await errorMessage(snapshot));
    return;
  }
  if (!confirm("Usare i valori di pitch e roll appena acquisiti come nuova calibrazione?")) return;
  const response = await fetch(`${endpoint}/calibration-form`, {method: "POST"});
  if (!response.ok) alert(await errorMessage(response));
});

async function applyManual(axis) {
  const input = document.getElementById(axis);
  const value = parseItalianNumber(input);
  if (value === null) {
    alert("Inserisci un valore valido");
    return;
  }
  formatItalianNumber(input);
  const label = axis === "pitch" ? "Pitch" : "Roll";
  if (!confirm(`Impostare manualmente ${label} a ${value.toFixed(1).replace(".", ",")}°?`)) return;
  const payload = axis === "pitch" ? {pitch_deg: value} : {roll_deg: value};
  const response = await fetch(`${endpoint}/manual-calibration`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  if (!response.ok) alert(await errorMessage(response));
}

document.getElementById("apply-pitch").addEventListener("click", () => applyManual("pitch"));
document.getElementById("apply-roll").addEventListener("click", () => applyManual("roll"));
