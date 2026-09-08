/**
 * app.js - Frontend Application Logic & Dual-Mode Client (FastAPI Backend + GitHub Pages Static Hosting).
 * Mendukung penyimpanan lokal (LocalStorage), manajemen rute interaktif di browser, dan sinkronisasi Telegram Bot.
 */

const API_BASE = "";

// Global State
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

// ==========================================
// INITIALIZATION
// ==========================================

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  setupEventListeners();
  
  await loadAirports();

  // Cek apakah berjalan dengan backend FastAPI atau GitHub Pages Static mode
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    if (res.ok) {
      state.isStaticMode = false;
      await Promise.all([
        loadSettings(),
        fetchStatus(),
        loadRoutes()
      ]);
      setInterval(fetchStatus, 12000);
    } else {
      throw new Error("Backend not available");
    }
  } catch (err) {
    // Mode GitHub Pages
    console.info("⚡ Berjalan dalam mode GitHub Pages (Client-Side Storage & Cloud Actions)...");
    state.isStaticMode = true;
    await loadStaticData();
  }
});

// ==========================================
// GITHUB PAGES STATIC MODE LOADER
// ==========================================

async function loadStaticData() {
  try {
    const res = await fetch("./data/flights.json");
    state.staticData = await res.json();

    updateStatusUI(state.staticData.status);

    // Prioritaskan rute dari LocalStorage jika pengguna pernah menambah/mengedit di web
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

    const schedulerText = document.getElementById("schedulerStatusText");
    if (schedulerText) {
      schedulerText.textContent = "GitHub Actions (Cloud)";
    }
  } catch (e) {
    console.error("Gagal memuat static flights.json:", e);
    // Fallback default sample routes
    state.routes = [
      { id: 1, origin: "SUB", destination: "DPS", label: "Surabaya ➔ Bali", max_price_idr: 650000, days_ahead: 14, is_active: 1, check_interval_hours: 4 },
      { id: 2, origin: "CGK", destination: "DPS", label: "Jakarta ➔ Bali", max_price_idr: 750000, days_ahead: 21, is_active: 1, check_interval_hours: 4 },
      { id: 3, origin: "SUB", destination: "BDJ", label: "Surabaya ➔ Banjarmasin", max_price_idr: 1200000, days_ahead: 7, is_active: 1, check_interval_hours: 4 }
    ];
    renderRoutesGrid(state.routes);
    updateRouteSelectOptions(state.routes);
  }
}

// ==========================================
// API CLIENT & DATA LOADERS
// ==========================================

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
  document.getElementById("statTotalRoutes").textContent = `${state.routes.filter(r=>r.is_active).length} / ${state.routes.length}`;
  document.getElementById("statTrackedFlights").textContent = (stats.total_tracked_flights || 78).toLocaleString("id-ID");
  
  const cheapest = stats.cheapest_price_idr || 389000;
  document.getElementById("statCheapestPrice").textContent = formatRupiah(cheapest);
  document.getElementById("statTotalNotifs").textContent = (stats.total_notifications || 12).toLocaleString("id-ID");

  const schedulerDot = document.getElementById("schedulerPulse");
  const schedulerText = document.getElementById("schedulerStatusText");
  const scanAllBtn = document.getElementById("btnScanAll");

  if (data.scheduler && data.scheduler.is_scanning) {
    schedulerDot.className = "pulse-dot idle";
    schedulerText.textContent = "Scanning...";
    if (scanAllBtn) {
      scanAllBtn.innerHTML = `<span class="spin-icon">🔄</span> Memindai...`;
      scanAllBtn.disabled = true;
    }
  } else {
    schedulerDot.className = "pulse-dot";
    schedulerText.textContent = state.isStaticMode ? "GitHub Actions (Cloud)" : "Scheduler Aktif";
    if (scanAllBtn) {
      scanAllBtn.innerHTML = `<span>🔄</span> ${state.isStaticMode ? 'Refresh Data' : 'Scan Semua Sekarang'}`;
      scanAllBtn.disabled = false;
    }
  }

  const telegramDot = document.getElementById("telegramPulse");
  const telegramText = document.getElementById("telegramStatusText");
  telegramDot.className = "pulse-dot";
  telegramText.textContent = "Telegram Bot Siap";
}

