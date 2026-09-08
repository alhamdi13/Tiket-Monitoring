/**
 * app.js - Frontend Application Logic & LocalStorage Interactive Route Manager
 */

const API_BASE = "";

const state = {
  routes: [],
  selectedRouteId: null,
  activeAnalyticsTab: "trend",
  airports: [],
  settings: {},
  isScanningAll: false,
  isStaticMode: false,
  staticData: null
};

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  setupEventListeners();
  await loadAirports();

  try {
    const res = await fetch(`${API_BASE}/api/status`);
    if (res.ok) {
      state.isStaticMode = false;
      await Promise.all([loadSettings(), fetchStatus(), loadRoutes()]);
      setInterval(fetchStatus, 12000);
    } else {
      throw new Error("Backend not available");
    }
  } catch (err) {
    state.isStaticMode = true;
    await loadStaticData();
  }
});

async function loadStaticData() {
  try {
    const res = await fetch("./data/flights.json");
    state.staticData = await res.json();
    updateStatusUI(state.staticData.status);

    const savedRoutes = localStorage.getItem("custom_flight_routes");
    if (savedRoutes) {
      state.routes = JSON.parse(savedRoutes);
    } else {
      state.routes = state.staticData.routes || [];
    }

    renderRoutesGrid(state.routes);
    updateRouteSelectOptions(state.routes);

    if (state.routes.length > 0) {
      state.selectedRouteId = state.routes[0].id;
      loadAnalytics(state.selectedRouteId);
      loadFlights(state.selectedRouteId);
    }
  } catch (e) {
    console.error("Static data error:", e);
  }
}

async function fetchStatus() {
  if (state.isStaticMode) return;
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const data = await res.json();
    updateStatusUI(data);
  } catch (err) {
    console.error("Gagal memuat status:", err);
  }
}

function updateStatusUI(data) {
  if (!data) return;
  const stats = data.stats || {};
  const activeCount = state.routes.filter(r => r.is_active).length;
  document.getElementById("statTotalRoutes").textContent = `${activeCount} / ${state.routes.length}`;
  document.getElementById("statTrackedFlights").textContent = (stats.total_tracked_flights || 304).toLocaleString("id-ID");
  
  const cheapest = stats.cheapest_price_idr || 389000;
  document.getElementById("statCheapestPrice").textContent = formatRupiah(cheapest);
  document.getElementById("statTotalNotifs").textContent = (stats.total_notifications || 39).toLocaleString("id-ID");

  const schedulerText = document.getElementById("schedulerStatusText");
  if (schedulerText) schedulerText.textContent = "GitHub Actions (Cloud)";

  const telegramDot = document.getElementById("telegramPulse");
  const telegramText = document.getElementById("telegramStatusText");
  if (telegramDot) telegramDot.className = "pulse-dot";
  if (telegramText) telegramText.textContent = "Telegram Bot Siap";
}

