"""
github_action_runner.py - Otomatisasi 100% Serverless via GitHub Actions.
Menjalankan pemindaian harga tiket, mengirim alert ke Telegram, dan mengekspor data ke static/data/flights.json
sehingga Dashboard bisa dibuka langsung di GitHub Pages tanpa memerlukan server lokal.
"""

import json
import logging
import os
from datetime import datetime

import database
from notifier import TelegramNotifier
from scraper import FlightScraper
from scheduler import scheduler_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("github_runner")


def run_github_monitoring():
    logger.info("=== Menjalankan GitHub Actions Flight Monitor ===")
    
    # 1. Inisialisasi Database
    database.init_db()

    # 2. Ambil Kredensial dari GitHub Secrets / Environment
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")

    if tg_token:
        database.set_setting("telegram_bot_token", tg_token)
    if tg_chat:
        database.set_setting("telegram_chat_id", tg_chat)

    # 3. Jalankan Pemindaian Seluruh Rute Aktif
    routes = database.get_routes(active_only=True)
    logger.info(f"Memindai {len(routes)} rute aktif...")

    scan_result = scheduler_service.scan_all_routes()
    logger.info(f"Hasil scan: {scan_result}")

    # 4. Ekspor Data Lengkap ke JSON untuk GitHub Pages
    stats = database.get_dashboard_stats()
    all_routes = database.get_routes()
    latest_flights = database.get_latest_flights(limit=100)
    notifs = database.get_notifications(limit=50)

    analytics_map = {}
    calendar_map = {}

    for r in all_routes:
        rid = r["id"]
        analytics_map[str(rid)] = database.get_price_trends(rid)
        calendar_map[str(rid)] = database.get_lowest_fare_calendar(rid, days_ahead=30)

    export_payload = {
        "status": {
            "status": "online",
            "mode": "github_pages",
            "last_updated": datetime.now().isoformat(),
            "scheduler": {
                "running": True,
                "is_scanning": False,
                "last_scan": datetime.now().isoformat(),
                "auto_scan_enabled": True
            },
            "telegram": {
                "token_configured": bool(tg_token or database.get_setting("telegram_bot_token")),
                "chat_id_configured": bool(tg_chat or database.get_setting("telegram_chat_id")),
                "bot_listener_active": False
            },
            "stats": stats
        },
        "routes": all_routes,
        "flights": latest_flights,
        "notifications": notifs,
        "analytics": analytics_map,
        "calendar": calendar_map
    }

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "flights.json")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, indent=2, ensure_ascii=False)

    logger.info(f"Data berhasil diekspor ke {out_file}")


if __name__ == "__main__":
    run_github_monitoring()