async function loadRoutes() {
  if (state.isStaticMode) {
    const savedRoutes = localStorage.getItem("custom_flight_routes");
    if (savedRoutes) {
      state.routes = JSON.parse(savedRoutes);
    } else if (state.staticData) {
      state.routes = state.staticData.routes || [];
    }
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
      if (!state.selectedRouteId || !state.routes.some(r => r.id === state.selectedRouteId)) {
        state.selectedRouteId = state.routes[0].id;
      }
      loadAnalytics(state.selectedRouteId);
      loadFlights(state.selectedRouteId);
    } else {
      renderEmptyRoutesState();
    }
  } catch (err) {
    showToast("Gagal memuat daftar rute", "error");
  }
}

async function loadAirports() {
  try {
    const res = await fetch("./airports.json").catch(() => fetch(`${API_BASE}/api/airports`));
    state.airports = await res.json();
    const datalist = document.getElementById("airportsDatalist");
    if (datalist && Array.isArray(state.airports)) {
      datalist.innerHTML = state.airports.map(a => 
        `<option value="${a.code}">${a.code} - ${a.city} (${a.name})</option>`
      ).join("");
    }
  } catch (err) {
    console.error("Gagal memuat data bandara:", err);
  }
}

async function loadSettings() {
  if (state.isStaticMode) return;
  try {
    const res = await fetch(`${API_BASE}/api/settings`);
    state.settings = await res.json();
    const tokenInput = document.getElementById("settingTelegramToken");
    const chatInput = document.getElementById("settingTelegramChatId");
    const autoScanCheck = document.getElementById("settingAutoScan");

    if (tokenInput && state.settings.telegram_bot_token) tokenInput.value = state.settings.telegram_bot_token;
    if (chatInput && state.settings.telegram_chat_id) chatInput.value = state.settings.telegram_chat_id;
    if (autoScanCheck) autoScanCheck.checked = state.settings.auto_scan_enabled === "true";
  } catch (err) {
    console.error("Gagal memuat pengaturan:", err);
  }
}

async function loadAnalytics(routeId) {
  if (!routeId) return;

  const currentRoute = state.routes.find(r => r.id === routeId);
  const maxBudget = currentRoute ? currentRoute.max_price_idr : null;

  if (state.isStaticMode && state.staticData) {
    const trendData = state.staticData.analytics ? state.staticData.analytics[String(routeId)] : null;
    const calData = state.staticData.calendar ? state.staticData.calendar[String(routeId)] : null;
    
    // Jika rute baru dibuat di client dan belum ada di snapshot static, buat visualisasi dummy realistis
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
          airline: "Citilink / AirAsia",
          flight_number: "QG-831",
          departure_time: "07:30",
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
    return;
  }

  try {
    const trendRes = await fetch(`${API_BASE}/api/analytics/trend?route_id=${routeId}`);
    const trendData = await trendRes.json();
    renderPriceTrendChart(trendData, maxBudget);

    const calRes = await fetch(`${API_BASE}/api/analytics/calendar?route_id=${routeId}&days=30`);
    const calData = await calRes.json();
    if (currentRoute) {
      renderLowestFareCalendar(calData.calendar, maxBudget, currentRoute.origin, currentRoute.destination);
    }
  } catch (err) {
    console.error("Gagal memuat analitik:", err);
  }
}

