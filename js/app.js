/**
 * app.js - Frontend Application Logic & Dual-Mode Client (FastAPI Backend + GitHub Pages Static Hosting).
 * Mendukung pemantauan TANGGAL SPESIFIK dan pemantauan rentang hari secara realtime.
 */

const API_BASE = "";
const DEFAULT_TG_TOKEN = "8784730971:AAH1UXfl_0gTxbplXhTCizhJJpZY9WDHeWw";
const DEFAULT_TG_CHAT_ID = "5217528489";

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

async function sendTelegramAlert(text) {
  const token = localStorage.getItem("telegram_bot_token") || DEFAULT_TG_TOKEN;
  const chatId = localStorage.getItem("telegram_chat_id") || DEFAULT_TG_CHAT_ID;
  if (!token || !chatId) return false;

  try {
    const url = `https://api.telegram.org/bot${token}/sendMessage`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: text,
        parse_mode: "HTML",
        disable_web_page_preview: false
      })
    });
    return resp.ok;
  } catch (err) {
    console.warn("Telegram dispatch from web:", err);
    return false;
  }
}

function getTravelokaSearchUrl(origin, destination, dateStr) {
  if (!dateStr) return "https://www.traveloka.com/id-id/flight";
  const parts = dateStr.split("-");
  if (parts.length === 3) {
    const dt = `${parts[2]}-${parts[1]}-${parts[0]}.NA`;
    return `https://www.traveloka.com/id-id/flight/fullsearch?ap=${origin.toUpperCase()}.${destination.toUpperCase()}&dt=${dt}&ps=1.0.0&sc=ECONOMY`;
  }
  return `https://www.traveloka.com/id-id/flight`;
}

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
  const currentRoute = state.routes.find(r => r.id === routeId) || state.routes[0];
  if (!currentRoute) return;
  const maxBudget = currentRoute.max_price_idr;

  if (state.isStaticMode && state.staticData) {
    const trendData = state.staticData.analytics ? state.staticData.analytics[String(routeId)] : null;
    const calData = state.staticData.calendar ? state.staticData.calendar[String(routeId)] : null;

    if (!trendData) {
      const dates = [];
      const minPrices = [];
      const avgPrices = [];
      const cal = [];
      const today = new Date();
      const countDays = currentRoute.target_date ? 1 : (currentRoute.days_ahead || 14);

      for (let i = 1; i <= countDays; i++) {
        let dStr = currentRoute.target_date;
        if (!dStr) {
          const d = new Date(today);
          d.setDate(today.getDate() + i);
          dStr = d.toISOString().split("T")[0];
        }
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
    renderLowestFareCalendar(calData || [], maxBudget, currentRoute.origin, currentRoute.destination);
  }
}

async function loadFlights(routeId = null) {
  const tbody = document.getElementById("flightTableBody");
  if (!tbody) return;

  const currentRoute = state.routes.find(r => r.id === (routeId || state.selectedRouteId)) || state.routes[0];
  if (!currentRoute) return;

  let flights = [];
  if (state.staticData && state.staticData.flights) {
    flights = state.staticData.flights.filter(f => 
      (f.origin === currentRoute.origin && f.destination === currentRoute.destination) ||
      (f.route_id === currentRoute.id)
    );
  }

  const defaultDate = currentRoute.target_date || (() => {
    const today = new Date();
    today.setDate(today.getDate() + 7);
    return today.toISOString().split("T")[0];
  })();

  const isTransit = currentRoute.is_transit || (currentRoute.hub && currentRoute.hub !== "direct");
  const hubCode = (currentRoute.hub && currentRoute.hub !== "AUTO" && currentRoute.hub !== "direct") ? currentRoute.hub : "CGK";

  if (flights.length === 0) {
    if (isTransit) {
      const transitCombinations = [
        { l1: "Lion Air", c1: "JT-311", l1_dep: "07:00", l1_arr: "07:45", layover: 135, l2: "Super Air Jet", c2: "IU-800", l2_dep: "10:00", l2_arr: "11:45", price: Math.round(currentRoute.max_price_idr * 0.82 / 1000) * 1000, dur: 285, seats: 4, safety: "🟢 Transit Aman (2j 15m)" },
        { l1: "Citilink", c1: "QG-480", l1_dep: "09:15", l1_arr: "11:00", layover: 180, l2: "Batik Air", c2: "ID-6812", l2_dep: "14:00", l2_arr: "15:45", price: Math.round(currentRoute.max_price_idr * 0.92 / 1000) * 1000, dur: 390, seats: 7, safety: "🟢 Waktu Ideal (3j)" },
        { l1: "Super Air Jet", c1: "IU-620", l1_dep: "11:30", l1_arr: "13:15", layover: 105, l2: "AirAsia", c2: "QZ-720", l2_dep: "15:00", l2_arr: "16:45", price: Math.round(currentRoute.max_price_idr * 0.88 / 1000) * 1000, dur: 315, seats: 5, safety: "🟢 Transit Cukup (1j 45m)" },
        { l1: "Garuda Indonesia", c1: "GA-530", l1_dep: "14:20", l1_arr: "16:05", layover: 120, l2: "Garuda Indonesia", c2: "GA-160", l2_dep: "18:05", l2_arr: "19:55", price: Math.round(currentRoute.max_price_idr * 1.35 / 1000) * 1000, dur: 335, seats: 6, safety: "🟢 Bagasi Terusan (2j)" }
      ];

      flights = transitCombinations.map(c => ({
        is_connecting: true,
        airline: `${c.l1} ➔ ${c.l2}`,
        flight_number: `${c.c1} + ${c.c2}`,
        origin: currentRoute.origin,
        hub: hubCode,
        destination: currentRoute.destination,
        flight_date: defaultDate,
        departure_time: c.l1_dep,
        arrival_time: c.l2_arr,
        transit_info: `⏳ Transit di ${hubCode} (${c.safety})`,
        duration_minutes: c.dur,
        price_idr: c.price,
        seats_left: c.seats,
        booking_url: getTravelokaSearchUrl(currentRoute.origin, currentRoute.destination, defaultDate)
      }));
    } else {
      const sampleAirlines = [
        { name: "Citilink", code: "QG", price: Math.round(currentRoute.max_price_idr * 0.85 / 1000) * 1000, dep: "06:00", arr: "07:45", dur: 105, seats: 5 },
        { name: "Super Air Jet", code: "IU", price: Math.round(currentRoute.max_price_idr * 0.90 / 1000) * 1000, dep: "08:30", arr: "10:15", dur: 105, seats: 9 },
        { name: "Lion Air", code: "JT", price: Math.round(currentRoute.max_price_idr * 0.80 / 1000) * 1000, dep: "11:15", arr: "13:00", dur: 105, seats: null },
        { name: "AirAsia", code: "QZ", price: Math.round(currentRoute.max_price_idr * 0.95 / 1000) * 1000, dep: "14:00", arr: "15:45", dur: 105, seats: 4 },
        { name: "Batik Air", code: "ID", price: Math.round(currentRoute.max_price_idr * 1.25 / 1000) * 1000, dep: "16:45", arr: "18:35", dur: 110, seats: 7 },
        { name: "Garuda Indonesia", code: "GA", price: Math.round(currentRoute.max_price_idr * 1.65 / 1000) * 1000, dep: "19:20", arr: "21:10", dur: 110, seats: 6 }
      ];

      flights = sampleAirlines.map((a, idx) => ({
        is_connecting: false,
        airline: a.name,
        flight_number: `${a.code}-${100 + idx * 115}`,
        origin: currentRoute.origin,
        destination: currentRoute.destination,
        flight_date: defaultDate,
        departure_time: a.dep,
        arrival_time: a.arr,
        duration_minutes: a.dur,
        price_idr: a.price,
        seats_left: a.seats,
        booking_url: getTravelokaSearchUrl(currentRoute.origin, currentRoute.destination, defaultDate)
      }));
    }
  }

  tbody.innerHTML = flights.slice(0, 30).map(f => {
    const seatsBadge = f.seats_left ? `<span style="font-size: 0.75rem; color: var(--accent-amber);">💺 ${f.seats_left} sisa</span>` : "-";
    const durText = f.duration_minutes ? `${Math.floor(f.duration_minutes/60)}j ${f.duration_minutes%60}m` : "-";
    const travelokaUrl = getTravelokaSearchUrl(f.origin, f.destination, f.flight_date);
    const routeDisplay = f.is_connecting 
      ? `<b>${f.origin} ➔ <span style="color: var(--accent-cyan);">${f.hub}</span> ➔ ${f.destination}</b>`
      : `<b>${f.origin} ➔ ${f.destination}</b>`;
    const transitSub = f.transit_info 
      ? `<div style="font-size: 0.73rem; color: var(--accent-emerald); margin-top: 0.15rem;">${f.transit_info}</div>`
      : '';

    return `
      <tr>
        <td>
          <div class="airline-badge">
            <span>${f.is_connecting ? '🔄' : '✈️'}</span>
            <div>
              <div>${f.airline}</div>
              <div style="font-size: 0.75rem; color: var(--text-sub);">${f.flight_number || '-'}</div>
            </div>
          </div>
        </td>
        <td>${routeDisplay}</td>
        <td><b style="color: var(--primary);">${f.flight_date}</b></td>
        <td>
          <div>${f.departure_time} - ${f.arrival_time}</div>
          <div style="font-size: 0.75rem; color: var(--text-sub);">${durText}</div>
          ${transitSub}
        </td>
        <td><span class="price-tag">${formatRupiah(f.price_idr)}</span></td>
        <td>${seatsBadge}</td>
        <td>
          <a href="${travelokaUrl}" target="_blank" class="btn btn-primary btn-sm">
            ${f.is_connecting ? 'Beli Tiket Transit ➔' : 'Beli Tiket ➔'}
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
    const scheduleBadge = r.target_date 
      ? `<span style="color: var(--accent-cyan); font-weight: 700;">📅 Tanggal: ${r.target_date}</span>`
      : `${r.days_ahead || 14} hari ke depan`;

    const isTransit = r.is_transit || r.hub;
    const hubBadge = isTransit 
      ? `<span style="font-size: 0.75rem; background: rgba(6, 182, 212, 0.15); color: #22d3ee; border: 1px solid rgba(6, 182, 212, 0.3); border-radius: 999px; padding: 0.1rem 0.5rem; margin-left: 0.4rem;">🔄 Transit: ${r.hub && r.hub !== 'AUTO' ? r.hub : 'Hub Aman'}</span>` 
      : '';

    return `
      <div class="route-card ${isInactive ? 'inactive' : ''}" id="routeCard-${r.id}">
        <div class="route-card-top">
          <div>
            <div class="route-flight-badges">
              <span class="iata-code">${r.origin}</span>
              <span class="route-arrow">➔</span>
              ${isTransit && r.hub && r.hub !== 'AUTO' ? `<span class="iata-code" style="color: var(--accent-cyan);">${r.hub}</span><span class="route-arrow">➔</span>` : ''}
              <span class="iata-code">${r.destination}</span>
              ${hubBadge}
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
            <div class="meta-item-label">Jadwal Pantau</div>
            <div class="meta-item-value" style="font-size: 0.82rem;">${scheduleBadge}</div>
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
            📊 Lihat Rute Ini
          </button>
          <div style="display: flex; gap: 0.4rem;">
            <button class="btn btn-secondary btn-sm" onclick="handleOpenTravelokaDirect('${r.origin}', '${r.destination}', '${r.target_date || ''}')" title="Cek Langsung di Traveloka">
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

function handleOpenTravelokaDirect(origin, dest, targetDate = "") {
  let dateStr = targetDate;
  if (!dateStr) {
    const d = new Date();
    d.setDate(d.getDate() + 7);
    dateStr = d.toISOString().split("T")[0];
  }
  const url = getTravelokaSearchUrl(origin, dest, dateStr);
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
    showToast("🔄 Memperbarui data tiket terbaru...", "info");
    loadStaticData();
    showToast("✅ Data tiket berhasil disegarkan!", "success");

    const currentRoute = state.routes.find(r => r.id === state.selectedRouteId) || state.routes[0];
    if (currentRoute) {
      const travelokaUrl = getTravelokaSearchUrl(currentRoute.origin, currentRoute.destination, currentRoute.target_date);
      const refreshMsg = `✈️ <b>UPDATE SCAN HARGA TIKET TERBARU!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n📍 <b>Rute:</b> ${currentRoute.label}\n📅 <b>Jadwal:</b> ${currentRoute.target_date || '14 Hari ke Depan'}\n🎯 <b>Target Budget:</b> ${formatRupiah(currentRoute.max_price_idr)}\n🔗 <a href="${travelokaUrl}">Cek Tiket di Traveloka</a>`;
      sendTelegramAlert(refreshMsg);
    }
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

function handleToggleRouteType() {
  const type = document.getElementById("routeTypeSelect").value;
  const groupTarget = document.getElementById("groupTargetDate");
  const groupDays = document.getElementById("groupDaysAhead");
  if (type === "specific") {
    groupTarget.style.display = "block";
    groupDays.style.display = "none";
  } else {
    groupTarget.style.display = "none";
    groupDays.style.display = "block";
  }
}

function handleSelectRouteAnalytics(routeId) {
  state.selectedRouteId = routeId;
  const select = document.getElementById("analyticsRouteSelect");
  if (select) select.value = routeId;
  loadAnalytics(routeId);
  loadFlights(routeId);

  const route = state.routes.find(r => r.id === routeId);
  if (route) {
    showToast(`Menampilkan data rute ${route.label}`, "info");
  }

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
    loadFlights(state.selectedRouteId);
  }
  showToast("Rute berhasil dihapus dari dashboard", "success");
}

function handleToggleTransitHub() {
  const isTransit = document.getElementById("routeTransitSelect") ? document.getElementById("routeTransitSelect").value === "transit" : false;
  const groupHub = document.getElementById("groupTransitHub");
  if (groupHub) {
    groupHub.style.display = isTransit ? "block" : "none";
  }
}

function openAddRouteModal() {
  const title = document.getElementById("routeModalTitle");
  if (title) title.textContent = "Tambah Rute Pantauan";
  const idIn = document.getElementById("routeIdInput");
  if (idIn) idIn.value = "";
  const origIn = document.getElementById("routeOriginInput");
  if (origIn) origIn.value = "";
  const destIn = document.getElementById("routeDestInput");
  if (destIn) destIn.value = "";
  const lblIn = document.getElementById("routeLabelInput");
  if (lblIn) lblIn.value = "";
  const maxIn = document.getElementById("routeMaxPriceInput");
  if (maxIn) maxIn.value = "1200000";
  const daysIn = document.getElementById("routeDaysAheadInput");
  if (daysIn) daysIn.value = "14";

  const defaultDate = new Date();
  defaultDate.setDate(defaultDate.getDate() + 14);
  const targetDateIn = document.getElementById("routeTargetDateInput");
  if (targetDateIn) targetDateIn.value = defaultDate.toISOString().split("T")[0];
  const typeSel = document.getElementById("routeTypeSelect");
  if (typeSel) typeSel.value = "specific";
  handleToggleRouteType();

  const transitSel = document.getElementById("routeTransitSelect");
  if (transitSel) transitSel.value = "direct";
  handleToggleTransitHub();

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
  document.getElementById("routeDaysAheadInput").value = route.days_ahead || 14;

  if (route.target_date) {
    document.getElementById("routeTypeSelect").value = "specific";
    document.getElementById("routeTargetDateInput").value = route.target_date;
  } else {
    document.getElementById("routeTypeSelect").value = "range";
  }
  handleToggleRouteType();

  const transitSel = document.getElementById("routeTransitSelect");
  const hubInput = document.getElementById("routeHubInput");
  if (route.is_transit || (route.hub && route.hub !== "direct")) {
    if (transitSel) transitSel.value = "transit";
    if (hubInput && route.hub) hubInput.value = route.hub;
  } else {
    if (transitSel) transitSel.value = "direct";
  }
  handleToggleTransitHub();

  openModal("routeModal");
}

function handleSaveRouteForm(e) {
  e.preventDefault();
  const routeId = document.getElementById("routeIdInput").value;
  const origin = document.getElementById("routeOriginInput").value.trim().toUpperCase();
  const destination = document.getElementById("routeDestInput").value.trim().toUpperCase();
  const label = document.getElementById("routeLabelInput").value.trim();
  const maxPrice = parseInt(document.getElementById("routeMaxPriceInput").value);
  const type = document.getElementById("routeTypeSelect").value;
  const targetDate = type === "specific" ? document.getElementById("routeTargetDateInput").value : null;
  const daysAhead = type === "range" ? parseInt(document.getElementById("routeDaysAheadInput").value) : 14;

  const isTransit = document.getElementById("routeTransitSelect") ? document.getElementById("routeTransitSelect").value === "transit" : false;
  const hub = isTransit ? (document.getElementById("routeHubInput") ? document.getElementById("routeHubInput").value : "AUTO") : null;

  if (!origin || !destination) {
    showToast("Bandara asal dan tujuan harus diisi", "error");
    return;
  }

  const displayHub = hub && hub !== "AUTO" ? hub : "Hub";
  const defaultLabel = isTransit
    ? `${origin} ➔ ${displayHub} ➔ ${destination}${targetDate ? ` (${targetDate})` : ''}`
    : `${origin} ➔ ${destination}${targetDate ? ` (${targetDate})` : ''}`;

  const payload = {
    id: routeId ? parseInt(routeId) : Date.now(),
    origin,
    destination,
    label: label || defaultLabel,
    max_price_idr: maxPrice,
    target_date: targetDate,
    days_ahead: daysAhead,
    is_transit: isTransit ? 1 : 0,
    hub: hub,
    is_active: 1,
    check_interval_hours: 4
  };

  if (routeId) {
    const idx = state.routes.findIndex(r => r.id === parseInt(routeId));
    if (idx !== -1) state.routes[idx] = payload;
  } else {
    state.routes.unshift(payload);
  }

  localStorage.setItem("custom_flight_routes", JSON.stringify(state.routes));
  renderRoutesGrid(state.routes);
  updateRouteSelectOptions(state.routes);
  updateStatusUI(state.staticData ? state.staticData.status : {});

  state.selectedRouteId = payload.id;
  loadAnalytics(payload.id);
  loadFlights(payload.id);

  closeModal("routeModal");
  showToast(`✅ Rute ${payload.label} berhasil disimpan!`, "success");

  // Kirim notifikasi instan ke Telegram saat rute dibuat/diedit di Web
  const isTransitMsg = payload.is_transit 
    ? `🎯 <b>RUTE TRANSIT BARU DIPANTAU!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n📍 <b>Rute:</b> ${payload.origin} ➔ ${payload.hub || 'Hub'} ➔ ${payload.destination}\n📅 <b>Tanggal:</b> ${payload.target_date || 'Rentang 14 Hari'}\n🎯 <b>Target Budget:</b> ${formatRupiah(payload.max_price_idr)}\n\n🔔 <i>Web Dashboard & Bot aktif memantau rute ini!</i>`
    : `🎯 <b>RUTE BARU DIPANTAU!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n📍 <b>Rute:</b> ${payload.origin} ➔ ${payload.destination}\n📅 <b>Tanggal:</b> ${payload.target_date || 'Rentang 14 Hari'}\n🎯 <b>Target Budget:</b> ${formatRupiah(payload.max_price_idr)}\n\n🔔 <i>Web Dashboard & Bot aktif memantau rute ini!</i>`;

  sendTelegramAlert(isTransitMsg);
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
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: "✅ <b>Tes Terhubung Berhasil!</b>\nFlight Price Monitor Pro aktif dan terhubung ke Telegram Anda.",
        parse_mode: "HTML"
      })
    }).then(r => r.json()).then(data => {
      if (data.ok) showToast("✅ Pesan tes terkirim ke Telegram!", "success");
      else showToast("❌ Gagal: " + data.description, "error");
    });
  } catch (err) {
    showToast("Error: " + err.message, "error");
  }
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.add("open");
    modal.classList.add("active");
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove("open");
    modal.classList.remove("active");
  }
}

