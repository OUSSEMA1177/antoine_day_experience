const API_BASE = window.location.origin.includes("8000")
  ? window.location.origin
  : "http://localhost:8000";

const dateSelect = document.getElementById("date-select");
const pathFilter = document.getElementById("path-filter");
const refreshBtn = document.getElementById("refresh-btn");
const tbody = document.getElementById("logs-tbody");
const tableMeta = document.getElementById("table-meta");

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso.slice(11, 19) || iso;
  }
}

function pathClass(path) {
  if (path === "deterministic") return "path-deterministic";
  if (path === "nlu+dialog") return "path-nlu-dialog";
  if (path === "nlu") return "path-nlu";
  if (path === "dialog") return "path-dialog";
  return "";
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderStats(stats) {
  const total = stats.total ?? 0;
  const zero = stats.deterministic ?? 0;
  const zeroPct = total > 0 ? Math.round((zero / total) * 100) : 0;
  const avgLatency = stats.avg_latency_ms != null ? Math.round(stats.avg_latency_ms) : null;

  document.getElementById("kpi-total").textContent = String(total);
  document.getElementById("kpi-zero").textContent = String(zero);
  document.getElementById("kpi-llm").textContent = String(stats.llm_turns ?? 0);
  document.getElementById("kpi-tokens").textContent = String(stats.total_tokens ?? 0);
  document.getElementById("kpi-latency").textContent = avgLatency != null ? `${avgLatency} ms` : "—";
  document.getElementById("kpi-errors").textContent = String(stats.errors ?? 0);

  // Bandeau hero (façon chiffres clés B2B)
  const statTotal = document.getElementById("stat-total");
  const statZeroPct = document.getElementById("stat-zero-pct");
  const statLatency = document.getElementById("stat-latency");
  if (statTotal) statTotal.textContent = String(total);
  if (statZeroPct) statZeroPct.textContent = total > 0 ? `${zeroPct}%` : "—";
  if (statLatency) statLatency.textContent = avgLatency != null ? `${avgLatency} ms` : "—";
}

function renderRows(events) {
  if (!events.length) {
    tbody.innerHTML =
      '<tr class="empty-row"><td colspan="7">Aucun événement pour ce filtre.</td></tr>';
    return;
  }

  tbody.innerHTML = events
    .map((ev) => {
      const path = ev.path || "—";
      const pill = `<span class="path-pill ${pathClass(path)}">${escapeHtml(path)}</span>`;
      return `<tr>
        <td class="mono">${escapeHtml(fmtTime(ev.ts))}</td>
        <td>${pill}</td>
        <td class="mono">${escapeHtml(ev.intent || "—")}</td>
        <td>${escapeHtml(ev.destination || "—")}</td>
        <td class="mono">${escapeHtml(String(ev.total_tokens ?? 0))}</td>
        <td class="mono">${escapeHtml(String(ev.latency_ms ?? 0))} ms</td>
        <td class="preview" title="${escapeHtml(ev.user_msg_preview || "")}">${escapeHtml(ev.user_msg_preview || "—")}</td>
      </tr>`;
    })
    .join("");
}

function fillDates(available, current) {
  const days = available && available.length ? available : [current];
  dateSelect.innerHTML = days
    .map((d) => `<option value="${escapeHtml(d)}"${d === current ? " selected" : ""}>${escapeHtml(d)}</option>`)
    .join("");
  if (!days.includes(current)) {
    dateSelect.insertAdjacentHTML(
      "afterbegin",
      `<option value="${escapeHtml(current)}" selected>${escapeHtml(current)}</option>`
    );
  }
}

async function loadLogs() {
  const date = dateSelect.value || "";
  const path = pathFilter.value || "";
  const params = new URLSearchParams({ limit: "150" });
  if (date) params.set("date", date);
  if (path) params.set("path", path);

  tbody.innerHTML = '<tr class="empty-row"><td colspan="7">Chargement…</td></tr>';

  try {
    const res = await fetch(`${API_BASE}/api/logs?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Si aujourd'hui est vide, basculer sur la date dispo la plus récente
    const available = data.available_dates || [];
    if (
      !date &&
      (data.events || []).length === 0 &&
      available.length &&
      available[0] !== data.date
    ) {
      fillDates(available, available[0]);
      dateSelect.value = available[0];
      return loadLogs();
    }

    fillDates(available, data.date);
    renderStats(data.stats || {});
    renderRows(data.events || []);
    tableMeta.textContent = `${data.events?.length ?? 0} lignes · ${data.date}`;
  } catch (err) {
    const msg = err instanceof Error ? err.message : "erreur";
    tbody.innerHTML = `<tr class="empty-row"><td colspan="7">Impossible de charger les logs (${escapeHtml(msg)}).</td></tr>`;
    tableMeta.textContent = "erreur";
  }
}

refreshBtn.addEventListener("click", loadLogs);
dateSelect.addEventListener("change", loadLogs);
pathFilter.addEventListener("change", loadLogs);

// Première charge : date du jour (API choisit si vide)
loadLogs();
setInterval(loadLogs, 15000);