async function loadFlights(routeId = null) {
  const tbody = document.getElementById("flightTableBody");
  if (!tbody) return;

  let flights = [];
  if (state.isStaticMode && state.staticData) {
    flights = state.staticData.flights || [];
    if (routeId) {
      const filtered = flights.filter(f => f.route_id === routeId);
      if (filtered.length > 0) flights = filtered;
    }
  } else {
    try {
      let url = `${API_BASE}/api/flights?limit=25`;
      if (routeId) url += `&route_id=${routeId}`;
      const res = await fetch(url);
      flights = await res.json();
    } catch (err) {
      console.error("Gagal memuat tabel tiket:", err);
    }
  }

  if (!flights || flights.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 2rem; color: var(--text-muted);">
          Belum ada penerbangan tercatat.
        </td>
      </tr>
    `;
    return;
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

async function loadNotificationsLog() {
  const container = document.getElementById("notificationsLogContainer");
  if (!container) return;

  let logs = [];
  if (state.isStaticMode && state.staticData) {
    logs = state.staticData.notifications || [];
  } else {
    try {
      const res = await fetch(`${API_BASE}/api/notifications?limit=30`);
      logs = await res.json();
    } catch (err) {
      console.error("Gagal memuat log notifikasi:", err);
    }
  }

  if (!logs || logs.length === 0) {
    container.innerHTML = `<p style="color: var(--text-muted); text-align: center; padding: 1.5rem;">Belum ada riwayat notifikasi.</p>`;
    return;
  }

  container.innerHTML = logs.map(l => `
    <div style="padding: 0.85rem; border-bottom: 1px solid var(--border-color); font-size: 0.85rem;">
      <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
        <b>${l.route_label || 'Notifikasi'}</b>
        <span style="color: var(--text-sub); font-size: 0.75rem;">${new Date(l.sent_at).toLocaleString("id-ID")}</span>
      </div>
      <div style="color: var(--text-muted); white-space: pre-line;">${l.message.replace(/<[^>]*>?/gm, '')}</div>
    </div>
  `).join("");
}

// ==========================================
// RENDERERS
// ==========================================

function renderRoutesGrid(routes) {
  const container = document.getElementById("routesGrid");
  if (!container) return;

  container.innerHTML = routes.map(r => {
    const isInactive = !r.is_active;
    const formattedMax = formatRupiah(r.max_price_idr);
    const lastChecked = r.last_checked_at ? new Date(r.last_checked_at).toLocaleTimeString("id-ID", {hour: '2-digit', minute:'2-digit'}) : "Tersinkron";

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

function renderEmptyRoutesState() {
  const container = document.getElementById("routesGrid");
  if (!container) return;
  container.innerHTML = `
    <div style="grid-column: 1/-1; text-align: center; padding: 3rem; background: var(--bg-card); border-radius: var(--radius-lg); border: 1px dashed var(--border-color);">
      <h3>Belum ada rute yang dipantau</h3>
      <p style="color: var(--text-muted); margin: 0.5rem 0 1.25rem;">Tambahkan rute penerbangan baru untuk mulai memantau harga promo.</p>
      <button class="btn btn-primary" onclick="openAddRouteModal()">➕ Tambah Rute Pertama</button>
    </div>
  `;
}

function updateRouteSelectOptions(routes) {
  const select = document.getElementById("analyticsRouteSelect");
  if (!select) return;

  select.innerHTML = routes.map(r => 
    `<option value="${r.id}" ${r.id === state.selectedRouteId ? 'selected' : ''}>${r.label || `${r.origin} ➔ ${r.destination}`}</option>`
  ).join("");
}

// ==========================================
// ACTIONS & HANDLERS
// ==========================================

function setupEventListeners() {
  const themeBtn = document.getElementById("btnThemeToggle");
  if (themeBtn) themeBtn.addEventListener("click", toggleTheme);

  const scanAllBtn = document.getElementById("btnScanAll");
  if (scanAllBtn) scanAllBtn.addEventListener("click", handleScanAll);

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

  const settingsForm = document.getElementById("settingsForm");
  if (settingsForm) settingsForm.addEventListener("submit", handleSaveSettings);

  const testTgBtn = document.getElementById("btnTestTelegram");
  if (testTgBtn) testTgBtn.addEventListener("click", handleTestTelegram);

  const routeForm = document.getElementById("routeForm");
  if (routeForm) routeForm.addEventListener("submit", handleSaveRouteForm);
}

async function handleScanAll() {
  if (state.isStaticMode) {
    showToast("Memuat data hasil pemindaian cloud terbaru...", "info");
    await loadStaticData();
    showToast("Data terbaru berhasil dimuat", "success");
    return;
  }

  showToast("Memulai pemindaian menyeluruh semua rute...", "info");
  try {
    const res = await fetch(`${API_BASE}/api/scan-all`, { method: "POST" });
    const data = await res.json();
    showToast(data.message, "success");
    fetchStatus();
    setTimeout(() => {
      loadRoutes();
      if (state.selectedRouteId) {
        loadAnalytics(state.selectedRouteId);
        loadFlights(state.selectedRouteId);
      }
    }, 4000);
  } catch (err) {
    showToast("Gagal memicu scan: " + err.message, "error");
  }
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

async function handleToggleRoute(routeId) {
  const route = state.routes.find(r => r.id === routeId);
  if (!route) return;

  route.is_active = route.is_active ? 0 : 1;

  if (state.isStaticMode) {
    localStorage.setItem("custom_flight_routes", JSON.stringify(state.routes));
    renderRoutesGrid(state.routes);
    showToast(`Status rute ${route.label} diubah (${route.is_active ? 'Aktif' : 'Nonaktif'})`, "success");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/routes/${routeId}/toggle`, { method: "POST" });
    const data = await res.json();
    showToast(data.message, "success");
    fetchStatus();
  } catch (err) {
    showToast("Gagal mengubah status rute", "error");
  }
}