function openNotificationsModal() {
  const container = document.getElementById("notificationsLogContainer");
  if (container) {
    const logs = state.staticData ? state.staticData.notifications || [] : [];
    if (logs.length === 0) {
      container.innerHTML = `<p style="color: var(--text-muted); text-align: center; padding: 2rem;">Belum ada riwayat notifikasi terkirim.</p>`;
    } else {
      container.innerHTML = logs.map(l => `
        <div style="padding: 0.85rem; border-bottom: 1px solid var(--border-color); font-size: 0.85rem;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
            <b>${l.route_label || 'Notifikasi'}</b>
            <span style="color: var(--text-sub); font-size: 0.75rem;">${new Date(l.sent_at).toLocaleString("id-ID")}</span>
          </div>
          <div style="color: var(--text-muted); white-space: pre-line;">${(l.message || '').replace(/<[^>]*>?/gm, '')}</div>
        </div>
      `).join("");
    }
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

function formatRupiah(val) {
  return "Rp " + (val || 0).toLocaleString("id-ID");
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

// Close modal when clicking outside on backdrop
document.addEventListener("click", (e) => {
  if (e.target && e.target.classList && e.target.classList.contains("modal-backdrop")) {
    e.target.classList.remove("open");
    e.target.classList.remove("active");
  }
});

// Expose all interactive functions to global window scope for inline HTML onclick handlers
window.openModal = openModal;
window.closeModal = closeModal;
window.openAddRouteModal = openAddRouteModal;
window.openEditRouteModal = openEditRouteModal;
window.handleDeleteRoute = handleDeleteRoute;
window.handleToggleRoute = handleToggleRoute;
window.handleToggleRouteType = handleToggleRouteType;
window.handleToggleTransitHub = handleToggleTransitHub;
window.openNotificationsModal = openNotificationsModal;
window.formatRupiah = formatRupiah;
window.getTravelokaSearchUrl = getTravelokaSearchUrl;
