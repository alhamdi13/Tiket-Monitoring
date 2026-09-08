"""
scheduler.py - Background Automated Scheduler & Worker untuk Flight Price Monitor Pro.
Menjalankan pengecekan multi-rute berkala, menyimpan histori harga tiket ke database,
dan memicu notifikasi Telegram saat harga tiket di bawah budget target.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import schedule

import database
from config import cfg
from notifier import TelegramNotifier
from scraper import FlightScraper, FlightResult

logger = logging.getLogger("scheduler")

# Cache in-memory untuk membandingkan harga terakhir yang ternotifikasi: key = "route_id-YYYY-MM-DD"
_last_notified_prices: Dict[str, int] = {}


class FlightScheduler:
    def __init__(self):
        self.scraper = FlightScraper()
        self.notifier = TelegramNotifier()
        self.running = False
        self.is_scanning = False
        self.thread: Optional[threading.Thread] = None
        self.last_scan_time: Optional[datetime] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="SchedulerWorker")
        self.thread.start()
        logger.info("[Scheduler] Automated background scheduler aktif...")

    def stop(self):
        self.running = False

    def _run_loop(self):
        # Jalankan scan perdana setelah delay singkat 3 detik
        time.sleep(3)
        self.scan_all_routes()

        # Atur jadwal rutin per jam
        schedule.every(1).hours.do(self._scheduled_job)

        while self.running:
            schedule.run_pending()
            time.sleep(30)

    def _scheduled_job(self):
        if not cfg.auto_scan_enabled:
            logger.info("[Scheduler] Auto-scan dimatikan di pengaturan, melewati jadwal.")
            return
        self.scan_all_routes()

    def scan_route(self, route_id: int) -> Dict[str, int]:
        """Memindai 1 rute tertentu untuk seluruh rentang hari."""
        route = database.get_route_by_id(route_id)
        if not route or not route["is_active"]:
            return {"scanned_days": 0, "cheap_found": 0}

        origin = route["origin"]
        destination = route["destination"]
        max_price = route["max_price_idr"]
        days_ahead = route["days_ahead"]
        route_label = route["label"] or f"{origin} ➔ {destination}"

        logger.info(f"[Scheduler] Memindai rute: {route_label} ({days_ahead} hari ke depan)")

        today = datetime.now()
        cheap_found_count = 0
        scanned_days = 0

        for day_offset in range(1, days_ahead + 1):
            target_date = today + timedelta(days=day_offset)
            date_str = target_date.strftime("%Y-%m-%d")

            try:
                flights = self.scraper.search(origin, destination, target_date)
            except Exception as e:
                logger.error(f"[Scheduler] Gagal scrape {origin}➔{destination} ({date_str}): {e}")
                continue

            if not flights:
                continue

            scanned_days += 1
            # 1. Simpan semua penerbangan ke database untuk analitik grafik
            database.save_flight_results(route_id, flights)

            # 2. Filter harga di bawah target
            cheap_flights = [f for f in flights if f.price_idr <= max_price]
            if not cheap_flights:
                continue

            cheapest = cheap_flights[0]
            cache_key = f"{route_id}-{date_str}"
            prev_price = _last_notified_prices.get(cache_key, 0)

            # Notifikasi jika belum pernah dinotifkan atau jika harga saat ini lebih murah dari sebelumnya
            if prev_price == 0 or cheapest.price_idr < prev_price:
                _last_notified_prices[cache_key] = cheapest.price_idr
                cheap_found_count += 1
                logger.info(f"[Scheduler] 🎯 Tiket murah ditemukan untuk {route_label} ({date_str}): {cheapest.price_formatted}")

                # Kirim Alert Telegram
                self.notifier.send_cheap_alert(
                    flights=cheap_flights,
                    route_label=f"{route_label} ({date_str})",
                    max_price=max_price,
                    route_id=route_id,
                )

        database.update_route_last_checked(route_id)
        return {"scanned_days": scanned_days, "cheap_found": cheap_found_count}

    def scan_all_routes(self) -> dict:
        """Memindai seluruh rute yang berstatus aktif di database."""
        if self.is_scanning:
            return {"status": "already_scanning"}

        self.is_scanning = True
        self.last_scan_time = datetime.now()
        logger.info("[Scheduler] Memulai pemindaian menyeluruh untuk semua rute aktif...")

        active_routes = database.get_routes(active_only=True)
        total_cheap = 0
        total_scanned = 0

        try:
            for route in active_routes:
                res = self.scan_route(route["id"])
                total_scanned += res.get("scanned_days", 0)
                total_cheap += res.get("cheap_found", 0)
        finally:
            self.is_scanning = False

        logger.info(f"[Scheduler] Pemindaian selesai. Total {total_scanned} hari dicek, {total_cheap} tiket murah ditemukan.")
        return {
            "status": "completed",
            "total_routes_checked": len(active_routes),
            "total_days_scanned": total_scanned,
            "cheap_tickets_found": total_cheap,
            "timestamp": datetime.now().isoformat()
        }


# Singleton Scheduler Instance
scheduler_service = FlightScheduler()


def scan_all_routes():
    return scheduler_service.scan_all_routes()


def scan_route(route_id: int):
    return scheduler_service.scan_route(route_id)
