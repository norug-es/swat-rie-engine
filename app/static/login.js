const toast = document.querySelector("#toast");
let qrPoll;

function showToast(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 3600);
}

async function request(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "No se pudo completar la operación.");
  return data;
}

async function redirectIfAuthenticated() {
  const response = await fetch("/auth/status");
  const status = await response.json();
  if (status.authenticated) window.location.replace("/");
}

document.querySelectorAll("[data-auth-tab]").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll("[data-auth-tab]").forEach((item) => item.classList.toggle("active", item === tab));
    ["login", "register", "recover"].forEach((name) => {
      document.querySelector(`#${name}-form`).classList.toggle("hidden", name !== tab.dataset.authTab);
    });
  });
});

document.querySelector("#login-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await request("/auth/login", {
      email: document.querySelector("#login-email").value,
      password: document.querySelector("#login-password").value,
    });
    window.location.replace("/");
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelector("#register-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await request("/auth/register", {
      email: document.querySelector("#register-email").value,
      password: document.querySelector("#register-password").value,
    });
    window.location.replace("/");
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelector("#recover-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await request("/auth/recover", { email: document.querySelector("#recover-email").value });
    document.querySelector("#recovery-result").textContent = result.reset_token
      ? `Token temporal: ${result.reset_token}`
      : "Si existe, recibirás instrucciones en tu email.";
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelector("#start-qr")?.addEventListener("click", async () => {
  try {
    const challenge = await request("/auth/qr/start", {});
    const image = document.querySelector("#qr-image");
    image.src = `/auth/qr/image?url=${encodeURIComponent(challenge.approve_url)}`;
    image.classList.remove("hidden");
    document.querySelector("#qr-status").textContent = "Escanéalo con el móvil y aprueba la sesión.";
    window.clearInterval(qrPoll);
    qrPoll = window.setInterval(async () => {
      const response = await fetch(`/auth/qr/status?challenge_id=${encodeURIComponent(challenge.challenge_id)}&secret=${encodeURIComponent(challenge.secret)}`);
      const status = await response.json();
      if (status.approved) {
        window.clearInterval(qrPoll);
        window.location.replace("/");
      }
    }, 2500);
  } catch (error) {
    showToast(error.message);
  }
});

const qrToken = new URLSearchParams(window.location.search).get("qr");
if (qrToken) {
  const separator = qrToken.indexOf(".");
  if (separator > 0) {
    request("/auth/qr/approve", {
      challenge_id: qrToken.slice(0, separator),
      secret: qrToken.slice(separator + 1),
    }).then(() => {
      document.querySelector(".auth-panel").innerHTML = '<div class="auth-confirmation"><p class="eyebrow">SWAT RIE</p><h2>Sesión aprobada</h2><p class="lede">Ya puedes volver al equipo donde escaneaste el código.</p></div>';
    }).catch(() => showToast("Inicia sesión en este móvil para aprobar el QR."));
  }
}

redirectIfAuthenticated();
