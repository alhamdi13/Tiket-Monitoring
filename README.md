# ✈️ Flight Price Monitor Pro

Sistem pemantauan harga tiket pesawat otomatis all-in-one yang dilengkapi dengan **Web Dashboard Interaktif (FastAPI)**, penyimpanan database **SQLite**, serta **Bot Telegram 2 Arah (Interactive Command & Push Alert)**.

---

## 🚀 Fitur Unggulan

1. **Modern Web Dashboard**:
   - **Price Trend Chart**: Grafik fluktuasi harga terendah dan rata-rata per tanggal.
   - **Lowest Fare Heatmap Calendar**: Matriks kalender 30 hari tarif termurah dengan tautan pemesanan langsung ke Traveloka / Tiket.com.
   - **Multi-Route Manager**: Tambah, edit, aktifkan/nonaktifkan, dan hapus rute pemantauan dengan autocomplete bandara IATA.
   - **Instant Scan Trigger**: Tombol pemindaian instan untuk rute tertentu atau seluruh rute sekaligus.
   - **Theme Switcher**: Dukungan mode Gelap (*Dark Glassmorphism*) dan mode Terang (*Light*).

2. **Bot Telegram Interaktif 2 Arah**:
   - Menerima dan merespons perintah langsung di chat:
     - `/cek CGK DPS 2026-10-15` — Cari harga tiket detik itu juga.
     - `/tambah SUB DPS 600000 14` — Daftarkan rute pantauan baru dari chat.
     - `/list` — Tampilkan seluruh rute yang sedang dipantau.
     - `/hapus [ID]` — Hapus rute pantauan tertentu.
     - `/scan` — Jalankan scan harga sekarang juga.
     - `/status` — Cek status sistem, database, dan scheduler.

3. **Smart Push Alert**:
   - Format HTML rapi dengan perbandingan harga vs budget, info maskapai, jam penerbangan, estimasi durasi, dan sisa kursi.
   - Anti-spam cerdas: Notifikasi hanya dikirim jika harga baru lebih murah dari notifikasi sebelumnya.

4. **Database Persistence (SQLite)**:
   - Menyimpan seluruh riwayat harga penerbangan, log notifikasi, dan rute pantauan secara permanen.

---

## 🛠️ Panduan Menjalankan

### 1. Install Dependensi
```bash
pip install -r requirements.txt
```

### 2. Konfigurasi Bot Telegram
Buka file `.env` dan masukkan token serta Chat ID Telegram kamu:
```env
TELEGRAM_BOT_TOKEN=token_bot_dari_botfather
TELEGRAM_CHAT_ID=chat_id_kamu
```

### 3. Jalankan Aplikasi
```bash
python main.py
```

Buka browser dan akses Dashboard di:
👉 **`http://localhost:8000`**

---

## 📁 Struktur Folder

```
Tiket-Monitoring-Pro/
├── main.py                   # FastAPI REST API & Server Entry Point
├── database.py               # SQLite Data Access Layer & Schema
├── config.py                 # Konfigurasi terpusat
├── scraper.py                # Multi-provider scraping engine & fallback
├── notifier.py               # Telegram push notification formatter
├── telegram_bot.py           # Telegram interactive 2-way bot handler
├── scheduler.py              # Background worker & periodic scheduler
├── airports.json             # Database bandara & kode IATA
├── static/                   # Web Dashboard UI
│   ├── index.html            # Halaman Web SPA
│   ├── css/style.css         # Styling Glassmorphism modern
│   └── js/
│       ├── app.js            # State management & REST API client
│       └── charts.js         # Renderer grafik Chart.js & kalender tarif
└── .env                      # File konfigurasi
```
