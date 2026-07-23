const eye = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg>';
const eyeOff = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 3 18 18"/><path d="M10.6 6.1A10.8 10.8 0 0 1 12 6c6 0 9.5 6 9.5 6a16 16 0 0 1-2.1 2.8M6.2 6.2C3.8 8 2.5 12 2.5 12s3.5 6 9.5 6c1.7 0 3.2-.5 4.5-1.2"/></svg>';

document.querySelectorAll(".password-toggle").forEach((button) => {
  const input = document.getElementById(button.dataset.password);
  const fieldLabel = button.dataset.label || "password";
  button.innerHTML = eye;
  button.addEventListener("click", () => {
    const reveal = input.type === "password";
    input.type = reveal ? "text" : "password";
    button.innerHTML = reveal ? eyeOff : eye;
    button.setAttribute("aria-label", `${reveal ? "Nascondi" : "Mostra"} ${fieldLabel}`);
    button.setAttribute("title", `${reveal ? "Nascondi" : "Mostra"} ${fieldLabel}`);
  });
});

const loginForm = document.getElementById("login");
const registerForm = document.getElementById("register");

function show(mode) {
  const login = mode === "login";
  loginForm.classList.toggle("hidden", !login);
  registerForm.classList.toggle("hidden", login);
  document.getElementById("login-tab").classList.toggle("active", login);
  document.getElementById("register-tab").classList.toggle("active", !login);
  document.getElementById("login-tab").setAttribute("aria-selected", String(login));
  document.getElementById("register-tab").setAttribute("aria-selected", String(!login));
}

function detail(body, fallback) {
  return Array.isArray(body.detail)
    ? body.detail.map((item) => item.msg).join(" · ")
    : (body.detail || fallback);
}

document.getElementById("login-tab").addEventListener("click", () => show("login"));
document.getElementById("register-tab").addEventListener("click", () => show("register"));

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.getElementById("login-error");
  error.textContent = "";
  const response = await fetch("/api/v1/grafana/login", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      email: document.getElementById("email").value,
      password: document.getElementById("password").value,
    }),
  });
  const body = await response.json().catch(() => ({}));
  if (response.ok) {
    window.location.assign(body.redirect || "/smartback/");
    return;
  }
  error.textContent = detail(body, "Accesso non riuscito");
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.getElementById("register-error");
  error.textContent = "";
  const response = await fetch("/api/v1/grafana/register", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      first_name: document.getElementById("first-name").value,
      last_name: document.getElementById("last-name").value,
      email: document.getElementById("register-email").value,
      password: document.getElementById("register-password").value,
      role: "doctor",
      medical_code: document.getElementById("medical-code").value,
    }),
  });
  const body = await response.json().catch(() => ({}));
  if (response.ok) {
    window.location.assign(body.redirect || "/smartback/");
    return;
  }
  error.textContent = detail(body, "Registrazione non riuscita");
});
