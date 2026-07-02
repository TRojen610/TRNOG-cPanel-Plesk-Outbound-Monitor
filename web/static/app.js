const appConfig = window.TRNOG_APP || {
  embed: false,
  defaultWindowSeconds: 3600,
  fallbackPollSeconds: 5,
};

const summaryTotal = document.getElementById("summary-total");
const summaryUsers = document.getElementById("summary-users");
const summaryDestinations = document.getElementById("summary-destinations");
const summaryPorts = document.getElementById("summary-ports");
const eventsBody = document.getElementById("events-body");
const topDestinations = document.getElementById("top-destinations");
const topUsers = document.getElementById("top-users");
const topPorts = document.getElementById("top-ports");
const collectorStatus = document.getElementById("collector-status");
const refreshStatus = document.getElementById("refresh-status");
const tableCaption = document.getElementById("table-caption");
const filtersForm = document.getElementById("filters-form");
const refreshButton = document.getElementById("refresh-button");

let refreshTimer = null;
let refreshInFlight = false;

filtersForm.elements.window_seconds.value = String(appConfig.defaultWindowSeconds);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function getFilters() {
  const formData = new FormData(filtersForm);
  const filters = {
    window_seconds: formData.get("window_seconds") || appConfig.defaultWindowSeconds,
    user: (formData.get("user") || "").trim(),
    dst_ip: (formData.get("dst_ip") || "").trim(),
    port: (formData.get("port") || "").trim(),
    family: formData.get("family") || "",
    search: (formData.get("search") || "").trim(),
  };
  return filters;
}

function toQueryString(filters, extra = {}) {
  const params = new URLSearchParams();
  Object.entries({ ...filters, ...extra }).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) {
      params.set(key, value);
    }
  });
  return params.toString();
}

async function fetchJson(path, filters, extra) {
  const response = await fetch(`${path}?${toQueryString(filters, extra)}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

function setRefreshStatus(text, isError = false) {
  refreshStatus.textContent = text;
  refreshStatus.classList.toggle("status-danger", isError);
  refreshStatus.classList.toggle("status-muted", !isError);
}

function renderSummary(summary) {
  summaryTotal.textContent = summary.total_events.toLocaleString();
  summaryUsers.textContent = summary.unique_users.toLocaleString();
  summaryDestinations.textContent = summary.unique_destinations.toLocaleString();
  summaryPorts.textContent = summary.unique_ports.toLocaleString();
  tableCaption.textContent = `${summary.total_events.toLocaleString()} events in selected window`;
}

function renderRankList(container, items, renderer) {
  if (!items.length) {
    container.innerHTML = '<div class="table-empty">No activity for this filter set</div>';
    return;
  }
  container.innerHTML = items
    .map((item, index) => renderer(item, index + 1))
    .join("");
}

function renderEvents(items) {
  if (!items.length) {
    eventsBody.innerHTML = '<tr><td colspan="7" class="table-empty">No outbound events match the current filters</td></tr>';
    return;
  }

  eventsBody.innerHTML = items
    .map((item) => {
      const destination = `${escapeHtml(item.dst_ip)}:${escapeHtml(item.dst_port)}`;
      const process = `${escapeHtml(item.comm)}<br><code>${escapeHtml(item.cmdline || "-")}</code>`;
      const source = `${escapeHtml(item.src_ip)}:${escapeHtml(item.src_port)}`;
      const hostHint = item.dst_host
        ? `<span class="pill">${escapeHtml(item.dst_host_source || "hint")}</span> <code>${escapeHtml(item.dst_host)}</code>`
        : '<span class="table-empty">-</span>';
      return `
        <tr>
          <td><code>${escapeHtml(item.timestamp)}</code></td>
          <td>${escapeHtml(item.user)}</td>
          <td>${process}</td>
          <td><code>${source}</code></td>
          <td><code>${destination}</code></td>
          <td>${escapeHtml(item.family)}</td>
          <td>${hostHint}</td>
        </tr>
      `;
    })
    .join("");
}

function renderHealth(health) {
  collectorStatus.textContent = `${health.status} / ${health.collector_mode}`;
  collectorStatus.classList.remove("status-danger", "status-muted");
  if (health.status === "degraded") {
    collectorStatus.classList.add("status-danger");
  } else if (health.status !== "running") {
    collectorStatus.classList.add("status-muted");
  }
}

async function refreshDashboard(reason = "refresh") {
  if (refreshInFlight) {
    return;
  }

  refreshInFlight = true;
  setRefreshStatus(`Updating (${reason})`);
  const filters = getFilters();

  try {
    const [health, summary, events, destinations, users, ports] = await Promise.all([
      fetchJson("health", {}, {}),
      fetchJson("api/summary", filters, {}),
      fetchJson("api/events", filters, { limit: 200 }),
      fetchJson("api/top/destinations", filters, { limit: 8 }),
      fetchJson("api/top/users", filters, { limit: 8 }),
      fetchJson("api/top/ports", filters, { limit: 8 }),
    ]);

    renderHealth(health);
    renderSummary(summary);
    renderEvents(events.items || []);
    renderRankList(topDestinations, destinations.items || [], (item, index) => `
      <div class="rank-item">
        <div>
          <strong>#${index} ${escapeHtml(item.dst_host || item.dst_ip)}</strong>
          <span>${escapeHtml(item.dst_ip)}:${escapeHtml(item.dst_port)}</span>
        </div>
        <strong>${Number(item.count).toLocaleString()}</strong>
      </div>
    `);
    renderRankList(topUsers, users.items || [], (item, index) => `
      <div class="rank-item">
        <div>
          <strong>#${index} ${escapeHtml(item.user)}</strong>
          <span>Account activity</span>
        </div>
        <strong>${Number(item.count).toLocaleString()}</strong>
      </div>
    `);
    renderRankList(topPorts, ports.items || [], (item, index) => `
      <div class="rank-item">
        <div>
          <strong>#${index} Port ${escapeHtml(item.port)}</strong>
          <span>Destination port</span>
        </div>
        <strong>${Number(item.count).toLocaleString()}</strong>
      </div>
    `);
    setRefreshStatus(`Last refresh ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    console.error(error);
    setRefreshStatus("Refresh failed", true);
  } finally {
    refreshInFlight = false;
  }
}

function debounceRefresh(reason) {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => refreshDashboard(reason), 250);
}

function startRealtime() {
  if (appConfig.embed) {
    window.setInterval(() => refreshDashboard("poll"), appConfig.fallbackPollSeconds * 1000);
    return;
  }

  const stream = new EventSource("events/stream");
  stream.onmessage = () => debounceRefresh("live");
  stream.onerror = () => {
    stream.close();
    window.setInterval(() => refreshDashboard("poll"), appConfig.fallbackPollSeconds * 1000);
  };
}

filtersForm.addEventListener("input", () => debounceRefresh("filter"));
filtersForm.addEventListener("change", () => debounceRefresh("filter"));
refreshButton.addEventListener("click", () => refreshDashboard("manual"));

refreshDashboard("startup");
startRealtime();
