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
const launcherEl = document.getElementById("chat-launcher");
const widgetEl = document.getElementById("chat-widget");
const minimizeEl = document.getElementById("chat-minimize");
const newSessionEl = document.getElementById("chat-new-session");
const dockEl = document.querySelector(".dev-dock");
const dockToggleEl = document.getElementById("dock-toggle");
const sessionDisplayEl = document.getElementById("session-display");
const faqListEl = document.getElementById("faq-list");
const faqSearchEl = document.getElementById("faq-search");
const faqEmptyEl = document.getElementById("faq-empty");
const panelChatEl = document.getElementById("panel-chat");
const panelFaqEl = document.getElementById("panel-faq");

let faqCache = null;
let faqLoaded = false;

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

function setWidgetOpen(open) {
  widgetEl.classList.toggle("is-open", open);
  launcherEl.classList.toggle("is-open", open);
  widgetEl.setAttribute("aria-hidden", open ? "false" : "true");
  launcherEl.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) {
    requestAnimationFrame(() => {
      if (panelChatEl.classList.contains("is-active")) {
        inputEl.focus();
        chatEl.scrollTop = chatEl.scrollHeight;
      } else if (faqSearchEl) {
        faqSearchEl.focus();
      }
    });
  }
}

function setActiveTab(tab) {
  const isChat = tab === "chat";
  document.querySelectorAll(".widget-tab").forEach((btn) => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  panelChatEl.classList.toggle("is-active", isChat);
  panelChatEl.hidden = !isChat;
  panelFaqEl.classList.toggle("is-active", !isChat);
  panelFaqEl.hidden = isChat;
  if (!isChat) {
    ensureFaqLoaded().then(() => {
      renderFaqList(faqSearchEl.value || "");
      faqSearchEl.focus();
    });
  } else {
    requestAnimationFrame(() => {
      inputEl.focus();
      chatEl.scrollTop = chatEl.scrollHeight;
    });
  }
}

function normFaq(text) {
  return String(text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function filterFaqItems(query) {
  const items = faqCache || [];
  const needle = normFaq(query).trim();
  if (!needle) return items;
  const tokens = needle.split(/\s+/).filter((t) => t.length >= 2);
  return items.filter((row) => {
    const blob = normFaq(
      `${row.question} ${row.reponse} ${row.categorie}`
    );
    if (blob.includes(needle)) return true;
    return tokens.every((t) => blob.includes(t));
  });
}

function renderFaqList(query) {
  if (!faqListEl) return;
  const items = filterFaqItems(query);
  faqListEl.innerHTML = "";
  if (faqEmptyEl) {
    faqEmptyEl.hidden = items.length > 0;
  }
  items.forEach((row) => {
    const item = document.createElement("article");
    item.className = "faq-item";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "faq-item-q";
    btn.setAttribute("aria-expanded", "false");

    const textWrap = document.createElement("span");
    textWrap.className = "faq-item-text";
    if (row.categorie) {
      const cat = document.createElement("span");
      cat.className = "faq-item-cat";
      cat.textContent = row.categorie;
      textWrap.appendChild(cat);
    }
    const q = document.createElement("span");
    q.className = "faq-item-title";
    q.textContent = row.question;
    textWrap.appendChild(q);
    btn.appendChild(textWrap);

    const chevron = document.createElement("span");
    chevron.className = "faq-chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.innerHTML =
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    btn.appendChild(chevron);

    const answer = document.createElement("div");
    answer.className = "faq-item-a";
    const p = document.createElement("p");
    p.style.margin = "0";
    p.textContent = row.reponse;
    answer.appendChild(p);

    const ask = document.createElement("button");
    ask.type = "button";
    ask.className = "faq-ask";
    ask.textContent = "Demander à Antoine";
    ask.addEventListener("click", (e) => {
      e.stopPropagation();
      setActiveTab("chat");
      inputEl.value = row.question;
      inputEl.focus();
    });
    answer.appendChild(ask);

    btn.addEventListener("click", () => {
      const open = item.classList.toggle("is-open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });

    item.appendChild(btn);
    item.appendChild(answer);
    faqListEl.appendChild(item);
  });
}

async function ensureFaqLoaded() {
  if (faqLoaded && faqCache) return faqCache;
  try {
    const res = await fetch(`${API_BASE}/faq`);
    if (!res.ok) throw new Error("FAQ unavailable");
    const data = await res.json();
    faqCache = data.items || [];
    faqLoaded = true;
  } catch {
    faqCache = [];
    faqLoaded = true;
    if (faqEmptyEl) {
      faqEmptyEl.hidden = false;
      faqEmptyEl.textContent = "Impossible de charger la FAQ.";
    }
  }
  return faqCache;
}

document.querySelectorAll(".widget-tab").forEach((btn) => {
  btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
});

if (faqSearchEl) {
  faqSearchEl.addEventListener("input", () => {
    renderFaqList(faqSearchEl.value);
  });
}

function toggleWidget() {
  setWidgetOpen(!widgetEl.classList.contains("is-open"));
}

launcherEl.addEventListener("click", toggleWidget);
minimizeEl.addEventListener("click", () => setWidgetOpen(false));

async function startNewSession() {
  const oldId = localStorage.getItem(SESSION_KEY);
  if (oldId) {
    try {
      await fetch(`${API_BASE}/session/${encodeURIComponent(oldId)}`, {
        method: "DELETE",
      });
    } catch {
      /* ignore */
    }
  }
  const id = crypto.randomUUID();
  localStorage.setItem(SESSION_KEY, id);
  if (sessionDisplayEl) {
    sessionDisplayEl.textContent = id.slice(0, 8) + "…";
  }
  chatEl.innerHTML = "";
  const div = document.createElement("div");
  div.className = "message bot";
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent =
    "Bonjour ! Votre client a choisi sa destination ? Dites-moi où il va — je vous montre ce qu'il peut y vivre.";
  div.appendChild(body);
  chatEl.appendChild(div);
  if (quoteGenerateBtn) quoteGenerateBtn.disabled = true;
  if (quoteSummaryEl) {
    quoteSummaryEl.textContent =
      "Complétez la conversation (destination, profil, activités, agence).";
  }
  setActiveTab("chat");
  await initGreeting();
  refreshQuoteState();
  inputEl.focus();
}

if (newSessionEl) {
  newSessionEl.addEventListener("click", () => {
    startNewSession();
  });
}

dockToggleEl.addEventListener("click", () => {
  const collapsed = dockEl.classList.toggle("is-collapsed");
  dockToggleEl.setAttribute("aria-expanded", collapsed ? "false" : "true");
});

function appendMessage(text, role, usage = null) {
  const div = document.createElement("div");
  div.className = `message ${role}`;

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;
  div.appendChild(body);

  if (role === "bot" && usage) {
    const badge = document.createElement("div");
    badge.className = "usage-badge";
    if (usage.llm_used) {
      const model = usage.llm_model ? usage.llm_model.split("/").pop() : "LLM";
      badge.textContent = `IA · ${model} · ${usage.total_tokens} tokens (${usage.prompt_tokens}↓ ${usage.completion_tokens}↑)`;
      badge.classList.add("usage-llm");
    } else {
      badge.textContent = "Réponse catalogue · 0 token";
      badge.classList.add("usage-local");
    }
    div.appendChild(badge);
  }

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

  if (quotePanelEl) {
    quotePanelEl.hidden = false;
  }

  if (activities.length > 0) {
    const lines = activities.map(
      (a, i) => `${i + 1}. ${a.titre} — ${a.prix_net || "?"} € net`
    );
    quoteSummaryEl.textContent = [
      data.destination ? `Destination : ${data.destination}` : "",
      data.nom_agence ? `Agence : ${data.nom_agence}` : "",
      "Activités sélectionnées :",
      ...lines,
    ]
      .filter(Boolean)
      .join("\n");
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
    setWidgetOpen(true);
    appendMessage(
      `Devis ${data.devis_ref} généré pour ${data.destination} (${data.activity_count} activités, total net ${data.total_net}).`,
      "bot"
    );
    appendQuoteDownload(data.pdf_url, data.devis_ref);
    quoteHintEl.textContent = "Devis généré avec succès.";
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Échec génération devis.";
    setWidgetOpen(true);
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
      const msg =
        typeof detail === "string"
          ? detail
          : `Erreur serveur (${res.status})`;
      throw new Error(msg);
    }

    const data = await res.json();
    appendMessage(data.reply, "bot", {
      llm_used: data.llm_used,
      llm_model: data.llm_model,
      prompt_tokens: data.prompt_tokens,
      completion_tokens: data.completion_tokens,
      total_tokens: data.total_tokens,
    });
    updateQuotePanel(data);
    if (data.quote_url) {
      appendQuoteDownload(data.quote_url, data.devis_ref);
    }
  } catch (err) {
    const msg =
      err instanceof Error && err.message
        ? err.message
        : "Impossible de joindre l'agent. Vérifiez que le backend tourne (uvicorn).";
    appendMessage(msg, "bot");
  }
});

sessionDisplayEl.textContent = getSessionId().slice(0, 8) + "…";
refreshQuoteState();

async function initGreeting() {
  const partnerId = getPartnerId();
  if (!partnerId) return;

  const firstBot = chatEl.querySelector(".message.bot .message-body")
    || chatEl.querySelector(".message.bot");
  if (!firstBot) return;

  try {
    const res = await fetch(
      `${API_BASE}/partners/${encodeURIComponent(partnerId)}`
    );
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

// Ouvre le widget au chargement pour la démo QA
setWidgetOpen(true);
initGreeting();
