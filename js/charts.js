/**
 * charts.js - Chart.js & Lowest Fare Calendar Renderer untuk Flight Price Monitor Pro.
 */

let trendChartInstance = null;

function formatRupiah(num) {
  if (!num) return "Rp 0";
  return "Rp " + Math.round(num).toLocaleString("id-ID");
}

/**
 * Render Grafik Tren Harga Harian menggunakan Chart.js
 */
function renderPriceTrendChart(trendData, maxBudget = null) {
  const ctx = document.getElementById("priceTrendCanvas");
  if (!ctx) return;

  if (trendChartInstance) {
    trendChartInstance.destroy();
  }

  const labels = trendData.dates || [];
  const minPrices = trendData.min_prices || [];
  const avgPrices = trendData.avg_prices || [];

  if (labels.length === 0) {
    ctx.parentElement.innerHTML = `
      <div style="text-align: center; padding: 3rem; color: var(--text-muted);">
        <p>📊 Belum ada data harga historis untuk rute ini.</p>
        <p style="font-size: 0.8rem; margin-top: 0.5rem;">Klik tombol "Scan Rute Ini" untuk mengambil data harga penerbangan.</p>
      </div>
    `;
    return;
  }

  // Siapkan dataset
  const datasets = [
    {
      label: "Harga Termurah",
      data: minPrices,
      borderColor: "#10b981",
      backgroundColor: "rgba(16, 185, 129, 0.12)",
      borderWidth: 3,
      fill: true,
      tension: 0.35,
      pointBackgroundColor: "#10b981",
      pointRadius: 4,
      pointHoverRadius: 7,
    },
    {
      label: "Rata-rata Harga",
      data: avgPrices,
      borderColor: "#6366f1",
      backgroundColor: "transparent",
      borderWidth: 2,
      borderDash: [5, 5],
      pointRadius: 2,
      tension: 0.35,
    }
  ];

  // Garis Target Budget
  if (maxBudget) {
    datasets.push({
      label: `Target Budget (${formatRupiah(maxBudget)})`,
      data: new Array(labels.length).fill(maxBudget),
      borderColor: "rgba(244, 63, 94, 0.7)",
      borderWidth: 2,
      borderDash: [3, 3],
      pointRadius: 0,
      fill: false
    });
  }

  const isDark = document.documentElement.getAttribute("data-theme") !== "light";
  const textColor = isDark ? "#9ca3af" : "#475569";
  const gridColor = isDark ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.05)";

  trendChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels.map(d => {
        const parts = d.split("-");
        return `${parts[2]}/${parts[1]}`;
      }),
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "top",
          labels: {
            color: textColor,
            font: { family: "'Plus Jakarta Sans', sans-serif", weight: "600", size: 12 },
            usePointStyle: true,
            boxWidth: 8
          }
        },
        tooltip: {
          backgroundColor: isDark ? "rgba(17, 24, 39, 0.95)" : "rgba(255, 255, 255, 0.95)",
          titleColor: isDark ? "#f3f4f6" : "#0f172a",
          bodyColor: isDark ? "#e5e7eb" : "#334155",
          borderColor: isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)",
          borderWidth: 1,
          padding: 12,
          boxPadding: 6,
          usePointStyle: true,
          callbacks: {
            label: function (context) {
              return ` ${context.dataset.label}: ${formatRupiah(context.parsed.y)}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: "'Plus Jakarta Sans', sans-serif" } }
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { family: "'JetBrains Mono', monospace", size: 11 },
            callback: function (val) {
              return (val / 1000).toLocaleString("id-ID") + "k";
            }
          }
        }
      }
    }
  });
}

/**
 * Render Matriks Kalender Tarif Termurah 30 Hari
 */
function renderLowestFareCalendar(calendarItems, maxBudget, origin, destination) {
  const container = document.getElementById("fareCalendarGrid");
  if (!container) return;

  container.innerHTML = "";

  if (!calendarItems || calendarItems.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--text-muted);">
        Belum ada data kalender tarif. Jalankan pemindaian untuk rute ini.
      </div>
    `;
    return;
  }

  const daysOfWeek = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];

  calendarItems.forEach(item => {
    const card = document.createElement("a");
    card.className = "calendar-card";
    
    const d = new Date(item.flight_date);
    const dayName = daysOfWeek[d.getDay()];
    const dateFormatted = `${d.getDate()} ${d.toLocaleString("id-ID", { month: "short" })}`;

    let priceClass = "expensive";
    let priceText = "Tidak ada";

    if (item.cheapest_price) {
      priceText = formatRupiah(item.cheapest_price);
      if (maxBudget && item.cheapest_price <= maxBudget) {
        priceClass = "cheap";
      } else if (maxBudget && item.cheapest_price <= maxBudget * 1.2) {
        priceClass = "normal";
      }
      
      const travelokaUrl = `https://www.traveloka.com/en-id/flight/fullprice/${origin.toLowerCase()}-to-${destination.toLowerCase()}/${item.flight_date}/1/0/0/Economy`;
      card.href = travelokaUrl;
      card.target = "_blank";
      card.title = `Klik untuk pesan tiket ${item.airline || ''} seharga ${priceText} di Traveloka`;
    } else {
      card.style.opacity = "0.45";
      card.style.cursor = "default";
      card.href = "javascript:void(0)";
    }

    card.innerHTML = `
      <div class="cal-date">${dateFormatted}</div>
      <div class="cal-day">${dayName}</div>
      <div class="cal-price ${priceClass}">${priceText}</div>
      <div class="cal-airline">${item.airline || '-'}</div>
    `;

    container.appendChild(card);
  });
}
