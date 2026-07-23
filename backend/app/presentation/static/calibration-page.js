// Gestisce la conferma protetta della calibrazione posturale.
const patient = document.body.dataset.patient;
const acknowledgement = document.getElementById("ack");
const confirmButton = document.getElementById("confirm");
const result = document.getElementById("result");

acknowledgement.addEventListener("change", () => {
  confirmButton.disabled = !acknowledgement.checked;
  confirmButton.style.background = acknowledgement.checked ? "#3274d9" : "#b8c0cc";
  confirmButton.style.cursor = acknowledgement.checked ? "pointer" : "not-allowed";
});

confirmButton.addEventListener("click", async () => {
  if (!acknowledgement.checked) return;
  confirmButton.disabled = true;
  result.textContent = "";
  const response = await fetch(
    `/api/v1/grafana/patients/${encodeURIComponent(patient)}/calibration`,
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({confirmed: true}),
    },
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    result.style.color = "#b42318";
    result.textContent = body.detail || "Calibrazione non riuscita";
    confirmButton.disabled = false;
    return;
  }
  setTimeout(() => {
    window.location.href = `/grafana/d/smartback-overview/smartback-monitoraggio-paziente?var-patient_id=${encodeURIComponent(patient)}&refresh=1s`;
  }, 900);
});