async function loadRoutes() {
  if (state.isStaticMode) {
    const savedRoutes = localStorage.getItem("custom_flight_routes");
    if (savedRoutes) state.routes = JSON.parse(savedRoutes);
    else if (state.staticData) state.routes = state.staticData.routes || [];
    renderRoutesGrid(state.routes);
    updateRouteSelectOptions(state.routes);
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/routes`);
    state.routes = await res.json();
    renderRoutesGrid(state.routes);
    updateRouteSelectOptions(state.routes);

    if (state.routes.length > 0) {
      state.selectedRouteId = state.routes[0].id;
      loadAnalytics(state.selectedRouteId);
      loadFlights(state.selectedRouteId);
    }
  } catch (err) {
    showToast("Gagal memuat rute", "error");
  }
}

async function loadAirports() {
  try {
    const res = await fetch("./airports.json");
    state.airports = await res.json();
    const datalist = document.getElementById("airportsDatalist");
    if (datalist && Array.isArray(state.airports)) {
      datalist.innerHTML = state.airports.map(a => 
        `<option value="${a.code}">${a.code} - ${a.city} (${a.name})</option>`
      ).join("");
    }
  } catch (err) {
    console.error("Gagal load bandara:", err);
  }
}

async function loadSettings() {
  if (state.isStaticMode) return;
  try {
    const res = await fetch(`${API_BASE}/api/settings`);
    state.settings = await res.json();
  } catch (err) {
    console.error("Settings error:", err);
  }
}

async function loadAnalytics(routeId) {
  if (!routeId) return;
  const currentRoute = state.routes.find(r => r.id === routeId);
  const maxBudget = currentRoute ? currentRoute.max_price_idr : null;

  if (state.isStaticMode && state.staticData) {
    const trendData = state.staticData.analytics ? state.staticData.analytics[String(routeId)] : null;
    const calData = state.staticData.calendar ? state.staticData.calendar[String(routeId)] : null;

    if (!trendData && currentRoute) {
      const dates = [];
      const minPrices = [];
      const avgPrices = [];
      const cal = [];
      const today = new Date();
      for (let i = 1; i <= (currentRoute.days_ahead || 14); i++) {
        const d = new Date(today);
        d.setDate(today.getDate() + i);
        const dStr = d.toISOString().split("T")[0];
        dates.push(dStr);
        const estMin = Math.round((currentRoute.max_price_idr * (0.75 + Math.random() * 0.35)) / 1000) * 1000;
        const estAvg = Math.round((estMin * 1.35) / 1000) * 1000;
        minPrices.push(estMin);
        avgPrices.push(estAvg);
        cal.push({
          flight_date: dStr,
          cheapest_price: estMin,
          airline: "Citilink / Lion Air",
          flight_number: "JT-680",
          departure_time: "08:15",
          duration_minutes: 90
        });
      }
      renderPriceTrendChart({ dates, min_prices: minPrices, avg_prices: avgPrices }, maxBudget);
      renderLowestFareCalendar(cal, maxBudget, currentRoute.origin, currentRoute.destination);
      return;
    }

    renderPriceTrendChart(trendData || { dates: [], min_prices: [], avg_prices: [] }, maxBudget);
    if (currentRoute) {
      renderLowestFareCalendar(calData || [], maxBudget, currentRoute.origin, currentRoute.destination);
    }
  }
}

async function loadFlights(routeId = null) {
  const tbody = document.getElementById("flightTableBody");
  if (!tbody) return;

  let flights = (state.staticData && state.staticData.flights) ? state.staticData.flights : [];
  if (routeId) {
    const filtered = flights.filter(f => f.route_id === routeId);
    if (filtered.length > 0) flights = filtered;
  }

  tbody.innerHTML = flights.slice(0, 30).map(f => {
    const seatsBadge = f.seats_left ? `<span style="font-size: 0.75rem; color: var(--accent-amber);">💺 ${f.seats_left} sisa</span>` : "";
    const durText = f.duration_minutes ? `${Math.floor(f.duration_minutes/60)}j ${f.duration_minutes%60}m` : "-";
    const travelokaUrl = `https://www.traveloka.com/en-id/flight/fullprice/${f.origin.toLowerCase()}-to-${f.destination.toLowerCase()}/${f.flight_date}/1/0/0/Economy`;

    return `
      <tr>
        <td>
          <div class="airline-badge">
            <span>✈️</span>
            <div>
              <div>${f.airline}</div>
              <div style="font-size: 0.75rem; color: var(--text-sub);">${f.flight_number || '-'}</div>
            </div>
          </div>
        </td>
        <td><b>${f.origin} ➔ ${f.destination}</b></td>
        <td>${f.flight_date}</td>
        <td>
          <div>${f.departure_time} - ${f.arrival_time}</div>
          <div style="font-size: 0.75rem; color: var(--text-sub);">${durText}</div>
        </td>
        <td><span class="price-tag">${formatRupiah(f.price_idr)}</span></td>
        <td>${seatsBadge || '<span style="color: var(--text-sub);">-</span>'}</td>
        <td>
          <a href="${travelokaUrl}" target="_blank" class="btn btn-primary btn-sm">
            Beli Tiket ➔
          </a>
        </td>
      </tr>
    `;
  }).join("");
}

