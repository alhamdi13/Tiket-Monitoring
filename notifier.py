"""
notifier.py - Telegram Push Notifier untuk Flight Price Monitor Pro.
Mengirimkan notifikasi tiket murah dengan format pesan HTML yang rapi, tombol direct booking, dan logging ke database.
"""

import logging
from datetime import datetime
from typing import List, Optional
import requests

import database
from scraper import FlightResult

logger = logging.getLogger("notifier")

AIRLINE_EMOJIS = {
    "garuda": "🦅",
    "lion": "🦁",
    "batik": "👑",
    "citilink": "🟢",
    "airasia": "🔴",
    "super air jet": "⚡",
    "pelita": "🔵",
    "sriwijaya": "⭐",
    "transnusa": "✈️",
    "wings": "🕊️",
}


def get_airline_emoji(name: str) -> str:
    name_lower = name.lower()
    for k, emoji in AIRLINE_EMOJIS.items():
        if k in name_lower:
            return emoji
    return "✈️"


def format_duration(minutes: int) -> str:
    if not minutes:
        return ""
    h, m = divmod(minutes, 60)
    return f"{h}j {m}m" if m else f"{h}j"


class TelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self._token = bot_token
        self._chat_id = chat_id

    @property
    def token(self) -> str:
        if self._token:
            return self._token
        return database.get_setting("telegram_bot_token")

    @property
    def chat_id(self) -> str:
        if self._chat_id:
            return self._chat_id
        return database.get_setting("telegram_chat_id")

    def _post(self, method: str, payload: dict) -> dict:
        if not self.token:
            raise ValueError("Token Telegram bot belum disetel!")
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        resp = requests.post(url, json=payload, timeout=12)
        resp.raise_for_status()
        return resp.json()

    def send_message(self, text: str, parse_mode: str = "HTML", route_id: Optional[int] = None, price_idr: int = 0) -> bool:
        if not self.token or not self.chat_id:
            logger.warning("[Telegram] Token atau Chat ID belum disetel, pesan tidak dikirim.")
            return False

        try:
            self._post("sendMessage", {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False,
            })
            logger.info("[Telegram] Pesan berhasil dikirim ke Telegram")
            database.log_notification(route_id, text, price_idr, "SUCCESS")
            return True
        except Exception as e:
            logger.error(f"[Telegram] Gagal mengirim pesan: {e}")
            database.log_notification(route_id, f"Error: {e}\n{text}", price_idr, "FAILED")
            return False

    def send_cheap_alert(self, flights: List[FlightResult], route_label: str, max_price: int, route_id: Optional[int] = None) -> bool:
        if not flights:
            return False

        cheapest = flights[0]
        count = len(flights)
        formatted_max = f"Rp {max_price:,.0f}".replace(",", ".")
        now_str = datetime.now().strftime("%d %b %Y, %H:%M WIB")

        # Hitung perkiraan diskon
        header = (
            f"🎉 <b>TIKET MURAH DITEMUKAN!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Rute:</b> {route_label}\n"
            f"📅 <b>Tanggal:</b> {cheapest.date}\n"
            f"🎯 <b>Target Budget:</b> {formatted_max}\n"
        )

        body = ""
        for i, f in enumerate(flights[:5], 1):
            emoji = get_airline_emoji(f.airline)
            dur_str = f" ({format_duration(f.duration_minutes)})" if f.duration_minutes else ""
            seats_str = f" | 💺 {f.seats_left} kursi" if f.seats_left else ""
            body += (
                f"\n<b>{i}. {emoji} {f.airline}</b> ({f.flight_number})\n"
                f"   🕒 {f.departure_time} ➔ {f.arrival_time}{dur_str}\n"
                f"   💰 <b>{f.price_formatted}</b>{seats_str}\n"
                f"   🔗 <a href='{f.booking_url}'>Cek & Pesan di Traveloka</a>\n"
            )

        if count > 5:
            body += f"\n<i>...dan {count - 5} opsi penerbangan murah lainnya</i>\n"

        footer = (
            f"\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>Waktu Scan: {now_str}</i>"
        )

        full_message = header + body + footer
        return self.send_message(full_message, route_id=route_id, price_idr=cheapest.price_idr)

    def test_connection(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> dict:
        use_token = token or self.token
        use_chat = chat_id or self.chat_id
        if not use_token:
            return {"success": False, "message": "Token bot belum diisi."}

        try:
            url = f"https://api.telegram.org/bot{use_token}/getMe"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if not data.get("ok"):
                return {"success": False, "message": f"Token tidak valid: {data.get('description')}"}

            bot_user = data["result"]["username"]

            # Coba kirim pesan jika chat_id diberikan
            if use_chat:
                send_url = f"https://api.telegram.org/bot{use_token}/sendMessage"
                s_resp = requests.post(send_url, json={
                    "chat_id": use_chat,
                    "text": f"✅ <b>Tes Koneksi Berhasil!</b>\nFlight Price Monitor Pro terhubung ke bot <b>@{bot_user}</b>.",
                    "parse_mode": "HTML"
                }, timeout=10)
                s_data = s_resp.json()
                if not s_data.get("ok"):
                    return {"success": False, "message": f"Bot valid (@{bot_user}), tapi gagal kirim ke Chat ID: {s_data.get('description')}"}

            return {
                "success": True,
                "bot_username": bot_user,
                "message": f"Terhubung ke @{bot_user}" + (f" dan pesan tes terkirim ke Chat ID {use_chat}" if use_chat else "")
            }
        except Exception as e:
            return {"success": False, "message": f"Koneksi gagal: {str(e)}"}
