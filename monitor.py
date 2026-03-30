"""
monitor.py — Scheduler utama flight monitor.

Jalankan: python monitor.py

Alur kerja:
  1. Validasi konfigurasi
  2. Test koneksi Telegram
  3. Jalankan pengecekan pertama segera
  4. Jadwalkan pengecekan berikutnya setiap N jam
"""

import logging
import time
from datetime import datetime

import schedule

from config import cfg
from scraper import FlightScraper, ScraperException
from notifier import TelegramNotifier

# ── Setup Logging ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, cfg.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("monitor")


# ── Komponen Global ───────────────────────────────────────────────────────────

scraper = FlightScraper()
notifier = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)

# Simpan harga terakhir yang sudah dinotifkan (hindari spam notifikasi)
_last_notified: dict[str, int] = {}   # key: "IATA-IATA-YYYY-MM-DD", value: price_idr


# ── Fungsi Utama ──────────────────────────────────────────────────────────────

def check_flights():
    """
    Cek harga tiket untuk semua tanggal dalam rentang days_ahead.
    Kirim notifikasi jika ditemukan harga di bawah max_price_idr.
    """
    logger.info(
        f"▶ Memulai pengecekan: {cfg.route.label} | "
        f"Batas Rp {cfg.max_price_idr:,} | "
        f"{cfg.days_ahead} hari ke depan"
    )

    found_any_cheap = False
    cheap_per_date: dict[str, list] = {}

    from datetime import timedelta
    today = datetime.now()

    for day_offset in range(1, cfg.days_ahead + 1):
        target_date = today + timedelta(days=day_offset)
        date_str = target_date.strftime("%Y-%m-%d")

        try:
            results = scraper.search(
                origin=cfg.route.origin,
                destination=cfg.route.destination,
                date=target_date,
            )
        except ScraperException as e:
            logger.error(f"[{date_str}] Gagal scrape: {e}")
            continue

        if not results:
            logger.debug(f"[{date_str}] Tidak ada penerbangan ditemukan")
            continue

        # Filter tiket di bawah harga maksimum
        cheap = [f for f in results if f.price_idr <= cfg.max_price_idr]

        if not cheap:
            logger.debug(
                f"[{date_str}] Harga termurah: Rp {results[0].price_idr:,} "
                f"(di atas limit Rp {cfg.max_price_idr:,})"
            )
            continue

        # Cek apakah harga ini sudah pernah dinotifkan sebelumnya
        cache_key = f"{cfg.route.origin}-{cfg.route.destination}-{date_str}"
        prev_price = _last_notified.get(cache_key, 0)

        if cheap[0].price_idr < prev_price or prev_price == 0:
            # Harga baru lebih murah atau belum pernah notif → kirim!
            cheap_per_date[date_str] = cheap
            _last_notified[cache_key] = cheap[0].price_idr
            found_any_cheap = True
            logger.info(
                f"[{date_str}] 🎉 Tiket murah! {len(cheap)} opsi, "
                f"termurah Rp {cheap[0].price_idr:,}"
            )
        else:
            logger.debug(
                f"[{date_str}] Harga sama/lebih mahal dari notif sebelumnya "
                f"(Rp {cheap[0].price_idr:,} vs prev Rp {prev_price:,})"
            )

    # Kirim notifikasi per tanggal
    for date_str, cheap_flights in cheap_per_date.items():
        notifier.send_cheap_alert(
            flights=cheap_flights,
            route_label=f"{cfg.route.label} ({date_str})",
            max_price=cfg.max_price_idr,
        )

    if not found_any_cheap:
        logger.info("✓ Pengecekan selesai — tidak ada tiket murah baru ditemukan")


def run():
    """Entry point utama."""
    logger.info("=" * 60)
    logger.info("  ✈  Flight Price Monitor")
    logger.info("=" * 60)

    # Validasi konfigurasi
    try:
        cfg.validate()
    except ValueError as e:
        logger.critical(str(e))
        return

    # Test koneksi Telegram
    if not notifier.test_connection():
        logger.critical("Tidak bisa terhubung ke Telegram. Periksa TELEGRAM_BOT_TOKEN.")
        return

    # Kirim pesan startup
    notifier.send_startup_message(
        route_label=cfg.route.label,
        max_price=cfg.max_price_idr,
        interval_hours=cfg.check_interval_hours,
    )

    # Pengecekan pertama langsung dijalankan
    check_flights()

    # Jadwalkan pengecekan berikutnya
    schedule.every(cfg.check_interval_hours).hours.do(check_flights)
    logger.info(f"⏱ Pengecekan berikutnya dijadwalkan setiap {cfg.check_interval_hours} jam")

    # Loop utama
    while True:
        schedule.run_pending()
        time.sleep(60)  # Cek jadwal setiap 1 menit


if __name__ == "__main__":
    run()
