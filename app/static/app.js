const state = {
  lastResult: null,
  qrPoll: null,
};

const els = {
  form: document.querySelector("#verify-form"),
  logoutButton: document.querySelector("#logout-button"),
  textField: document.querySelector("#text-field"),
  urlField: document.querySelector("#url-field"),
  textInput: document.querySelector("#text-input"),
  urlInput: document.querySelector("#url-input"),
  autonomousSearch: document.querySelector("#autonomous-search"),
  evidenceQuery: document.querySelector("#evidence-query"),
  evidenceList: document.querySelector("#evidence-list"),
  addEvidence: document.querySelector("#add-evidence"),
  searchPrevious: document.querySelector("#search-previous"),
  resetButton: document.querySelector("#reset-button"),
  submitButton: document.querySelector("#submit-button"),
  loadInvestigation: document.querySelector("#load-investigation"),
  loadProviders: document.querySelector("#load-providers"),
  providersList: document.querySelector("#providers-list"),
  mediaFile: document.querySelector("#media-file"),
  uploadMedia: document.querySelector("#upload-media"),
  mediaUrl: document.querySelector("#media-url"),
  downloadMedia: document.querySelector("#download-media"),
  artifactBox: document.querySelector("#artifact-box"),
  investigationId: document.querySelector("#investigation-id"),
  resultPanel: document.querySelector("#result-panel"),
  resultVerdict: document.querySelector("#result-verdict"),
  resultConfidence: document.querySelector("#result-confidence"),
  resultId: document.querySelector("#result-id"),
  resultSource: document.querySelector("#result-source"),
  copyId: document.querySelector("#copy-id"),
  claimsList: document.querySelector("#claims-list"),
  evidenceResultList: document.querySelector("#evidence-result-list"),
  dimensionsList: document.querySelector("#dimensions-list"),
  graphList: document.querySelector("#graph-list"),
  certificateBox: document.querySelector("#certificate-box"),
  loadCertificate: document.querySelector("#load-certificate"),
  explanationList: document.querySelector("#explanation-list"),
  limitationsList: document.querySelector("#limitations-list"),
  reviewAction: document.querySelector("#review-action"),
  reviewAnalyst: document.querySelector("#review-analyst"),
  reviewVerdict: document.querySelector("#review-verdict"),
  reviewNotes: document.querySelector("#review-notes"),
  submitReview: document.querySelector("#submit-review"),
  reviewsList: document.querySelector("#reviews-list"),
  healthDot: document.querySelector("#health-dot"),
  healthTitle: document.querySelector("#health-title"),
  healthDetail: document.querySelector("#health-detail"),
  toast: document.querySelector("#toast"),
};

function getMode() {
  return document.querySelector('input[name="mode"]:checked')?.value || "text";
}

function showToast(message) {
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => els.toast.classList.add("hidden"), 3600);
}

function setBusy(isBusy) {
  if (!els.submitButton) return;
  els.submitButton.disabled = isBusy;
  els.submitButton.textContent = isBusy ? "Verificando..." : "Verificar";
}

function addEvidenceRow(value = "") {
  const count = els.evidenceList.querySelectorAll("input").length;
  if (count >= 12) {
    showToast("El motor admite un maximo de 12 evidencias.");
    return;
  }

  const row = document.createElement("div");
  row.className = "evidence-row";

  const input = document.createElement("input");
  input.type = "url";
  input.placeholder = "https://fuente-oficial.example/nota";
  input.value = value;

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "icon-button";
  remove.title = "Eliminar evidencia";
  remove.setAttribute("aria-label", "Eliminar evidencia");
  remove.textContent = "x";
  remove.addEventListener("click", () => row.remove());

  row.append(input, remove);
  els.evidenceList.append(row);
}

function collectEvidenceUrls() {
  return [...els.evidenceList.querySelectorAll("input")]
    .map((input) => input.value.trim())
    .filter(Boolean);
}

function buildPayload() {
  const mode = getMode();
  const payload = {
    evidence_urls: collectEvidenceUrls(),
    autonomous_search: els.autonomousSearch.checked,
  };
  const evidenceQuery = els.evidenceQuery.value.trim();
  if (evidenceQuery) {
    payload.evidence_query = evidenceQuery;
  }

  if (mode === "text") {
    const text = els.textInput.value.trim();
    if (text.length < 3) {
      throw new Error("El texto debe tener al menos 3 caracteres.");
    }
    payload.text = text;
    return payload;
  }

  const url = els.urlInput.value.trim();
  if (!url) {
    throw new Error("Indica una URL origen.");
  }
  payload.url = url;
  return payload;
}

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  const text = await response.text();
  const data = parseApiResponse(text);

  if (!response.ok) {
    const detail = data?.detail || `${response.status} ${response.statusText}`;
    throw new Error(Array.isArray(detail) ? JSON.stringify(detail) : detail);
  }

  return data;
}

