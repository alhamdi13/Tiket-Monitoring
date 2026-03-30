"""
config.py — Konfigurasi utama flight monitor.
Semua nilai dibaca dari file .env
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class FlightRoute:
    origin: str           # Kode IATA bandara asal (misal: CGK, MLG, SUB)
    destination: str      # Kode IATA bandara tujuan (misal: DPS, JOG, BPN)
    label: str = ""       # Label tampilan (misal: "Jakarta → Bali")

    def __post_init__(self):
        self.origin = self.origin.upper()
        self.destination = self.destination.upper()
        if not self.label:
            self.label = f"{self.origin} → {self.destination}"


@dataclass
class Config:
    # ── Telegram ──────────────────────────────────────────────────────
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )
    telegram_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "")
    )

    # ── Rute & Budget ─────────────────────────────────────────────────
    route: FlightRoute = field(
        default_factory=lambda: FlightRoute(
            origin=os.getenv("FLIGHT_ORIGIN", "CGK"),
            destination=os.getenv("FLIGHT_DESTINATION", "DPS"),
            label=os.getenv("FLIGHT_LABEL", ""),
        )
    )

    # Harga maksimum (IDR) agar dianggap "murah" dan notif dikirim
    max_price_idr: int = field(
        default_factory=lambda: int(os.getenv("MAX_PRICE_IDR", "500000"))
    )

    # Berapa hari ke depan yang dicek (misal: 7 = cek 7 hari ke depan)
    days_ahead: int = field(
        default_factory=lambda: int(os.getenv("DAYS_AHEAD", "30"))
    )

    # ── Jadwal Pengecekan ─────────────────────────────────────────────
    # Interval dalam JAM (misal: 6 = cek setiap 6 jam)
    check_interval_hours: int = field(
        default_factory=lambda: int(os.getenv("CHECK_INTERVAL_HOURS", "6"))
    )

    # ── Logging ───────────────────────────────────────────────────────
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )

    def validate(self):
        errors = []
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN belum diisi di .env")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID belum diisi di .env")
        if not self.route.origin or not self.route.destination:
            errors.append("FLIGHT_ORIGIN dan FLIGHT_DESTINATION harus diisi")
        if self.max_price_idr <= 0:
            errors.append("MAX_PRICE_IDR harus lebih dari 0")
        if errors:
            raise ValueError("Konfigurasi tidak valid:\n" + "\n".join(f"  - {e}" for e in errors))
        return True


# Singleton config — import dari modul lain pakai: from config import cfg
cfg = Config()
