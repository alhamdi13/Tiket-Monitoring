"""
main.py - Entry Point Utama Flight Price Monitor Pro.
Menyediakan REST API berbasis FastAPI, server file statis untuk Web Dashboard,
serta mengorkestrasi Telegram Interactive Bot dan Automated Background Scheduler.
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database
from config import cfg
from notifier import TelegramNotifier
from scheduler import scheduler_service
from telegram_bot import telegram_bot_service

# Logging Setup
logging.basicConfig(
    level=getattr(logging, cfg.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Inisialisasi Database SQLite
    logger.info("Initializing SQLite database...")
    database.init_db()

    # 2. Start Background Scheduler & Telegram Bot
    logger.info("Starting Background Scheduler...")
    scheduler_service.start()

    logger.info("Starting Telegram Interactive Bot Polling...")
    telegram_bot_service.start()

    yield

    # Cleanup saat shutdown
    scheduler_service.stop()
    telegram_bot_service.stop()
    logger.info("Server stopped.")


app = FastAPI(
    title="Flight Price Monitor Pro",
    description="Sistem Pemantauan Harga Tiket Pesawat All-in-One",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# PYDANTIC SCHEMAS
# ==========================================

class RouteCreateRequest(BaseModel):
    origin: str
    destination: str
    max_price_idr: int
    days_ahead: int = 14
    label: Optional[str] = ""
    check_interval_hours: int = 4


class RouteUpdateRequest(BaseModel):
    origin: str
    destination: str
    max_price_idr: int
    days_ahead: int
    label: Optional[str] = ""
    check_interval_hours: int = 4


class SettingsUpdateRequest(BaseModel):
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    auto_scan_enabled: Optional[bool] = None
    mock_simulation_enabled: Optional[bool] = None


class TestTelegramRequest(BaseModel):
    token: Optional[str] = None
    chat_id: Optional[str] = None


# ==========================================
# REST API ENDPOINTS
# ==========================================

@app.get("/api/status")
def get_system_status():
    """Mengambil status real-time sistem, scheduler, bot Telegram, dan statistik database."""
    stats = database.get_dashboard_stats()
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "scheduler": {
            "running": scheduler_service.running,
            "is_scanning": scheduler_service.is_scanning,
            "last_scan": scheduler_service.last_scan_time.isoformat() if scheduler_service.last_scan_time else None,
            "auto_scan_enabled": cfg.auto_scan_enabled
        },
        "telegram": {
            "token_configured": bool(cfg.telegram_bot_token),
            "chat_id_configured": bool(cfg.telegram_chat_id),
            "bot_listener_active": telegram_bot_service.running
        },
        "stats": stats
    }


@app.get("/api/routes")
def list_routes(active_only: bool = False):
    """Mendapatkan seluruh rute pantauan."""
    return database.get_routes(active_only=active_only)


@app.post("/api/routes")
def add_route(data: RouteCreateRequest):
    """Menambahkan rute baru ke pantauan."""
    if not data.origin or not data.destination:
        raise HTTPException(status_code=400, detail="Origin dan destination harus diisi")
    if data.max_price_idr <= 0:
        raise HTTPException(status_code=400, detail="Budget maksimal harus lebih besar dari 0")

    created = database.create_route(
        origin=data.origin,
        destination=data.destination,
        max_price_idr=data.max_price_idr,
        days_ahead=data.days_ahead,
        label=data.label or f"{data.origin.upper()} ➔ {data.destination.upper()}",
        check_interval_hours=data.check_interval_hours
    )
    return {"message": "Rute berhasil ditambahkan", "route": created}


@app.put("/api/routes/{route_id}")
def update_route(route_id: int, data: RouteUpdateRequest):
    """Memperbarui pengaturan rute pantauan."""
    existing = database.get_route_by_id(route_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rute tidak ditemukan")

    updated = database.update_route(
        route_id=route_id,
        origin=data.origin,
        destination=data.destination,
        max_price_idr=data.max_price_idr,
        days_ahead=data.days_ahead,
        label=data.label or f"{data.origin.upper()} ➔ {data.destination.upper()}",
        check_interval_hours=data.check_interval_hours
    )
    return {"message": "Rute berhasil diperbarui", "route": updated}


@app.delete("/api/routes/{route_id}")
def delete_route(route_id: int):
    """Menghapus rute dari pantauan."""
    success = database.delete_route(route_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rute tidak ditemukan")
    return {"message": "Rute berhasil dihapus"}


@app.post("/api/routes/{route_id}/toggle")
def toggle_route(route_id: int):
    """Mengaktifkan atau menonaktifkan rute pantauan."""
    updated = database.toggle_route(route_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Rute tidak ditemukan")
    return {"message": "Status rute berhasil diubah", "route": updated}


@app.post("/api/routes/{route_id}/scan")
def scan_single_route(route_id: int, bg_tasks: BackgroundTasks):
    """Memicu scan manual untuk 1 rute tertentu di background."""
    route = database.get_route_by_id(route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Rute tidak ditemukan")

    bg_tasks.add_task(scheduler_service.scan_route, route_id)
    return {"message": f"Pemindaian rute {route['label']} sedang berjalan di background"}


@app.post("/api/scan-all")
def scan_all_routes(bg_tasks: BackgroundTasks):
    """Memicu scan instan untuk seluruh rute aktif di background."""
    if scheduler_service.is_scanning:
        return {"message": "Pemindaian sudah sedang berjalan di background"}

    bg_tasks.add_task(scheduler_service.scan_all_routes)
    return {"message": "Pemindaian menyeluruh semua rute berhasil dipicu"}


@app.get("/api/analytics/trend")
def get_route_price_trend(route_id: int):
    """Mengambil data tren harga historis per hari untuk visualisasi Chart.js."""
    route = database.get_route_by_id(route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Rute tidak ditemukan")

    data = database.get_price_trends(route_id)
    data["route"] = route
    return data


@app.get("/api/analytics/calendar")
def get_route_lowest_fare_calendar(route_id: int, days: int = 30):
    """Mengambil matriks kalender harga termurah 30 hari ke depan."""
    route = database.get_route_by_id(route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Rute tidak ditemukan")

    calendar = database.get_lowest_fare_calendar(route_id, days_ahead=days)
    return {"route": route, "calendar": calendar}


@app.get("/api/flights")
def get_flights(route_id: Optional[int] = None, flight_date: Optional[str] = None, limit: int = 50):
    """Mengambil daftar riwayat penerbangan hasil scan terbaru."""
    return database.get_latest_flights(route_id=route_id, flight_date=flight_date, limit=limit)


@app.get("/api/notifications")
def get_notifications_log(limit: int = 50):
    """Mengambil log notifikasi alert yang pernah dikirim."""
    return database.get_notifications(limit=limit)


@app.get("/api/settings")
def get_settings():
    """Mengambil konfigurasi sistem."""
    return database.get_settings()


@app.post("/api/settings")
def update_settings(data: SettingsUpdateRequest):
    """Menyimpan konfigurasi sistem."""
    if data.telegram_bot_token is not None:
        database.set_setting("telegram_bot_token", data.telegram_bot_token.strip())
    if data.telegram_chat_id is not None:
        database.set_setting("telegram_chat_id", data.telegram_chat_id.strip())
    if data.auto_scan_enabled is not None:
        database.set_setting("auto_scan_enabled", "true" if data.auto_scan_enabled else "false")
    if data.mock_simulation_enabled is not None:
        database.set_setting("mock_simulation_enabled", "true" if data.mock_simulation_enabled else "false")

    return {"message": "Pengaturan berhasil disimpan", "settings": database.get_settings()}


@app.post("/api/test-telegram")
def test_telegram_connection(data: TestTelegramRequest):
    """Menguji kredensial bot Telegram & mengirim pesan verifikasi."""
    notifier = TelegramNotifier()
    result = notifier.test_connection(token=data.token, chat_id=data.chat_id)
    return result


@app.get("/api/airports")
def get_airports_list():
    """Mengembalikan daftar bandara dengan kode IATA."""
    airports_path = os.path.join(BASE_DIR, "airports.json")
    if os.path.exists(airports_path):
        with open(airports_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ==========================================
# STATIC FILES & SPA SERVING
# ==========================================

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_dashboard():
    """Melayani antarmuka Web Dashboard."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h1>Dashboard sedang dimuat...</h1>")


if __name__ == "__main__":
    uvicorn.run("main:app", host=cfg.host, port=cfg.port, reload=True)