async function apiFormFetch(path, formData) {
  const response = await fetch(path, {
    method: "POST",
    body: formData,
  });
  const text = await response.text();
  const data = parseApiResponse(text);
  if (!response.ok) {
    const detail = data?.detail || `${response.status} ${response.statusText}`;
    throw new Error(Array.isArray(detail) ? JSON.stringify(detail) : detail);
  }
  return data;
}

function parseApiResponse(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 300) };
  }
}

function renderList(listEl, items) {
  listEl.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    listEl.append(li);
  }
}

function renderClaims(claims = []) {
  els.claimsList.innerHTML = "";
  if (!claims.length) {
    els.claimsList.innerHTML = '<p class="muted">No se extrajeron claims evaluables.</p>';
    return;
  }

  for (const claim of claims) {
    const card = document.createElement("article");
    card.className = "item-card";
    card.innerHTML = `
      <span class="badge ${claim.verdict}">${claim.verdict}</span>
      <p>${escapeHtml(claim.claim)}</p>
      <div class="metrics">
        <span>support: ${claim.support_score}</span>
        <span>contradiction: ${claim.contradiction_score}</span>
        <span>matches: ${claim.matched_evidence}</span>
      </div>
    `;
    els.claimsList.append(card);
  }
}

function renderEvidence(evidence = []) {
  els.evidenceResultList.innerHTML = "";
  if (!evidence.length) {
    els.evidenceResultList.innerHTML = '<p class="muted">Sin evidencias externas.</p>';
    return;
  }

  for (const ev of evidence) {
    const card = document.createElement("article");
    card.className = "item-card";
    const detail = ev.error ? `<p class="muted">${escapeHtml(ev.error)}</p>` : "";
    const url = ev.url ? `<a class="evidence-link" href="${escapeHtml(ev.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(ev.url)}</a>` : "";
    card.innerHTML = `
      <span class="badge ${ev.status}">${ev.status}</span>
      <p>${escapeHtml(ev.title || ev.url)}</p>
      ${url}
      <div class="metrics">
        <span>${ev.extracted_chars} caracteres extraidos</span>
        <span>${escapeHtml(ev.source_type || "unknown")}</span>
        <span>reliability: ${ev.source_reliability ?? 0}</span>
      </div>
      ${detail}
    `;
    els.evidenceResultList.append(card);
  }
}

function renderDimensions(dimensions = {}) {
  els.dimensionsList.innerHTML = "";
  const labels = {
    media_authenticity: "Media authenticity",
    claim_factuality: "Claim factuality",
    source_reliability: "Source reliability",
    temporal_consistency: "Temporal consistency",
    geolocation_consistency: "Geolocation consistency",
    provenance_confidence: "Provenance confidence",
    deepfake_probability: "Deepfake probability",
  };

  for (const [key, label] of Object.entries(labels)) {
    const value = Number(dimensions[key] || 0);
    const row = document.createElement("div");
    row.className = "dimension-row";
    row.innerHTML = `
      <div>
        <strong>${label}</strong>
        <span>${Math.round(value * 100)}%</span>
      </div>
      <meter min="0" max="1" value="${value}"></meter>
    `;
    els.dimensionsList.append(row);
  }
}

function renderGraph(graph = { nodes: [], edges: [] }) {
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  els.graphList.innerHTML = `
    <div class="graph-summary">
      <strong>${nodes.length}</strong><span>nodes</span>
      <strong>${edges.length}</strong><span>edges</span>
    </div>
  `;
  for (const edge of edges.slice(0, 12)) {
    const row = document.createElement("p");
    row.textContent = `${edge.from} -> ${edge.type} -> ${edge.to}`;
    els.graphList.append(row);
  }
}

function renderReviews(reviews = [], reviewStatus = "AI_ANALYSIS") {
  els.reviewsList.innerHTML = `<p class="muted">Estado: ${escapeHtml(reviewStatus)}</p>`;
  for (const review of reviews.slice().reverse()) {
    const card = document.createElement("article");
    card.className = "item-card";
    card.innerHTML = `
      <span class="badge MIXED">${escapeHtml(review.status)}</span>
      <p>${escapeHtml(review.action)} por ${escapeHtml(review.analyst)}</p>
      <div class="metrics">
        <span>${escapeHtml(review.reviewed_at)}</span>
        ${review.verdict ? `<span>verdict: ${escapeHtml(review.verdict)}</span>` : ""}
      </div>
      ${review.notes ? `<p class="muted">${escapeHtml(review.notes)}</p>` : ""}
    `;
    els.reviewsList.append(card);
  }
}

