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

function bufferFromBase64(value) {
  const normalized = String(value).replace(/\s/g, "").replace(/-/g, "+").replace(/_/g, "/").replace(/=+$/, "");
  const remainder = normalized.length % 4;
  if (remainder === 1) throw new Error("Invalid base64url value from passkey provider");
  const padded = normalized + "=".repeat((4 - remainder) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0)).buffer;
}

function base64FromBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function credentialPayload(credential) {
  return {
    id: credential.id,
    rawId: base64FromBuffer(credential.rawId),
    type: credential.type,
    response: Object.fromEntries(Object.entries(credential.response).map(([key, value]) => [
      key,
      value instanceof ArrayBuffer ? base64FromBuffer(value) : value,
    ])),
  };
}

async function loginWithPasskey() {
  if (!window.PublicKeyCredential) throw new Error("Este navegador no admite passkeys.");
  const { challenge_id: challengeId, options } = await request("/auth/passkey/login/options", {});
  options.challenge = bufferFromBase64(options.challenge);
  if (options.allowCredentials) options.allowCredentials = options.allowCredentials.map((item) => ({ ...item, id: bufferFromBase64(item.id) }));
  const credential = await navigator.credentials.get({ publicKey: options });
  await request("/auth/passkey/login/verify", { challenge_id: challengeId, credential: credentialPayload(credential) });
  await finishLogin();
}

async function finishLogin() {
  if (qrToken) {
    await approveQrFromToken();
  } else {
    window.location.replace("/");
  }
}

async function redirectIfAuthenticated() {
  const response = await fetch("/auth/status");
  const status = await response.json();
  if (!status.authenticated) return;
  if (qrToken) {
    await approveQrFromToken();
    return;
  }
  window.location.replace("/");
}

const qrToken = new URLSearchParams(window.location.search).get("qr");
const qrParts = qrToken?.split(".");

async function approveQrFromToken() {
  if (!qrParts || qrParts.length !== 2) return;
  await request("/auth/qr/approve", {
    challenge_id: qrParts[0],
    secret: qrParts[1],
  });
  document.querySelector(".auth-panel").innerHTML = '<div class="auth-confirmation"><p class="eyebrow">SWAT RIE</p><h2>Sesión aprobada</h2><p class="lede">Ya puedes volver al navegador donde escaneaste el código.</p></div>';
}

document.querySelectorAll("[data-auth-tab]").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll("[data-auth-tab]").forEach((item) => item.classList.toggle("active", item === tab));
    ["login", "register", "recover"].forEach((name) => {
      document.querySelector(`#${name}-form`).classList.toggle("hidden", name !== tab.dataset.authTab);
    });
  });
});

document.querySelector("#passkey-login")?.addEventListener("click", async () => {
  try {
    await loginWithPasskey();
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelector("#show-totp-login")?.addEventListener("click", () => {
  document.querySelector("#login-form").classList.add("hidden");
  document.querySelector("#totp-login-form").classList.remove("hidden");
});

document.querySelector("#show-passkey-login")?.addEventListener("click", () => {
  document.querySelector("#totp-login-form").classList.add("hidden");
  document.querySelector("#login-form").classList.remove("hidden");
});

document.querySelector("#totp-login-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await request("/auth/totp/login", {
      email: document.querySelector("#totp-email").value,
      code: document.querySelector("#totp-code").value,
    });
    await finishLogin();
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelector("#register-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await request("/auth/register", {
      email: document.querySelector("#register-email").value,
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

if (qrToken) {
  document.querySelector("#qr-status").textContent = "Inicia sesión en este móvil para aprobar el acceso del navegador.";
}

redirectIfAuthenticated().catch(() => showToast("No se pudo validar la sesión."));
