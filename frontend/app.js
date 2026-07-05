const API_BASE = window.location.origin.includes("8000")
  ? window.location.origin
  : "http://localhost:8000";

const chatEl = document.getElementById("chat");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("message-input");
const quotePanelEl = document.getElementById("quote-panel");
const quoteSummaryEl = document.getElementById("quote-summary");
const quoteGenerateBtn = document.getElementById("quote-generate-btn");
const quoteHintEl = document.getElementById("quote-hint");

const SESSION_KEY = "day_experience_session_id";
const PARTNER_KEY = "day_experience_partner_id";

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function getPartnerId() {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get("partner_id");
  if (fromUrl) {
    localStorage.setItem(PARTNER_KEY, fromUrl);
    return fromUrl;
  }
  return localStorage.getItem(PARTNER_KEY) || null;
}

function appendMessage(text, role) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function appendQuoteDownload(pdfUrl, devisRef) {
  const wrap = document.createElement("div");
  wrap.className = "message bot quote-download";

  const label = document.createElement("p");
  label.textContent = devisRef
    ? `Devis ${devisRef} prêt :`
    : "Votre devis est prêt :";
  wrap.appendChild(label);

  const link = document.createElement("a");
  link.href = `${API_BASE}${pdfUrl}`;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.className = "quote-btn";
  link.textContent = "Télécharger le PDF";
  wrap.appendChild(link);

  chatEl.appendChild(wrap);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function updateQuotePanel(data) {
  const activities = data.quote_activities || [];
  const ready = Boolean(data.quote_ready);

  quotePanelEl.hidden = false;

  if (activities.length > 0) {
    const lines = activities.map(
      (a, i) => `${i + 1}. ${a.titre} — ${a.prix_net || "?"} € net`
    );
    quoteSummaryEl.textContent = [
      data.destination ? `Destination : ${data.destination}` : "",
      data.nom_agence ? `Agence : ${data.nom_agence}` : "",
      "Activités sélectionnées :",
      ...lines,
    ].filter(Boolean).join("\n");
  } else {
    quoteSummaryEl.textContent = ready
      ? "Prêt pour le devis."
      : "Complétez la conversation (destination, profil, activités, agence).";
  }

  quoteGenerateBtn.disabled = !ready;

  if (ready) {
    quoteHintEl.textContent =
      "Cliquez pour générer le devis White Label PDF (sans passer par l'IA).";
  } else {
    quoteHintEl.textContent =
      "Le bouton s'active quand destination, profil, activités catalogue et agence sont connus.";
  }
}

async function refreshQuoteState() {
  try {
    const res = await fetch(
      `${API_BASE}/session/${getSessionId()}/quote-state`
    );
    if (res.ok) {
      updateQuotePanel(await res.json());
    }
  } catch {
    /* ignore */
  }
}

quoteGenerateBtn.addEventListener("click", async () => {
  quoteGenerateBtn.disabled = true;
  quoteHintEl.textContent = "Génération du PDF en cours…";

  try {
    const body = { session_id: getSessionId() };
    const partnerId = getPartnerId();
    if (partnerId) body.partner_id = partnerId;

    const res = await fetch(`${API_BASE}/quote/from-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Erreur ${res.status}`);
    }

    const data = await res.json();
    appendMessage(
      `Devis ${data.devis_ref} généré pour ${data.destination} (${data.activity_count} activités, total net ${data.total_net}).`,
      "bot"
    );
    appendQuoteDownload(data.pdf_url, data.devis_ref);
    quoteHintEl.textContent = "Devis généré avec succès.";
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Échec génération devis.";
    appendMessage(msg, "bot");
    quoteHintEl.textContent = msg;
    quoteGenerateBtn.disabled = false;
  }
});

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = inputEl.value.trim();
  if (!message) return;

  appendMessage(message, "user");
  inputEl.value = "";

  try {
    const body = {
      session_id: getSessionId(),
      message,
    };
    const partnerId = getPartnerId();
    if (partnerId) {
      body.partner_id = partnerId;
    }

    const res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = err.detail;
      const msg = typeof detail === "string"
        ? detail
        : `Erreur serveur (${res.status})`;
      throw new Error(msg);
    }

    const data = await res.json();
    appendMessage(data.reply, "bot");
    updateQuotePanel(data);
    if (data.quote_url) {
      appendQuoteDownload(data.quote_url, data.devis_ref);
    }
  } catch (err) {
    const msg = err instanceof Error && err.message
      ? err.message
      : "Impossible de joindre l'agent. Vérifiez que le backend tourne (uvicorn).";
    appendMessage(msg, "bot");
  }
});

refreshQuoteState();

async function initGreeting() {
  const partnerId = getPartnerId();
  if (!partnerId) return;

  const firstBot = chatEl.querySelector(".message.bot");
  if (!firstBot) return;

  try {
    const res = await fetch(`${API_BASE}/partners/${encodeURIComponent(partnerId)}`);
    if (res.ok) {
      const data = await res.json();
      if (data.greeting_message) {
        firstBot.textContent = data.greeting_message;
      }
    }
  } catch {
    /* garde le message par défaut */
  }
}

initGreeting();
