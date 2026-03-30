"""
scraper.py — Ambil harga tiket dari Traveloka (+ fallback Tiket.com)

Strategi:
  1. Coba Traveloka internal API (JSON endpoint)
  2. Jika gagal, fallback ke Tiket.com API
  3. Jika keduanya gagal, raise ScraperException dengan detail error

Catatan: Endpoint ini adalah unofficial/reverse-engineered.
Jika Traveloka mengubah struktur API, payload di _build_payload()
dan parser di _parse_response() mungkin perlu disesuaikan.
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

import cloudscraper

logger = logging.getLogger(__name__)


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class FlightResult:
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    price_idr: int
    seats_left: Optional[int]
    source: str  # "traveloka" atau "tiket"
    date: str    # format: YYYY-MM-DD

    @property
    def price_formatted(self) -> str:
        return f"Rp {self.price_idr:,.0f}".replace(",", ".")

    def __repr__(self):
        return (
            f"[{self.airline} {self.flight_number}] "
            f"{self.departure_time} → {self.arrival_time} | "
            f"{self.price_formatted}"
        )


class ScraperException(Exception):
    pass


# ── Traveloka Scraper ─────────────────────────────────────────────────────────

class TravelokaScraper:
    """
    Scraper untuk Traveloka menggunakan cloudscraper (bypass Cloudflare).
    Menggunakan internal API Traveloka.
    """

    API_BASE = "https://api.traveloka.com"
    # Endpoint ini reverse-engineered; bisa berubah sewaktu-waktu
    SEARCH_PATH = "/v2/flight/search/search"

    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "X-Domain": "traveloka.com",
        "X-Tvlk-Encrypted-Request": "false",
        "Origin": "https://www.traveloka.com",
        "Referer": "https://www.traveloka.com/",
    }

    def __init__(self):
        self.client = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )

    def search(self, origin: str, destination: str, date: datetime, adults: int = 1) -> list[FlightResult]:
        payload = self._build_payload(origin, destination, date, adults)
        logger.info(f"[Traveloka] Mencari {origin}→{destination} tanggal {date.strftime('%Y-%m-%d')}")

        try:
            resp = self.client.post(
                f"{self.API_BASE}{self.SEARCH_PATH}",
                json=payload,
                headers=self.HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()
            results = self._parse_response(raw, origin, destination, date)
            logger.info(f"[Traveloka] Ditemukan {len(results)} penerbangan")
            return results
        except Exception as exc:
            raise ScraperException(f"Traveloka gagal: {exc}") from exc

    def _build_payload(self, origin, destination, date, adults):
        return {
            "data": {
                "flightSpec": {
                    "flightType": "ONE_WAY",
                    "segments": [
                        {
                            "departureAirport": {"code": origin},
                            "arrivalAirport": {"code": destination},
                            "departureDate": {
                                "year": date.year,
                                "month": date.month,
                                "day": date.day,
                            },
                        }
                    ],
                    "adultsCount": adults,
                    "childrenCount": 0,
                    "infantsCount": 0,
                    "cabinClass": "ECONOMY",
                },
                "page": {"limit": 30, "offset": 0},
                "sort": {"by": "PRICE", "order": "ASC"},
                "filters": {},
            }
        }

    def _parse_response(self, data: dict, origin, destination, date) -> list[FlightResult]:
        flights = []
        date_str = date.strftime("%Y-%m-%d")

        # Traveloka bisa punya beberapa struktur respons; coba beberapa path
        flight_list = (
            data.get("data", {}).get("flightList")
            or data.get("data", {}).get("flights")
            or data.get("data", {}).get("results", {}).get("flightList")
            or []
        )

        for item in flight_list:
            try:
                # Harga
                price_block = (
                    item.get("displayPrice")
                    or item.get("price")
                    or item.get("totalPrice")
                    or {}
                )
                price = int(price_block.get("amount", 0) or price_block.get("value", 0))
                if price <= 0:
                    continue

                # Legs / segmen penerbangan
                legs = item.get("legs") or item.get("segments") or [{}]
                leg = legs[0] if legs else {}

                airline = (
                    leg.get("carrier", {}).get("name")
                    or leg.get("airline", {}).get("name")
                    or "Unknown"
                )
                flight_number = (
                    leg.get("flightNumber")
                    or leg.get("number")
                    or "-"
                )
                dep_time = leg.get("departureTime") or leg.get("departure", {}).get("time", "")
                arr_time = leg.get("arrivalTime") or leg.get("arrival", {}).get("time", "")
                duration = int(leg.get("duration", {}).get("totalMinutes", 0) or 0)
                seats = item.get("seatAvailability") or item.get("seatsLeft")

                flights.append(
                    FlightResult(
                        airline=airline,
                        flight_number=flight_number,
                        origin=origin,
                        destination=destination,
                        departure_time=dep_time,
                        arrival_time=arr_time,
                        duration_minutes=duration,
                        price_idr=price,
                        seats_left=seats,
                        source="traveloka",
                        date=date_str,
                    )
                )
            except (KeyError, TypeError, ValueError) as e:
                logger.debug(f"[Traveloka] Skip item karena parse error: {e}")
                continue

        return sorted(flights, key=lambda f: f.price_idr)


# ── Tiket.com Scraper (Fallback) ──────────────────────────────────────────────

class TiketScraper:
    """
    Fallback scraper menggunakan Tiket.com API.
    """

    API_BASE = "https://www.tiket.com"
    SEARCH_PATH = "/api/v2/flight/search"

    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": "id-ID,id;q=0.9",
        "Origin": "https://www.tiket.com",
        "Referer": "https://www.tiket.com/",
    }

    def __init__(self):
        self.client = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )

    def search(self, origin: str, destination: str, date: datetime, adults: int = 1) -> list[FlightResult]:
        params = {
            "from": origin,
            "to": destination,
            "date": date.strftime("%Y-%m-%d"),
            "adult": adults,
            "child": 0,
            "infant": 0,
            "class": "economy",
            "page": 1,
            "limit": 30,
            "sort": "cheapest",
        }
        logger.info(f"[Tiket.com] Mencari {origin}→{destination} tanggal {date.strftime('%Y-%m-%d')}")

        try:
            resp = self.client.get(
                f"{self.API_BASE}{self.SEARCH_PATH}",
                params=params,
                headers=self.HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()
            results = self._parse_response(raw, origin, destination, date)
            logger.info(f"[Tiket.com] Ditemukan {len(results)} penerbangan")
            return results
        except Exception as exc:
            raise ScraperException(f"Tiket.com gagal: {exc}") from exc

    def _parse_response(self, data: dict, origin, destination, date) -> list[FlightResult]:
        flights = []
        date_str = date.strftime("%Y-%m-%d")

        items = (
            data.get("data", {}).get("flights")
            or data.get("data", [])
            or []
        )

        for item in items:
            try:
                price = int(
                    item.get("price", {}).get("amount", 0)
                    or item.get("totalFare", 0)
                    or 0
                )
                if price <= 0:
                    continue

                airline = item.get("airlineName") or item.get("carrier", {}).get("name", "Unknown")
                flight_number = item.get("flightNumber") or item.get("number", "-")
                dep_time = item.get("departureTime") or ""
                arr_time = item.get("arrivalTime") or ""
                duration = int(item.get("durationMinutes", 0) or 0)

                flights.append(
                    FlightResult(
                        airline=airline,
                        flight_number=flight_number,
                        origin=origin,
                        destination=destination,
                        departure_time=dep_time,
                        arrival_time=arr_time,
                        duration_minutes=duration,
                        price_idr=price,
                        seats_left=None,
                        source="tiket",
                        date=date_str,
                    )
                )
            except (KeyError, TypeError, ValueError) as e:
                logger.debug(f"[Tiket.com] Skip item: {e}")
                continue

        return sorted(flights, key=lambda f: f.price_idr)


# ── Smart Scraper (Primary + Fallback) ───────────────────────────────────────

class FlightScraper:
    """
    Wrapper cerdas: coba Traveloka dulu, fallback ke Tiket.com.
    """

    def __init__(self):
        self._traveloka = TravelokaScraper()
        self._tiket = TiketScraper()

    def search(self, origin: str, destination: str, date: datetime, adults: int = 1) -> list[FlightResult]:
        # Coba Traveloka dulu
        try:
            results = self._traveloka.search(origin, destination, date, adults)
            if results:
                return results
            logger.warning("[FlightScraper] Traveloka mengembalikan hasil kosong, coba Tiket.com...")
        except ScraperException as e:
            logger.warning(f"[FlightScraper] Traveloka gagal ({e}), beralih ke Tiket.com...")

        # Fallback ke Tiket.com
        return self._tiket.search(origin, destination, date, adults)

    def search_date_range(
        self, origin: str, destination: str, days_ahead: int = 30
    ) -> list[FlightResult]:
        """Cari harga untuk beberapa hari ke depan, kembalikan semua hasil."""
        all_results = []
        today = datetime.now()

        for day_offset in range(1, days_ahead + 1):
            target_date = today + timedelta(days=day_offset)
            try:
                results = self.search(origin, destination, target_date)
                all_results.extend(results)
            except ScraperException as e:
                logger.error(f"[FlightScraper] Gagal tanggal {target_date.strftime('%Y-%m-%d')}: {e}")

        return all_results