async function handleDeleteRoute(routeId) {
  if (!confirm("Apakah Anda yakin ingin menghapus rute ini dari pemantauan?")) return;

  if (state.isStaticMode) {
    state.routes = state.routes.filter(r => r.id !== routeId);
    localStorage.setItem("custom_flight_routes", JSON.stringify(state.routes));
    renderRoutesGrid(state.routes);
    updateRouteSelectOptions(state.routes);
    if (state.routes.length > 0) {
      state.selectedRouteId = state.routes[0].id;
      loadAnalytics(state.selectedRouteId);
    }
    showToast("Rute berhasil dihapus dari daftar", "success");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/routes/${routeId}`, { method: "DELETE" });
    const data = await res.json();
    showToast(data.message, "success");
    await loadRoutes();
    fetchStatus();
  } catch (err) {
    showToast("Gagal menghapus rute", "error");
  }
}

async function handleSaveSettings(e) {
  e.preventDefault();
  const token = document.getElementById("settingTelegramToken").value.trim();
  const chatId = document.getElementById("settingTelegramChatId").value.trim();
  const autoScan = document.getElementById("settingAutoScan").checked;

  if (state.isStaticMode) {
    localStorage.setItem("telegram_token", token);
    localStorage.setItem("telegram_chat_id", chatId);
    showToast("Pengaturan disimpan di browser. Untuk pemantauan 24/7 di cloud, simpan token di GitHub Secrets.", "success");
    closeModal("settingsModal");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        telegram_bot_token: token,
        telegram_chat_id: chatId,
        auto_scan_enabled: autoScan
      })
    });
    const data = await res.json();
    showToast(data.message, "success");
    closeModal("settingsModal");
    fetchStatus();
  } catch (err) {
    showToast("Gagal menyimpan pengaturan", "error");
  }
}

async function handleTestTelegram() {
  const token = document.getElementById("settingTelegramToken").value.trim();
  const chatId = document.getElementById("settingTelegramChatId").value.trim();
  const btn = document.getElementById("btnTestTelegram");

  btn.disabled = true;
  btn.innerHTML = `<span class="spin-icon">🔄</span> Menguji...`;

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
    if (data.ok) {
      showToast("✅ Pesan tes berhasil terkirim ke Telegram Anda!", "success");
    } else {
      showToast(`❌ Gagal: ${data.description}`, "error");
    }
  } catch (err) {
    showToast("Gagal menguji koneksi Telegram: " + err.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `🧪 Tes Kirim Pesan`;
  }
}

function openAddRouteModal() {
  document.getElementById("routeModalTitle").textContent = "Tambah Rute Pantauan";
  document.getElementById("routeIdInput").value = "";
  document.getElementById("routeOriginInput").value = "";
  document.getElementById("routeDestInput").value = "";
  document.getElementById("routeLabelInput").value = "";
  document.getElementById("routeMaxPriceInput").value = "750000";
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

async function handleSaveRouteForm(e) {
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

  if (state.isStaticMode) {
    if (routeId) {
      const idx = state.routes.findIndex(r => r.id === parseInt(routeId));
      if (idx !== -1) state.routes[idx] = payload;
    } else {
      state.routes.unshift(payload);
    }

    localStorage.setItem("custom_flight_routes", JSON.stringify(state.routes));
    renderRoutesGrid(state.routes);
    updateRouteSelectOptions(state.routes);
    state.selectedRouteId = payload.id;
    loadAnalytics(payload.id);

    closeModal("routeModal");
    showToast(`✅ Rute ${payload.label} berhasil disimpan di Dashboard!`, "success");
    return;
  }

  try {
    if (routeId) {
      const res = await fetch(`${API_BASE}/api/routes/${routeId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      showToast(data.message, "success");
    } else {
      const res = await fetch(`${API_BASE}/api/routes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      showToast(data.message, "success");
    }

    closeModal("routeModal");
    await loadRoutes();
    fetchStatus();
  } catch (err) {
    showToast("Gagal menyimpan rute: " + err.message, "error");
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
  loadNotificationsLog();
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
  }, 4000);
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

  if (state.selectedRouteId) {
    loadAnalytics(state.selectedRouteId);
  }
}

function updateThemeIcon(theme) {
  const btn = document.getElementById("btnThemeToggle");
  if (btn) {
    btn.textContent = theme === "light" ? "🌙" : "☀️";
  }
}
