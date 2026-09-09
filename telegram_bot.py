"""
telegram_bot.py - Telegram Interactive 2-Way Bot Handler untuk Flight Price Monitor Pro.
Mendukung perintah pemantauan tanggal spesifik (/pantau), pencarian on-demand (/cek), dan manajemen rute.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional
import requests

import database
from config import cfg
from notifier import get_airline_emoji
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
                    time.sleep(10)
            except Exception as e:
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
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        logger.info(f"[TelegramBot] Command diterima dari {first_name} ({chat_id}): {text}")

        if cmd in ("/start", "/help", "/menu"):
            self._cmd_help(token, chat_id, first_name)
        elif cmd in ("/transit", "/connecting", "/via"):
            self._cmd_transit(token, chat_id, args)
        elif cmd in ("/pantau", "/target"):
            self._cmd_pantau_tanggal(token, chat_id, args)
        elif cmd in ("/cek", "/check", "/cari"):
            self._cmd_cek(token, chat_id, args)
        elif cmd in ("/tambah", "/add"):
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
            f"<b>Fitur Cerdas Penerbangan Transit (Connecting):</b>\n"
            f"• <code>/transit [ASAL] [HUB] [TUJUAN] [YYYY-MM-DD]</code>\n"
            f"  <i>Contoh:</i> <code>/transit BDJ CGK PDG 2026-10-25</code>\n"
            f"• <code>/transit [ASAL] [TUJUAN] [YYYY-MM-DD]</code> (Otomatis cari hub terbaik)\n"
            f"  <i>Contoh:</i> <code>/transit BDJ PDG 2026-10-25</code>\n"
            f"  <i>(Dilengkapi proteksi waktu transit aman ≥ 75 menit agar tidak salah beli tiket!)</i>\n\n"
            f"<b>Fitur Pemantauan Tanggal Spesifik:</b>\n"
            f"• <code>/pantau [ASAL] [TUJUAN] [YYYY-MM-DD] [MAX_HARGA]</code>\n"
            f"  <i>Contoh:</i> <code>/pantau CGK DPS 2026-10-25 550000</code>\n\n"
            f"<b>Perintah Lainnya:</b>\n"
            f"• <code>/cek CGK DPS 2026-10-25</code> — Cek harga langsung satu rute\n"
            f"• <code>/list</code> — Lihat seluruh rute pantauan\n"
            f"• <code>/hapus [ID]</code> — Hapus rute\n"
            f"• <code>/scan</code> — Trigger scan sekarang\n\n"
            f"🌐 Dashboard Web: <code>https://alhamdi13.github.io/Tiket-Monitoring/</code>"
        )
        self._reply(token, chat_id, msg)

    def _cmd_transit(self, token: str, chat_id: int, args: list):
        if len(args) < 2:
            self._reply(token, chat_id, (
                "⚠️ <b>Format perintah transit:</b>\n"
                "• <b>Dengan Hub:</b> <code>/transit [ASAL] [HUB] [TUJUAN] [YYYY-MM-DD]</code>\n"
                "  <i>Contoh:</i> <code>/transit BDJ CGK PDG 2026-10-25</code>\n\n"
                "• <b>Auto Hub:</b> <code>/transit [ASAL] [TUJUAN] [YYYY-MM-DD]</code>\n"
                "  <i>Contoh:</i> <code>/transit BDJ PDG 2026-10-25</code>"
            ))
            return

        origin = args[0].upper()
        hub = None
        destination = None
        date_str = None

        if len(args) >= 4:
            hub = args[1].upper()
            destination = args[2].upper()
            date_str = args[3]
        elif len(args) == 3:
            if "-" in args[2]:
                destination = args[1].upper()
                date_str = args[2]
            else:
                hub = args[1].upper()
                destination = args[2].upper()
                date_str = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        else:
            destination = args[1].upper()
            date_str = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            self._reply(token, chat_id, "⚠️ Format tanggal salah! Gunakan format <code>YYYY-MM-DD</code> (contoh: <code>2026-10-25</code>)")
            return

        hub_text = f" via <b>{hub}</b>" if hub else " (Pencarian Hub Otomatis)"
        self._reply(token, chat_id, f"🔍 <i>Menganalisis opsi penerbangan transit aman untuk <b>{origin} ➔ {destination}</b>{hub_text} pada {date_str}...</i>")

        try:
            connecting_results = self.scraper.search_connecting(origin, destination, target_date, hub=hub)
        except Exception as e:
            logger.error(f"Gagal mencari connecting flights: {e}")
            connecting_results = []

        if not connecting_results:
            self._reply(token, chat_id, (
                f"❌ <b>Tidak ditemukan kombinasi penerbangan transit yang aman</b> untuk rute {origin} ➔ {destination} pada {date_str}.\n\n"
                f"<i>Catatan: Sistem secara otomatis menolak jadwal dengan jeda transit < 75 menit agar tidak berisiko tertinggal pesawat.</i>"
            ))
            return

        msg = (
            f"✈️ <b>HASIL PENERBANGAN TRANSIT / CONNECTING</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Rute:</b> {origin} ➔ {destination}\n"
            f"📅 <b>Tanggal:</b> {date_str}\n"
            f"🛡️ <b>Proteksi Jadwal:</b> Waktu transit diverifikasi aman (≥ 75 menit)\n\n"
        )

        for i, c in enumerate(connecting_results[:4], 1):
            e1 = get_airline_emoji(c.leg1_airline)
            e2 = get_airline_emoji(c.leg2_airline)
            p1 = f"Rp {c.leg1_price_idr:,.0f}".replace(",", ".")
            p2 = f"Rp {c.leg2_price_idr:,.0f}".replace(",", ".")

            msg += (
                f"<b>{i}. {c.safety_rating}</b>\n"
                f"   💰 <b>Total Tarif: {c.total_price_formatted}</b> | ⏱️ {c.total_duration_formatted}\n"
                f"   🛫 <b>Leg 1 ({origin} ➔ {c.hub}):</b> {e1} {c.leg1_airline} ({c.leg1_flight_number})\n"
                f"      🕒 {c.leg1_departure_time} ➔ {c.leg1_arrival_time} | {p1}\n"
                f"      👉 <a href='{c.leg1_booking_url}'>Pesan Leg 1 di Traveloka</a>\n"
                f"   ⏳ <b>Transit di {c.hub}:</b> <b>{c.layover_formatted}</b>\n"
                f"   🛫 <b>Leg 2 ({c.hub} ➔ {destination}):</b> {e2} {c.leg2_airline} ({c.leg2_flight_number})\n"
                f"      🕒 {c.leg2_departure_time} ➔ {c.leg2_arrival_time} | {p2}\n"
                f"      👉 <a href='{c.leg2_booking_url}'>Pesan Leg 2 di Traveloka</a>\n"
                f"   🔗 <a href='{c.booking_url}'>Cek Tiket Terusan Traveloka</a> | <a href='{c.tiket_url}'>Tiket.com</a>\n\n"
            )

        msg += "━━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Tips: Waktu transit telah dihitung agar Anda sempat turun, ambil bagasi, & pindah terminal tanpa terburu-buru!</i>"
        self._reply(token, chat_id, msg)

    def _cmd_pantau_tanggal(self, token: str, chat_id: int, args: list):
        if len(args) < 4:
            self._reply(token, chat_id, (
                "⚠️ <b>Format salah!</b>\n"
                "Gunakan: <code>/pantau [ASAL] [TUJUAN] [YYYY-MM-DD] [MAX_HARGA]</code>\n\n"
                "<i>Contoh:</i> <code>/pantau CGK DPS 2026-10-25 550000</code>"
            ))
            return

        origin = args[0].upper()
        destination = args[1].upper()
        date_str = args[2]

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            self._reply(token, chat_id, "⚠️ Format tanggal salah! Gunakan format <code>YYYY-MM-DD</code> (contoh: <code>2026-10-25</code>)")
            return

        try:
            max_price = int(args[3].replace(".", "").replace(",", "").replace("Rp", "").replace("rp", ""))
        except ValueError:
            self._reply(token, chat_id, "⚠️ Harga harus berupa angka nominal Rupiah!")
            return

        route_label = f"{origin} ➔ {destination} ({date_str})"
        new_route = database.create_route(
            origin=origin,
            destination=destination,
            max_price_idr=max_price,
            target_date=date_str,
            label=route_label
        )

        formatted_price = f"Rp {max_price:,.0f}".replace(",", ".")
        self._reply(token, chat_id, f"🔍 <i>Memeriksa harga tiket awal untuk tanggal {date_str}...</i>")

        try:
            flights = self.scraper.search(origin, destination, target_date)
            initial_cheapest = flights[0].price_formatted if flights else "-"
        except Exception:
            initial_cheapest = "-"

        self._reply(token, chat_id, (
            f"🎯 <b>Pemantauan Tanggal Spesifik Berhasil Diaktifkan!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>ID Pantauan:</b> <code>{new_route['id']}</code>\n"
            f"📍 <b>Rute:</b> {origin} ➔ {destination}\n"
            f"📅 <b>Tanggal Target:</b> <b>{date_str}</b>\n"
            f"🎯 <b>Target Budget:</b> {formatted_price}\n"
            f"💰 <b>Harga Saat Ini:</b> {initial_cheapest}\n\n"
            f"🔔 <i>Bot akan otomatis mengirim notifikasi setiap ada tiket turun di bawah budget target!</i>"
        ))

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
                self._reply(token, chat_id, "⚠️ Format tanggal salah! Gunakan format <code>YYYY-MM-DD</code>")
                return
        else:
            target_date = datetime.now() + timedelta(days=7)

        date_str = target_date.strftime("%Y-%m-%d")
        self._reply(token, chat_id, f"🔍 <i>Mencari penerbangan {origin} ➔ {destination} ({date_str})...</i>")

        try:
            flights = self.scraper.search(origin, destination, target_date)
            if not flights:
                self._reply(token, chat_id, f"❌ Tidak ditemukan penerbangan untuk {origin} ➔ {destination} pada {date_str}.")
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
                    f"   🔗 <a href='{f.booking_url}'>Buka di Traveloka</a> | <a href='{f.tiket_url}'>Buka di Tiket.com</a>\n\n"
                )
            self._reply(token, chat_id, msg)
        except Exception as e:
            self._reply(token, chat_id, f"❌ Gagal mencari tiket: {e}")

    def _cmd_tambah(self, token: str, chat_id: int, args: list):
        if len(args) < 3:
            self._reply(token, chat_id, "⚠️ <b>Format:</b> <code>/tambah [ASAL] [TUJUAN] [MAX_HARGA] [HARI_KE_DEPAN]</code>\nContoh: <code>/tambah SUB DPS 650000 14</code>")
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
            f"🆔 <b>ID Rute:</b> <code>{new_route['id']}</code>\n"
            f"📍 <b>Rute:</b> {new_route['label']}\n"
            f"🎯 <b>Target Maks:</b> {formatted_price}\n"
            f"📅 <b>Rentang:</b> {days_ahead} hari ke depan"
        ))

    def _cmd_list(self, token: str, chat_id: int):
        routes = database.get_routes()
        if not routes:
            self._reply(token, chat_id, "📋 Belum ada rute yang dipantau.\nGunakan <code>/pantau</code> atau <code>/tambah</code> untuk mendaftarkan.")
            return

        msg = "📋 <b>Daftar Rute Pantauan:</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        for r in routes:
            status_emoji = "🟢" if r["is_active"] else "⚪"
            p_format = f"Rp {r['max_price_idr']:,.0f}".replace(",", ".")
            target_info = f"📅 <b>Target: {r['target_date']}</b>" if r.get("target_date") else f"📅 {r['days_ahead']} hari ke depan"
            msg += (
                f"{status_emoji} <b>[ID {r['id']}] {r['label']}</b>\n"
                f"   🎯 Max: {p_format} | {target_info}\n"
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
                self._reply(token, chat_id, f"❌ Rute ID <b>{route_id}</b> tidak ditemukan.")
                return

            database.delete_route(route_id)
            self._reply(token, chat_id, f"🗑️ Rute <b>[ID {route_id}] {route['label']}</b> berhasil dihapus!")
        except ValueError:
            self._reply(token, chat_id, "⚠️ ID rute harus berupa angka!")

    def _cmd_scan(self, token: str, chat_id: int):
        self._reply(token, chat_id, "🔄 <b>Memulai pemindaian sekarang...</b>\nKamu akan menerima notifikasi jika ditemukan tiket murah.")
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
        )
        self._reply(token, chat_id, msg)


telegram_bot_service = TelegramInteractiveBot()
