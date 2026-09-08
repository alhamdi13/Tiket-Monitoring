"""
telegram_bot.py - Telegram Interactive 2-Way Bot Handler untuk Flight Price Monitor Pro.
Menerima dan memproses perintah interaktif Telegram (/start, /cek, /tambah, /list, /hapus, /scan, /status)
melalui background polling thread tanpa memerlukan webhook atau port forwarding publik.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional
import requests

import database
from config import cfg
from scraper import FlightScraper

logger = logging.getLogger("telegram_bot")


class TelegramInteractiveBot:
    def __init__(self):
        self.scraper = FlightScraper()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_update_id = 0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramBotPolling")
        self.thread.start()
        logger.info("[TelegramBot] Interactive Bot Poller dimulai...")

    def stop(self):
        self.running = False

    def _poll_loop(self):
        while self.running:
            token = cfg.telegram_bot_token
            if not token:
                time.sleep(5)
                continue

            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates"
                params = {
                    "offset": self.last_update_id + 1,
                    "timeout": 15,
                    "allowed_updates": ["message"]
                }
                resp = requests.get(url, params=params, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        for update in data.get("result", []):
                            self.last_update_id = update["update_id"]
                            if "message" in update and "text" in update["message"]:
                                self._handle_message(token, update["message"])
                elif resp.status_code in (401, 404):
                    logger.warning("[TelegramBot] Token bot tidak valid, menunggu update...")
                    time.sleep(10)
            except requests.exceptions.Timeout:
                pass
            except Exception as e:
                logger.error(f"[TelegramBot] Polling error: {e}")
                time.sleep(3)

    def _reply(self, token: str, chat_id: int, text: str, parse_mode: str = "HTML"):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False
            }, timeout=10)
        except Exception as e:
            logger.error(f"[TelegramBot] Gagal balas pesan: {e}")

    def _handle_message(self, token: str, msg: dict):
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        first_name = msg.get("from", {}).get("first_name", "Pengguna")

        if not text.startswith("/"):
            return

        parts = text.split()
        cmd = parts[0].lower().split("@")[0]  # Menghapus tag @bot jika ada
        args = parts[1:]

        logger.info(f"[TelegramBot] Command diterima dari {first_name} ({chat_id}): {text}")

        # Routing Perintah
        if cmd in ("/start", "/help", "/menu"):
            self._cmd_help(token, chat_id, first_name)
        elif cmd in ("/cek", "/check", "/cari"):
            self._cmd_cek(token, chat_id, args)
        elif cmd in ("/tambah", "/add", "/pantau"):
            self._cmd_tambah(token, chat_id, args)
        elif cmd in ("/list", "/daftar", "/rute"):
            self._cmd_list(token, chat_id)
        elif cmd in ("/hapus", "/delete", "/del"):
            self._cmd_hapus(token, chat_id, args)
        elif cmd in ("/scan", "/sync"):
            self._cmd_scan(token, chat_id)
        elif cmd in ("/status", "/info"):
            self._cmd_status(token, chat_id)
        else:
            self._reply(token, chat_id, f"❓ Perintah <code>{cmd}</code> tidak dikenal.\nKetik <code>/help</code> untuk panduan.")

    def _cmd_help(self, token: str, chat_id: int, name: str):
        msg = (
            f"👋 <b>Halo, {name}!</b>\n"
            f"Selamat datang di <b>Flight Price Monitor Pro</b> ✈️\n\n"
            f"<b>Daftar Perintah:</b>\n"
            f"• <code>/cek [ASAL] [TUJUAN] [YYYY-MM-DD]</code>\n"
            f"  <i>Contoh:</i> <code>/cek CGK DPS 2026-10-15</code>\n\n"
            f"• <code>/tambah [ASAL] [TUJUAN] [MAX_HARGA] [HARI]</code>\n"
            f"  <i>Contoh:</i> <code>/tambah SUB DPS 600000 14</code>\n\n"
            f"• <code>/list</code> — Lihat semua rute yang sedang dipantau\n"
            f"• <code>/hapus [ID]</code> — Hapus rute pantauan (misal: <code>/hapus 2</code>)\n"
            f"• <code>/scan</code> — Jalankan pemindaian harga sekarang\n"
            f"• <code>/status</code> — Cek status sistem & database\n\n"
            f"🌐 Dashboard Web: <code>http://localhost:8000</code>"
        )
        self._reply(token, chat_id, msg)

    def _cmd_cek(self, token: str, chat_id: int, args: list):
        if len(args) < 2:
            self._reply(token, chat_id, "⚠️ <b>Format salah!</b>\nGunakan: <code>/cek [ASAL] [TUJUAN] [YYYY-MM-DD]</code>\nContoh: <code>/cek CGK DPS 2026-10-20</code>")
            return

        origin = args[0].upper()
        destination = args[1].upper()

        if len(args) >= 3:
            try:
                target_date = datetime.strptime(args[2], "%Y-%m-%d")
            except ValueError:
                self._reply(token, chat_id, "⚠️ Format tanggal salah! Gunakan format <code>YYYY-MM-DD</code> (contoh: <code>2026-10-20</code>)")
                return
        else:
            target_date = datetime.now() + timedelta(days=7)

        date_str = target_date.strftime("%Y-%m-%d")
        self._reply(token, chat_id, f"🔍 <i>Sedang mencari penerbangan {origin} ➔ {destination} pada {date_str}...</i>")

        try:
            flights = self.scraper.search(origin, destination, target_date)
            if not flights:
                self._reply(token, chat_id, f"❌ Tidak ditemukan penerbangan untuk rute <b>{origin} ➔ {destination}</b> pada <b>{date_str}</b>.")
                return

            msg = (
                f"✈️ <b>Hasil Pencarian Tiket</b>\n"
                f"📍 <b>{origin} ➔ {destination}</b> ({date_str})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            for i, f in enumerate(flights[:5], 1):
                msg += (
                    f"<b>{i}. {f.airline}</b> ({f.flight_number})\n"
                    f"   🕒 {f.departure_time} ➔ {f.arrival_time}\n"
                    f"   💰 <b>{f.price_formatted}</b>\n"
                    f"   🔗 <a href='{f.booking_url}'>Lihat di Traveloka</a>\n\n"
                )
            self._reply(token, chat_id, msg)
        except Exception as e:
            self._reply(token, chat_id, f"❌ Gagal mencari tiket: {e}")

    def _cmd_tambah(self, token: str, chat_id: int, args: list):
        if len(args) < 3:
            self._reply(token, chat_id, "⚠️ <b>Format salah!</b>\nGunakan: <code>/tambah [ASAL] [TUJUAN] [MAX_HARGA] [HARI_KE_DEPAN]</code>\nContoh: <code>/tambah SUB DPS 650000 14</code>")
            return

        origin = args[0].upper()
        destination = args[1].upper()
        try:
            max_price = int(args[2].replace(".", "").replace(",", "").replace("Rp", "").replace("rp", ""))
            days_ahead = int(args[3]) if len(args) >= 4 else 14
        except ValueError:
            self._reply(token, chat_id, "⚠️ Harga atau jumlah hari harus berupa angka!")
            return

        new_route = database.create_route(
            origin=origin,
            destination=destination,
            max_price_idr=max_price,
            days_ahead=days_ahead,
            label=f"{origin} ➔ {destination}"
        )

        formatted_price = f"Rp {max_price:,.0f}".replace(",", ".")
        self._reply(token, chat_id, (
            f"✅ <b>Rute Berhasil Ditambahkan!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>ID Rute:</b> <code>{new_route['id']}</code>\n"
            f"📍 <b>Rute:</b> {new_route['label']}\n"
            f"🎯 <b>Target Maks:</b> {formatted_price}\n"
            f"📅 <b>Rentang Cek:</b> {days_ahead} hari ke depan\n\n"
            f"<i>Bot akan otomatis memberi tahu jika ada harga di bawah target!</i>"
        ))

    def _cmd_list(self, token: str, chat_id: int):
        routes = database.get_routes()
        if not routes:
            self._reply(token, chat_id, "📋 Belum ada rute yang dipantau.\nGunakan <code>/tambah [ASAL] [TUJUAN] [HARGA]</code> untuk menambahkan.")
            return

        msg = "📋 <b>Daftar Rute Pantauan:</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        for r in routes:
            status_emoji = "🟢" if r["is_active"] else "⚪"
            p_format = f"Rp {r['max_price_idr']:,.0f}".replace(",", ".")
            msg += (
                f"{status_emoji} <b>[ID {r['id']}] {r['label']}</b>\n"
                f"   🎯 Max: {p_format} | 📅 {r['days_ahead']} hari\n"
                f"   ⚙️ Status: {'Aktif' if r['is_active'] else 'Nonaktif'}\n\n"
            )
        msg += "<i>Gunakan /hapus [ID] untuk menghapus rute.</i>"
        self._reply(token, chat_id, msg)

    def _cmd_hapus(self, token: str, chat_id: int, args: list):
        if not args:
            self._reply(token, chat_id, "⚠️ Masukkan ID rute yang ingin dihapus!\nContoh: <code>/hapus 2</code>")
            return
        try:
            route_id = int(args[0])
            route = database.get_route_by_id(route_id)
            if not route:
                self._reply(token, chat_id, f"❌ Rute dengan ID <b>{route_id}</b> tidak ditemukan.")
                return

            database.delete_route(route_id)
            self._reply(token, chat_id, f"🗑️ Rute <b>[ID {route_id}] {route['label']}</b> berhasil dihapus!")
        except ValueError:
            self._reply(token, chat_id, "⚠️ ID rute harus berupa angka!")

    def _cmd_scan(self, token: str, chat_id: int):
        self._reply(token, chat_id, "🔄 <b>Memulai pemindaian manual semua rute...</b>\nKamu akan menerima notifikasi jika ditemukan tiket murah.")
        import scheduler
        threading.Thread(target=scheduler.scan_all_routes, daemon=True).start()

    def _cmd_status(self, token: str, chat_id: int):
        stats = database.get_dashboard_stats()
        cheapest_format = f"Rp {stats['cheapest_price_idr']:,.0f}".replace(",", ".") if stats['cheapest_price_idr'] else "Belum ada"
        msg = (
            f"📊 <b>Status Flight Monitor Pro</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 Total Rute: <b>{stats['total_routes']}</b> ({stats['active_routes']} aktif)\n"
            f"✈️ Total Tiket Terpantau: <b>{stats['total_tracked_flights']}</b>\n"
            f"💰 Tiket Termurah Tercatat: <b>{cheapest_format}</b>\n"
            f"🔔 Notifikasi Terkirim: <b>{stats['total_notifications']}</b>\n"
            f"⚙️ Auto-Scan: <b>{'Aktif' if cfg.auto_scan_enabled else 'Nonaktif'}</b>\n"
        )
        self._reply(token, chat_id, msg)


# Singleton Interactive Bot
telegram_bot_service = TelegramInteractiveBot()
