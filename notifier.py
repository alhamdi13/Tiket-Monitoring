"""
notifier.py — Kirim notifikasi Telegram saat tiket murah ditemukan.

Menggunakan Telegram Bot API (tanpa library eksternal berat,
cukup dengan requests biasa).
"""

import logging
from typing import Optional

import requests

from scraper import FlightResult

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# ── Emoji & Format ────────────────────────────────────────────────────────────

AIRLINE_EMOJI = {
    "garuda": "🦅",
    "lion": "🦁",
    "batik": "🌺",
    "citilink": "🟢",
    "airasia": "❤️",
    "sriwijaya": "🌴",
    "trans nusa": "✈️",
    "wings": "🕊️",
}


def _airline_emoji(name: str) -> str:
    name_lower = name.lower()
    for key, emoji in AIRLINE_EMOJI.items():
        if key in name_lower:
            return emoji
    return "✈️"


def _format_duration(minutes: int) -> str:
    if not minutes:
        return ""
    h, m = divmod(minutes, 60)
    return f"{h}j {m}m" if m else f"{h}j"


# ── Telegram Sender ───────────────────────────────────────────────────────────

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.token = bot_token
        self.chat_id = chat_id
        self._base = f"https://api.telegram.org/bot{bot_token}"

    def _post(self, method: str, payload: dict) -> dict:
        url = f"{self._base}/{method}"
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        try:
            self._post("sendMessage", {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            })
            logger.info("[Telegram] Pesan berhasil dikirim")
            return True
        except Exception as e:
            logger.error(f"[Telegram] Gagal kirim pesan: {e}")
            return False

    def send_cheap_alert(
        self,
        flights: list[FlightResult],
        route_label: str,
        max_price: int,
    ) -> bool:
        """Kirim notifikasi tiket murah dalam format yang rapi."""
        if not flights:
            return False

        cheapest = flights[0]
        count = len(flights)

        header = (
            f"🚨 <b>TIKET MURAH DITEMUKAN!</b>\n"
            f"{'─' * 30}\n"
            f"🛫 <b>Rute:</b> {route_label}\n"
            f"📅 <b>Tanggal:</b> {cheapest.date}\n"
            f"💸 <b>Batas harga:</b> Rp {max_price:,.0f}\n".replace(",", ".")
        )

        body = ""
        for i, f in enumerate(flights[:5], 1):  # Tampilkan maks 5 penerbangan
            emoji = _airline_emoji(f.airline)
            duration_str = f" ({_format_duration(f.duration_minutes)})" if f.duration_minutes else ""
            seats_str = f" | 🪑 {f.seats_left} kursi" if f.seats_left else ""
            body += (
                f"\n{i}. {emoji} <b>{f.airline}</b> {f.flight_number}\n"
                f"   🕐 {f.departure_time} → {f.arrival_time}{duration_str}\n"
                f"   💰 <b>{f.price_formatted}</b>{seats_str}\n"
                f"   📍 Sumber: {f.source.capitalize()}\n"
            )

        if count > 5:
            body += f"\n<i>...dan {count - 5} penerbangan murah lainnya</i>\n"

        traveloka_url = (
            f"https://www.traveloka.com/en-id/flight/fullprice/"
            f"{cheapest.origin.lower()}-to-{cheapest.destination.lower()}"
            f"/{cheapest.date}/1/0/0/Economy"
        )

        footer = (
            f"\n{'─' * 30}\n"
            f"🔗 <a href='{traveloka_url}'>Lihat di Traveloka</a>\n"
            f"⏰ Cek dilakukan: {_now_str()}"
        )

        return self.send_message(header + body + footer)

    def send_startup_message(self, route_label: str, max_price: int, interval_hours: int):
        """Kirim pesan konfirmasi saat bot pertama kali dijalankan."""
        text = (
            f"✅ <b>Flight Monitor aktif!</b>\n\n"
            f"🛫 Rute: <b>{route_label}</b>\n"
            f"💸 Batas harga: <b>Rp {max_price:,.0f}</b>\n".replace(",", ".")
            + f"⏱ Cek setiap: <b>{interval_hours} jam</b>\n\n"
            f"Saya akan memberi tahu kamu jika ada tiket di bawah batas harga. ✈️"
        )
        return self.send_message(text)

    def send_no_results_alert(self, route_label: str):
        """Kirim pesan jika tidak ada penerbangan yang ditemukan sama sekali."""
        text = (
            f"ℹ️ <b>Tidak ada penerbangan ditemukan</b>\n"
            f"Rute: {route_label}\n"
            f"Akan dicek kembali sesuai jadwal."
        )
        return self.send_message(text)

    def test_connection(self) -> bool:
        """Test apakah bot bisa mengirim pesan."""
        try:
            resp = self._post("getMe", {})
            bot_name = resp.get("result", {}).get("username", "?")
            logger.info(f"[Telegram] Koneksi OK — bot: @{bot_name}")
            return True
        except Exception as e:
            logger.error(f"[Telegram] Koneksi gagal: {e}")
            return False


# ── Helper ────────────────────────────────────────────────────────────────────

def _now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%d %b %Y, %H:%M WIB")
