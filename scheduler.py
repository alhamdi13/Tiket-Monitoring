"""
scheduler.py - Background Automated Scheduler & Worker untuk Flight Price Monitor Pro.
Mendukung pemantauan rentang hari, target date spesifik, dan penerbangan transit connecting.
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
        time.sleep(3)
        self.scan_all_routes()
        schedule.every(1).hours.do(self._scheduled_job)

        while self.running:
            schedule.run_pending()
            time.sleep(30)

    def _scheduled_job(self):
        if not cfg.auto_scan_enabled:
            return
        self.scan_all_routes()

    def scan_route(self, route_id: int) -> Dict[str, int]:
        route = database.get_route_by_id(route_id)
        if not route or not route["is_active"]:
            return {"scanned_days": 0, "cheap_found": 0}

        origin = route["origin"]
        destination = route["destination"]
        max_price = route["max_price_idr"]
        target_date_str = route.get("target_date")
        route_label = route["label"] or f"{origin} ➔ {destination}"

        today = datetime.now()
        cheap_found_count = 0
        scanned_days = 0

        # ==========================================
        # KASUS 1: PEMANTAUAN TANGGAL SPESIFIK
        # ==========================================
        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
            except ValueError:
                logger.error(f"[Scheduler] Format target_date tidak valid: {target_date_str}")
                return {"scanned_days": 0, "cheap_found": 0}

            logger.info(f"[Scheduler] 🎯 Memindai TANGGAL SPESIFIK: {route_label} pada {target_date_str}")
            flights = []
            try:
                if "Transit" in route_label or "Connecting" in route_label or (origin == "BDJ" and destination == "PDG"):
                    hub = "CGK" if "CGK" in route_label else None
                    flights = self.scraper.search_connecting(origin, destination, target_date, hub=hub)
                if not flights:
                    flights = self.scraper.search(origin, destination, target_date)
            except Exception as e:
                logger.error(f"[Scheduler] Gagal scrape target date {target_date_str}: {e}")
                return {"scanned_days": 0, "cheap_found": 0}

            if flights:
                scanned_days = 1
                if hasattr(flights[0], "total_price_idr"):
                    conv_flights = [
                        FlightResult(
                            airline=f"{c.leg1_airline} + {c.leg2_airline}",
                            flight_number=f"{c.leg1_flight_number}/{c.leg2_flight_number}",
                            origin=c.origin,
                            destination=c.destination,
                            departure_time=c.leg1_departure_time,
                            arrival_time=c.leg2_arrival_time,
                            duration_minutes=c.total_duration_minutes,
                            price_idr=c.total_price_idr,
                            seats_left=None,
                            source="connecting",
                            date=c.date,
                            booking_url=c.booking_url,
                            tiket_url=c.tiket_url
                        ) for c in flights
                    ]
                    database.save_flight_results(route_id, conv_flights)
                    cheapest_price = flights[0].total_price_idr
                    cheapest_fmt = flights[0].total_price_formatted
                else:
                    database.save_flight_results(route_id, flights)
                    cheapest_price = flights[0].price_idr
                    cheapest_fmt = flights[0].price_formatted

                prev_price = route.get("last_price_idr") or 0

                if cheapest_price <= max_price and (prev_price == 0 or cheapest_price < prev_price):
                    cheap_found_count = 1
                    diff_str = f" (Turun Rp {prev_price - cheapest_price:,.0f}!)" if prev_price > cheapest_price else ""
                    logger.info(f"[Scheduler] 🎯 Update harga tanggal spesifik {target_date_str}: {cheapest_fmt}{diff_str}")

                    self.notifier.send_cheap_alert(
                        flights=flights,
                        route_label=f"{route_label} (Target: {target_date_str}){diff_str}",
                        max_price=max_price,
                        route_id=route_id,
                    )

                database.update_route_last_checked(route_id, last_price=cheapest_price)
            return {"scanned_days": scanned_days, "cheap_found": cheap_found_count}

        # ==========================================
        # KASUS 2: PEMANTAUAN RENTANG HARI (1..N)
        # ==========================================
        days_ahead = route.get("days_ahead", 14)
        logger.info(f"[Scheduler] Memindai rentang rute: {route_label} ({days_ahead} hari ke depan)")

        cheapest_overall = 0
        for day_offset in range(1, days_ahead + 1):
            target_date = today + timedelta(days=day_offset)
            date_str = target_date.strftime("%Y-%m-%d")

            flights = []
            try:
                if "Transit" in route_label or "Connecting" in route_label or (origin == "BDJ" and destination == "PDG"):
                    hub = "CGK" if "CGK" in route_label else None
                    flights = self.scraper.search_connecting(origin, destination, target_date, hub=hub)
                if not flights:
                    flights = self.scraper.search(origin, destination, target_date)
            except Exception as e:
                continue

            if not flights:
                continue

            scanned_days += 1
            if hasattr(flights[0], "total_price_idr"):
                conv_flights = [
                    FlightResult(
                        airline=f"{c.leg1_airline} + {c.leg2_airline}",
                        flight_number=f"{c.leg1_flight_number}/{c.leg2_flight_number}",
                        origin=c.origin,
                        destination=c.destination,
                        departure_time=c.leg1_departure_time,
                        arrival_time=c.leg2_arrival_time,
                        duration_minutes=c.total_duration_minutes,
                        price_idr=c.total_price_idr,
                        seats_left=None,
                        source="connecting",
                        date=c.date,
                        booking_url=c.booking_url,
                        tiket_url=c.tiket_url
                    ) for c in flights
                ]
                database.save_flight_results(route_id, conv_flights)
                cheap_flights = [f for f in flights if f.total_price_idr <= max_price]
                if not cheap_flights:
                    continue
                cheapest = cheap_flights[0]
                cheapest_price = cheapest.total_price_idr
            else:
                database.save_flight_results(route_id, flights)
                cheap_flights = [f for f in flights if f.price_idr <= max_price]
                if not cheap_flights:
                    continue
                cheapest = cheap_flights[0]
                cheapest_price = cheapest.price_idr

            if cheapest_overall == 0 or cheapest_price < cheapest_overall:
                cheapest_overall = cheapest_price

            cache_key = f"{route_id}-{date_str}"
            prev_price = _last_notified_prices.get(cache_key, 0)

            if prev_price == 0 or cheapest_price < prev_price:
                _last_notified_prices[cache_key] = cheapest_price
                cheap_found_count += 1
                self.notifier.send_cheap_alert(
                    flights=cheap_flights,
                    route_label=f"{route_label} ({date_str})",
                    max_price=max_price,
                    route_id=route_id,
                )

        database.update_route_last_checked(route_id, last_price=cheapest_overall)
        return {"scanned_days": scanned_days, "cheap_found": cheap_found_count}

    def scan_all_routes(self) -> dict:
        if self.is_scanning:
            return {"status": "already_scanning"}

        self.is_scanning = True
        self.last_scan_time = datetime.now()
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

        return {
            "status": "completed",
            "total_routes_checked": len(active_routes),
            "total_days_scanned": total_scanned,
            "cheap_tickets_found": total_cheap,
            "timestamp": datetime.now().isoformat()
        }


scheduler_service = FlightScheduler()


def scan_all_routes():
    return scheduler_service.scan_all_routes()


def scan_route(route_id: int):
    return scheduler_service.scan_route(route_id)