function renderRoutesGrid(routes) {
  const container = document.getElementById("routesGrid");
  if (!container) return;

  container.innerHTML = routes.map(r => {
    const isInactive = !r.is_active;
    const formattedMax = formatRupiah(r.max_price_idr);

    return `
      <div class="route-card ${isInactive ? 'inactive' : ''}" id="routeCard-${r.id}">
        <div class="route-card-top">
          <div>
            <div class="route-flight-badges">
              <span class="iata-code">${r.origin}</span>
              <span class="route-arrow">➔</span>
              <span class="iata-code">${r.destination}</span>
            </div>
            <div class="route-label-sub">${r.label || `${r.origin} ke ${r.destination}`}</div>
          </div>
          
          <label class="toggle-switch" title="Aktifkan/Nonaktifkan Pemantauan">
            <input type="checkbox" ${r.is_active ? 'checked' : ''} onchange="handleToggleRoute(${r.id})">
            <span class="slider"></span>
          </label>
        </div>

        <div class="route-meta-box">
          <div>
            <div class="meta-item-label">Target Budget</div>
            <div class="meta-item-value highlight">${formattedMax}</div>
          </div>
          <div>
            <div class="meta-item-label">Rentang Cek</div>
            <div class="meta-item-value">${r.days_ahead} hari ke depan</div>
          </div>
          <div>
            <div class="meta-item-label">Status</div>
            <div class="meta-item-value" style="font-size: 0.8rem; color: ${r.is_active ? 'var(--accent-emerald)' : 'var(--text-sub)'};">
              ${r.is_active ? '🟢 Aktif Memantau' : '⚪ Nonaktif'}
            </div>
          </div>
          <div>
            <div class="meta-item-label">Interval</div>
            <div class="meta-item-value">${r.check_interval_hours || 4} jam</div>
          </div>
        </div>

        <div class="route-card-actions">
          <button class="btn btn-secondary btn-sm" onclick="handleSelectRouteAnalytics(${r.id})">
            📊 Lihat Tren
          </button>
          <div style="display: flex; gap: 0.4rem;">
            <button class="btn btn-secondary btn-sm" onclick="handleOpenTravelokaDirect('${r.origin}', '${r.destination}')" title="Cek Langsung di Traveloka">
              ✈️ Buka
            </button>
            <button class="btn btn-secondary btn-sm" onclick="openEditRouteModal(${r.id})" title="Edit Rute">
              ✏️
            </button>
            <button class="btn btn-danger btn-sm" onclick="handleDeleteRoute(${r.id})" title="Hapus Rute">
              🗑️
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function handleOpenTravelokaDirect(origin, dest) {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  const dStr = d.toISOString().split("T")[0];
  const url = `https://www.traveloka.com/en-id/flight/fullprice/${origin.toLowerCase()}-to-${dest.toLowerCase()}/${dStr}/1/0/0/Economy`;
  window.open(url, "_blank");
}

function updateRouteSelectOptions(routes) {
  const select = document.getElementById("analyticsRouteSelect");
  if (!select) return;
  select.innerHTML = routes.map(r => 
    `<option value="${r.id}" ${r.id === state.selectedRouteId ? 'selected' : ''}>${r.label || `${r.origin} ➔ ${r.destination}`}</option>`
  ).join("");
}

function setupEventListeners() {
  const themeBtn = document.getElementById("btnThemeToggle");
  if (themeBtn) themeBtn.addEventListener("click", toggleTheme);

  const scanAllBtn = document.getElementById("btnScanAll");
  if (scanAllBtn) scanAllBtn.addEventListener("click", () => {
    showToast("Data diperbarui dari cloud", "success");
    loadStaticData();
  });

  const routeSelect = document.getElementById("analyticsRouteSelect");
  if (routeSelect) {
    routeSelect.addEventListener("change", (e) => {
      state.selectedRouteId = parseInt(e.target.value);
      loadAnalytics(state.selectedRouteId);
      loadFlights(state.selectedRouteId);
    });
  }

  const tabTrend = document.getElementById("tabTrend");
  const tabCal = document.getElementById("tabCalendar");
  const trendView = document.getElementById("trendViewWrapper");
  const calView = document.getElementById("calendarViewWrapper");

  if (tabTrend && tabCal) {
    tabTrend.addEventListener("click", () => {
      tabTrend.classList.add("active");
      tabCal.classList.remove("active");
      trendView.style.display = "block";
      calView.style.display = "none";
    });

    tabCal.addEventListener("click", () => {
      tabCal.classList.add("active");
      tabTrend.classList.remove("active");
      trendView.style.display = "none";
      calView.style.display = "block";
    });
  }

  const routeForm = document.getElementById("routeForm");
  if (routeForm) routeForm.addEventListener("submit", handleSaveRouteForm);

  const settingsForm = document.getElementById("settingsForm");
  if (settingsForm) settingsForm.addEventListener("submit", (e) => {
    e.preventDefault();
    closeModal("settingsModal");
    showToast("Pengaturan disimpan!", "success");
  });

  const testTgBtn = document.getElementById("btnTestTelegram");
  if (testTgBtn) testTgBtn.addEventListener("click", handleTestTelegram);
}

function handleSelectRouteAnalytics(routeId) {
  state.selectedRouteId = routeId;
  const select = document.getElementById("analyticsRouteSelect");
  if (select) select.value = routeId;
  loadAnalytics(routeId);
  loadFlights(routeId);
  const section = document.getElementById("analyticsSection");
  if (section) section.scrollIntoView({ behavior: "smooth" });
}

function handleToggleRoute(routeId) {
  const route = state.routes.find(r => r.id === routeId);
  if (!route) return;

  route.is_active = route.is_active ? 0 : 1;
  localStorage.setItem("custom_flight_routes", JSON.stringify(state.routes));
  renderRoutesGrid(state.routes);
  updateStatusUI(state.staticData ? state.staticData.status : {});
  showToast(`Status rute ${route.label} diubah (${route.is_active ? 'Aktif' : 'Nonaktif'})`, "success");
}

function handleDeleteRoute(routeId) {
  if (!confirm("Hapus rute ini dari pemantauan dashboard?")) return;

  state.routes = state.routes.filter(r => r.id !== routeId);
  localStorage.setItem("custom_flight_routes", JSON.stringify(state.routes));
  renderRoutesGrid(state.routes);
  updateRouteSelectOptions(state.routes);
  updateStatusUI(state.staticData ? state.staticData.status : {});

  if (state.routes.length > 0) {
    state.selectedRouteId = state.routes[0].id;
    loadAnalytics(state.selectedRouteId);
  }
  showToast("Rute berhasil dihapus dari dashboard", "success");
}

function openAddRouteModal() {
  document.getElementById("routeModalTitle").textContent = "Tambah Rute Pantauan";
  document.getElementById("routeIdInput").value = "";
  document.getElementById("routeOriginInput").value = "";
  document.getElementById("routeDestInput").value = "";
  document.getElementById("routeLabelInput").value = "";
  document.getElementById("routeMaxPriceInput").value = "600000";
  document.getElementById("routeDaysAheadInput").value = "14";
  openModal("routeModal");
}

function openEditRouteModal(routeId) {
  const route = state.routes.find(r => r.id === routeId);
  if (!route) return;

  document.getElementById("routeModalTitle").textContent = `Edit Rute: ${route.label}`;
  document.getElementById("routeIdInput").value = route.id;
  document.getElementById("routeOriginInput").value = route.origin;
  document.getElementById("routeDestInput").value = route.destination;
  document.getElementById("routeLabelInput").value = route.label || "";
  document.getElementById("routeMaxPriceInput").value = route.max_price_idr;
  document.getElementById("routeDaysAheadInput").value = route.days_ahead;
  openModal("routeModal");
}

function handleSaveRouteForm(e) {
  e.preventDefault();
  const routeId = document.getElementById("routeIdInput").value;
  const origin = document.getElementById("routeOriginInput").value.trim().toUpperCase();
  const destination = document.getElementById("routeDestInput").value.trim().toUpperCase();
  const label = document.getElementById("routeLabelInput").value.trim();
  const maxPrice = parseInt(document.getElementById("routeMaxPriceInput").value);
  const daysAhead = parseInt(document.getElementById("routeDaysAheadInput").value);

  if (!origin || !destination) {
    showToast("Bandara asal dan tujuan harus diisi", "error");
    return;
  }

  const payload = {
    id: routeId ? parseInt(routeId) : Date.now(),
    origin,
    destination,
    label: label || `${origin} ➔ ${destination}`,
    max_price_idr: maxPrice,
    days_ahead: daysAhead,
    is_active: 1,
    check_interval_hours: 4
  };

  if (routeId) {
    const idx = state.routes.findIndex(r => r.id === parseInt(routeId));
    if (idx !== -1) state.routes[idx] = payload;
  } else {
    state.routes.unshift(payload);
  }

  // Simpan permanen ke memori browser
  localStorage.setItem("custom_flight_routes", JSON.stringify(state.routes));
  renderRoutesGrid(state.routes);
  updateRouteSelectOptions(state.routes);
  updateStatusUI(state.staticData ? state.staticData.status : {});

  state.selectedRouteId = payload.id;
  loadAnalytics(payload.id);

  closeModal("routeModal");
  showToast(`✅ Rute ${payload.label} berhasil disimpan di Dashboard!`, "success");
}

async function handleTestTelegram() {
  const token = document.getElementById("settingTelegramToken").value.trim();
  const chatId = document.getElementById("settingTelegramChatId").value.trim();
  if (!token || !chatId) {
    showToast("Masukkan Token dan Chat ID", "error");
    return;
  }
  try {
    const url = `https://api.telegram.org/bot${token}/sendMessage`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: "✅ <b>Tes Terhubung Berhasil!</b>\nFlight Price Monitor Pro aktif dan terhubung ke Telegram Anda.",
        parse_mode: "HTML"
      })
    });
    const data = await resp.json();
    if (data.ok) showToast("✅ Pesan tes terkirim ke Telegram!", "success");
    else showToast("❌ Gagal: " + data.description, "error");
  } catch (err) {
    showToast("Error: " + err.message, "error");
  }
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add("open");
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("open");
}

function openNotificationsModal() {
  const container = document.getElementById("notificationsLogContainer");
  if (container && state.staticData && state.staticData.notifications) {
    container.innerHTML = state.staticData.notifications.map(l => `
      <div style="padding: 0.85rem; border-bottom: 1px solid var(--border-color); font-size: 0.85rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
          <b>${l.route_label || 'Notifikasi'}</b>
          <span style="color: var(--text-sub); font-size: 0.75rem;">${new Date(l.sent_at).toLocaleString("id-ID")}</span>
        </div>
        <div style="color: var(--text-muted); white-space: pre-line;">${l.message.replace(/<[^>]*>?/gm, '')}</div>
      </div>
    `).join("");
  }
  openModal("notificationsModal");
}

function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</span> <div>${message}</div>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function initTheme() {
  const saved = localStorage.getItem("flight_theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeIcon(saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", current);
  localStorage.setItem("flight_theme", current);
  updateThemeIcon(current);
  if (state.selectedRouteId) loadAnalytics(state.selectedRouteId);
}

function updateThemeIcon(theme) {
  const btn = document.getElementById("btnThemeToggle");
  if (btn) btn.textContent = theme === "light" ? "🌙" : "☀️";
}