function renderProviders(providers = []) {
  els.providersList.innerHTML = "";
  for (const provider of providers) {
    const card = document.createElement("article");
    card.className = "provider-row";
    card.innerHTML = `
      <strong>${escapeHtml(provider.provider)}</strong>
      <span class="provider-status">${escapeHtml(provider.status)}</span>
      <p>${escapeHtml(provider.capability)}</p>
    `;
    els.providersList.append(card);
  }
}

function renderArtifact(artifact) {
  const pipeline = (artifact.pipeline || [])
    .map((item) => `<li><strong>${escapeHtml(item.stage)}</strong>: ${escapeHtml(item.status)}${item.detail ? ` - ${escapeHtml(item.detail)}` : ""}</li>`)
    .join("");
  const transcription = artifact.metadata?.transcription?.text
    ? `<p><strong>Transcripcion</strong></p><p class="muted">${escapeHtml(artifact.metadata.transcription.text)}</p>`
    : "";
  const normalized = artifact.metadata?.normalized_audio_path
    ? `<p class="muted">WAV normalizado: ${escapeHtml(artifact.metadata.normalized_audio_path)}</p>`
    : "";
  const keyframes = artifact.metadata?.keyframes?.length
    ? `<p class="muted">Keyframes: ${artifact.metadata.keyframes.length}</p>`
    : "";
  els.artifactBox.innerHTML = `
    <p><strong>${escapeHtml(artifact.input_type)}</strong> ${escapeHtml(artifact.filename)}</p>
    <p class="muted">${artifact.size_bytes} bytes</p>
    <code>${escapeHtml(artifact.sha256)}</code>
    ${normalized}
    ${keyframes}
    ${transcription}
    <button type="button" class="ghost-button" id="search-artifact">Buscar hash</button>
    <ul>${pipeline}</ul>
  `;
  document.querySelector("#search-artifact").addEventListener("click", async () => {
    try {
      const result = await apiFetch("/v1/reality/media/search", {
        method: "POST",
        body: JSON.stringify({ sha256: artifact.sha256 }),
      });
      showToast(result.previously_seen ? `Artefacto visto: ${result.artifact_id}` : "Artefacto no visto antes.");
    } catch (error) {
      showToast(error.message);
    }
  });
}

function renderResult(result) {
  state.lastResult = result;
  els.resultPanel.classList.remove("hidden");
  els.resultVerdict.textContent = result.verdict;
  els.resultConfidence.textContent = `${Math.round((result.confidence || 0) * 100)}%`;
  els.resultId.textContent = result.investigation_id ? `ID: ${result.investigation_id}` : "";
  els.resultSource.innerHTML = result.source?.url
    ? `Origen: <a class="evidence-link" href="${escapeHtml(result.source.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(result.source.url)}</a>`
    : "";
  renderClaims(result.claims);
  renderEvidence(result.evidence);
  renderDimensions(result.dimensions);
  renderGraph(result.evidence_graph);
  renderReviews(result.reviews, result.review_status);
  els.certificateBox.innerHTML = `
    <p><strong>Hash</strong></p>
    <code>${escapeHtml(result.certificate_hash || "")}</code>
    <p class="muted">Content hash: ${escapeHtml(result.content_hash || "")}</p>
  `;
  renderList(els.explanationList, result.explanation || []);
  renderList(els.limitationsList, result.limitations || []);
  els.resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function checkHealth() {
  try {
    const response = await fetch("/v1/health");
    const data = await response.json();
    if (!response.ok) throw new Error("health failed");
    els.healthDot.className = "dot dot-ok";
    els.healthTitle.textContent = "Servicio activo";
    els.healthDetail.textContent = `${data.engine} ${data.version}`;
  } catch (error) {
    els.healthDot.className = "dot dot-error";
    els.healthTitle.textContent = "Servicio no disponible";
    els.healthDetail.textContent = "Revisa docker compose logs";
  }
}

async function authRequest(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "No se pudo completar la operación.");
  return data;
}

async function requireSession() {
  const response = await fetch("/auth/me");
  if (!response.ok) window.location.replace("/login");
}

