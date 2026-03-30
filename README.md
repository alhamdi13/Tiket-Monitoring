# ✈️ Flight Price Monitor — Telegram Bot

Bot otomatis yang memantau harga tiket pesawat di Traveloka/Tiket.com dan mengirimkan notifikasi ke Telegram saat tiket murah ditemukan.

---

## 🚀 Setup (5 Langkah)

### 1. Buat Telegram Bot
1. Buka Telegram → cari **@BotFather**
2. Kirim `/newbot`
3. Masukkan nama bot (misal: `Flight Monitor Saya`)
4. Salin **token** yang diberikan (format: `123456:ABCdef...`)

### 2. Dapatkan Chat ID Kamu
1. Cari **@userinfobot** di Telegram
2. Kirim `/start`
3. Salin angka **Id** yang muncul (misal: `987654321`)

### 3. Konfigurasi
```bash
cp .env.example .env
nano .env   # atau edit dengan text editor apa saja
```

Isi nilai berikut di `.env`:
```
TELEGRAM_BOT_TOKEN=token-dari-botfather
TELEGRAM_CHAT_ID=id-dari-userinfobot
FLIGHT_ORIGIN=CGK       # Bandara asal (kode IATA)
FLIGHT_DESTINATION=DPS  # Bandara tujuan (kode IATA)
MAX_PRICE_IDR=500000     # Notif jika harga di bawah ini
DAYS_AHEAD=30            # Cek 30 hari ke depan
CHECK_INTERVAL_HOURS=6   # Cek setiap 6 jam
```

**Kode IATA Bandara Indonesia yang Umum:**
| Kota | Bandara | Kode |
|------|---------|------|
| Jakarta | Soekarno-Hatta | CGK |
| Bali | Ngurah Rai | DPS |
| Surabaya | Juanda | SUB |
| Malang | Abdul Rachman Saleh | MLG |
| Yogyakarta | YIA / Adisutjipto | YIA / JOG |
| Medan | Kualanamu | KNO |
| Makassar | Sultan Hasanuddin | UPG |
| Lombok | Zainuddin Abdul Madjid | LOP |

### 4. Install & Jalankan

**Cara A — Python langsung:**
```bash
pip install -r requirements.txt
python monitor.py
```

**Cara B — Docker (direkomendasikan agar jalan terus):**
```bash
docker build -t flight-monitor .
docker run -d --name flight-monitor --env-file .env flight-monitor
```

### 5. Deploy Gratis (Pilih Salah Satu)

#### Option 1: Railway (Termudah)
1. Daftar di [railway.app](https://railway.app) (gratis)
2. New Project → Deploy from GitHub
3. Push kode ke GitHub dulu
4. Tambahkan Environment Variables dari `.env` di dashboard Railway
5. Deploy!

#### Option 2: Render
1. Daftar di [render.com](https://render.com)
2. New → Background Worker
3. Connect GitHub repo
4. Set Environment Variables
5. Deploy!

#### Option 3: VPS / Raspberry Pi
```bash
# Jalankan di background dengan nohup
nohup python monitor.py > flight-monitor.log 2>&1 &

# Atau gunakan screen
screen -S flight-monitor
python monitor.py
# Ctrl+A, D untuk detach
```

---

## 📱 Contoh Notifikasi Telegram

```
🚨 TIKET MURAH DITEMUKAN!
──────────────────────────────
🛫 Rute: Jakarta → Bali (2024-07-15)
💸 Batas harga: Rp 500.000

1. 🟢 Citilink QG-831
   🕐 06:00 → 08:55 (2j 55m)
   💰 Rp 389.000

2. ❤️ AirAsia QZ-7684
   🕐 08:30 → 11:20 (2j 50m)
   💰 Rp 425.000

──────────────────────────────
🔗 Lihat di Traveloka
⏰ Cek dilakukan: 15 Jun 2024, 06:00 WIB
```

---

## ⚠️ Catatan Penting

- **Anti-spam**: Bot tidak akan mengirim notifikasi berulang untuk harga yang sama. Notifikasi baru hanya dikirim jika ada harga yang lebih murah dari sebelumnya.
- **Scraping**: Endpoint Traveloka/Tiket.com adalah unofficial. Jika tidak berfungsi, buka issue di repo.
- **Rate limiting**: Bot menunggu antar request untuk menghindari pemblokiran IP.
- **Akurasi harga**: Harga di Traveloka bisa berubah sewaktu-waktu. Selalu verifikasi sebelum membeli.

---

## 🐛 Troubleshooting

**Bot tidak mengirim pesan:**
- Pastikan kamu sudah `/start` bot di Telegram terlebih dahulu
- Cek token dan chat ID di `.env`

**Scraping gagal terus:**
- Coba tambah `LOG_LEVEL=DEBUG` di `.env` untuk lihat detail error
- Bisa jadi IP kamu di-rate-limit; tunggu beberapa jam

**Harga tidak ditemukan:**
- Cek kode IATA sudah benar
- Coba perbesar `DAYS_AHEAD`