els.logoutButton?.addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST" });
  window.location.replace("/login");
});

document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    const isText = getMode() === "text";
    els.textField.classList.toggle("hidden", !isText);
    els.urlField.classList.toggle("hidden", isText);
  });
});

els.addEvidence?.addEventListener("click", () => addEvidenceRow());

els.resetButton?.addEventListener("click", () => {
  els.form.reset();
  els.evidenceList.innerHTML = "";
  els.resultPanel.classList.add("hidden");
  addEvidenceRow("https://example.com/");
});

els.form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy(true);
  try {
    const result = await apiFetch("/v1/reality/verify", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });
    els.investigationId.value = result.investigation_id;
    renderResult(result);
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
});

els.searchPrevious?.addEventListener("click", async () => {
  try {
    const payload = buildPayload();
    delete payload.evidence_urls;
    const result = await apiFetch("/v1/reality/media/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.previously_seen) {
      els.investigationId.value = result.investigation_id;
      showToast(`Contenido visto antes por ${result.matched_on}.`);
      return;
    }
    showToast("No hay coincidencias previas.");
  } catch (error) {
    showToast(error.message);
  }
});

els.loadInvestigation?.addEventListener("click", async () => {
  const id = els.investigationId.value.trim();
  if (!id) {
    showToast("Indica un investigation_id.");
    return;
  }

  try {
    const result = await apiFetch(`/v1/reality/investigations/${encodeURIComponent(id)}`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });
    renderResult(result);
  } catch (error) {
    showToast(error.message);
  }
});

els.loadProviders?.addEventListener("click", async () => {
  try {
    const providers = await apiFetch("/v1/reality/reverse-search/providers", {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });
    renderProviders(providers);
  } catch (error) {
    showToast(error.message);
  }
});

els.uploadMedia?.addEventListener("click", async () => {
  const file = els.mediaFile.files[0];
  if (!file) {
    showToast("Selecciona un archivo.");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  try {
    const artifact = await apiFormFetch("/v1/reality/media/ingest", formData);
    renderArtifact(artifact);
    showToast("Artefacto ingerido.");
  } catch (error) {
    showToast(error.message);
  }
});

els.downloadMedia?.addEventListener("click", async () => {
  const url = els.mediaUrl.value.trim();
  if (!url) {
    showToast("Indica una URL de vídeo.");
    return;
  }
  els.downloadMedia.disabled = true;
  els.downloadMedia.textContent = "Descargando...";
  try {
    const artifact = await apiFetch("/v1/reality/media/ingest-url", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
    renderArtifact(artifact);
    showToast("Vídeo descargado y preparado para análisis.");
  } catch (error) {
    showToast(error.message);
  } finally {
    els.downloadMedia.disabled = false;
    els.downloadMedia.textContent = "Descargar y analizar";
  }
});

els.loadCertificate?.addEventListener("click", async () => {
  const id = state.lastResult?.investigation_id || els.investigationId.value.trim();
  if (!id) {
    showToast("Primero carga o genera una investigacion.");
    return;
  }

  try {
    const cert = await apiFetch(`/v1/reality/investigations/${encodeURIComponent(id)}/certificate`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });
    els.certificateBox.innerHTML = `<pre>${escapeHtml(JSON.stringify(cert, null, 2))}</pre>`;
  } catch (error) {
    showToast(error.message);
  }
});

els.submitReview?.addEventListener("click", async () => {
  const id = state.lastResult?.investigation_id || els.investigationId.value.trim();
  if (!id) {
    showToast("Primero carga o genera una investigacion.");
    return;
  }
  const analyst = els.reviewAnalyst.value.trim();
  if (analyst.length < 2) {
    showToast("Indica el analista o equipo.");
    return;
  }

  const body = {
    action: els.reviewAction.value,
    analyst,
    notes: els.reviewNotes.value.trim() || null,
  };
  if (els.reviewVerdict.value) {
    body.verdict = els.reviewVerdict.value;
  }

  try {
    const result = await apiFetch(`/v1/reality/investigations/${encodeURIComponent(id)}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    renderResult(result);
    showToast("Revision registrada.");
  } catch (error) {
    showToast(error.message);
  }
});

els.copyId?.addEventListener("click", async () => {
  if (!state.lastResult?.investigation_id) return;
  await navigator.clipboard.writeText(state.lastResult.investigation_id);
  showToast("Investigation ID copiado.");
});

if (els.form) {
  addEvidenceRow("https://example.com/");
  checkHealth();
  requireSession();
}
