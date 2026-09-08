"""
database.py - Data Access Layer & SQLite Persistence untuk Flight Price Monitor Pro.
Mendukung sinkronisasi konfigurasi data/routes.json, target date, dan histori harga.
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flights_monitor.db")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            label TEXT,
            max_price_idr INTEGER NOT NULL DEFAULT 1000000,
            days_ahead INTEGER NOT NULL DEFAULT 14,
            target_date TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            check_interval_hours INTEGER NOT NULL DEFAULT 4,
            last_checked_at TEXT,
            last_price_idr INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(routes)")
    columns = [col["name"] for col in cursor.fetchall()]
    if "target_date" not in columns:
        cursor.execute("ALTER TABLE routes ADD COLUMN target_date TEXT")
    if "last_price_idr" not in columns:
        cursor.execute("ALTER TABLE routes ADD COLUMN last_price_idr INTEGER DEFAULT 0")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS flight_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER,
            airline TEXT NOT NULL,
            flight_number TEXT,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            flight_date TEXT NOT NULL,
            departure_time TEXT,
            arrival_time TEXT,
            duration_minutes INTEGER DEFAULT 0,
            price_idr INTEGER NOT NULL,
            seats_left INTEGER,
            source TEXT DEFAULT 'traveloka',
            recorded_at TEXT NOT NULL,
            FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_flight_history_lookup 
        ON flight_history (route_id, flight_date, price_idr)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER,
            message TEXT NOT NULL,
            price_idr INTEGER,
            sent_at TEXT NOT NULL,
            status TEXT DEFAULT 'SUCCESS',
            FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    default_settings = {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "auto_scan_enabled": "true",
        "default_scan_interval_hours": "4",
        "mock_simulation_enabled": "true"
    }

    for k, v in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    sync_routes_from_json_file(cursor)
    conn.commit()
    conn.close()


def sync_routes_from_json_file(cursor=None):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "data", "routes.json"),
        os.path.join(base_dir, "routes.json"),
        os.path.join(base_dir, "static", "data", "routes.json")
    ]
    json_path = None
    for c in candidates:
        if os.path.exists(c):
            json_path = c
            break

    should_close = False
    if cursor is None:
        conn = get_db()
        cursor = conn.cursor()
        should_close = True

    now_str = datetime.now().isoformat()

    if json_path:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                routes_data = json.load(f)
            if isinstance(routes_data, list) and len(routes_data) > 0:
                cursor.execute("DELETE FROM routes")
                records = []
                for r in routes_data:
                    orig = r.get("origin", "").strip().upper()
                    dest = r.get("destination", "").strip().upper()
                    target_d = r.get("target_date")
                    date_lbl = f" ({target_d})" if target_d else ""
                    label = r.get("label") or f"{orig} ➔ {dest}{date_lbl}"
                    records.append((
                        orig,
                        dest,
                        label,
                        int(r.get("max_price_idr", 1500000)),
                        int(r.get("days_ahead", 14)),
                        target_d,
                        int(r.get("is_active", 1)),
                        int(r.get("check_interval_hours", 4)),
                        now_str,
                        now_str
                    ))
                cursor.executemany("""
                    INSERT INTO routes (origin, destination, label, max_price_idr, days_ahead, target_date, is_active, check_interval_hours, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, records)
        except Exception as e:
            print(f"[DB] Warning reading {json_path}: {e}")
    else:
        cursor.execute("SELECT COUNT(*) FROM routes")
        if cursor.fetchone()[0] == 0:
            sample_routes = [
                ("BDJ", "PDG", "Banjarmasin ➔ Padang (Transit CGK)", 2500000, 14, "2026-10-25", 1, 4, now_str, now_str)
            ]
            cursor.executemany("""
                INSERT INTO routes (origin, destination, label, max_price_idr, days_ahead, target_date, is_active, check_interval_hours, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, sample_routes)

    if should_close:
        conn.commit()
        conn.close()


def get_routes(active_only: bool = False) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if active_only:
        cursor.execute("SELECT * FROM routes WHERE is_active = 1 ORDER BY id DESC")
    else:
        cursor.execute("SELECT * FROM routes ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_route_by_id(route_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM routes WHERE id = ?", (route_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_route(origin: str, destination: str, max_price_idr: int, days_ahead: int = 14,
              target_date: Optional[str] = None, label: str = "", check_interval_hours: int = 4) -> Dict[str, Any]:
    origin = origin.strip().upper()
    destination = destination.strip().upper()
    if not label:
        date_suffix = f" ({target_date})" if target_date else ""
        label = f"{origin} ➔ {destination}{date_suffix}"
    now_str = datetime.now().isoformat()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO routes (origin, destination, label, max_price_idr, days_ahead, target_date, is_active, check_interval_hours, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
    """, (origin, destination, label, max_price_idr, days_ahead, target_date, check_interval_hours, now_str, now_str))
    route_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return get_route_by_id(route_id)


def update_route(route_id: int, origin: str, destination: str, max_price_idr: int,
                 days_ahead: int, target_date: Optional[str] = None, label: str = "", check_interval_hours: int = 4) -> Optional[Dict[str, Any]]:
    origin = origin.strip().upper()
    destination = destination.strip().upper()
    if not label:
        date_suffix = f" ({target_date})" if target_date else ""
        label = f"{origin} ➔ {destination}{date_suffix}"
    now_str = datetime.now().isoformat()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE routes 
        SET origin = ?, destination = ?, label = ?, max_price_idr = ?, days_ahead = ?, target_date = ?, check_interval_hours = ?, updated_at = ?
        WHERE id = ?
    """, (origin, destination, label, max_price_idr, days_ahead, target_date, check_interval_hours, now_str, route_id))
    conn.commit()
    conn.close()
    return get_route_by_id(route_id)


def toggle_route(route_id: int, is_active: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if is_active is None:
        cursor.execute("UPDATE routes SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (route_id,))
    else:
        cursor.execute("UPDATE routes SET is_active = ? WHERE id = ?", (1 if is_active else 0, route_id))
    conn.commit()
    conn.close()
    return get_route_by_id(route_id)


def delete_route(route_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM flight_history WHERE route_id = ?", (route_id,))
    cursor.execute("DELETE FROM routes WHERE id = ?", (route_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def update_route_last_checked(route_id: int, last_price: int = 0):
    now_str = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE routes SET last_checked_at = ?, last_price_idr = ? WHERE id = ?", (now_str, last_price, route_id))
    conn.commit()
    conn.close()


def save_flight_results(route_id: int, flights: List[Any]):
    if not flights:
        return
    now_str = datetime.now().isoformat()
    records = []
    for f in flights:
        records.append((
            route_id,
            getattr(f, 'airline', 'Unknown'),
            getattr(f, 'flight_number', '-'),
            getattr(f, 'origin', ''),
            getattr(f, 'destination', ''),
            getattr(f, 'date', ''),
            getattr(f, 'departure_time', ''),
            getattr(f, 'arrival_time', ''),
            getattr(f, 'duration_minutes', 0),
            getattr(f, 'price_idr', 0),
            getattr(f, 'seats_left', None),
            getattr(f, 'source', 'traveloka'),
            now_str
        ))

    conn = get_db()
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT INTO flight_history (
            route_id, airline, flight_number, origin, destination,
            flight_date, departure_time, arrival_time, duration_minutes,
            price_idr, seats_left, source, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, records)
    conn.commit()
    conn.close()


def get_latest_flights(route_id: Optional[int] = None, flight_date: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT fh.*, r.label as route_label, r.max_price_idr 
        FROM flight_history fh
        LEFT JOIN routes r ON fh.route_id = r.id
        WHERE 1=1
    """
    params = []
    if route_id:
        query += " AND fh.route_id = ?"
        params.append(route_id)
    if flight_date:
        query += " AND fh.flight_date = ?"
        params.append(flight_date)

    query += " ORDER BY fh.recorded_at DESC, fh.price_idr ASC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_price_trends(route_id: int) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            flight_date,
            MIN(price_idr) as min_price,
            AVG(price_idr) as avg_price,
            MAX(price_idr) as max_price,
            COUNT(*) as total_flights
        FROM flight_history
        WHERE route_id = ?
        GROUP BY flight_date
        ORDER BY flight_date ASC
    """, (route_id,))
    rows = cursor.fetchall()

    cursor.execute("""
        SELECT airline, MIN(price_idr) as min_price, COUNT(*) as flight_count
        FROM flight_history
        WHERE route_id = ?
        GROUP BY airline
        ORDER BY min_price ASC
    """, (route_id,))
    airline_rows = cursor.fetchall()
    conn.close()

    labels = [r["flight_date"] for r in rows]
    min_prices = [r["min_price"] for r in rows]
    avg_prices = [int(r["avg_price"]) for r in rows]

    return {
        "dates": labels,
        "min_prices": min_prices,
        "avg_prices": avg_prices,
        "airline_breakdown": [dict(a) for a in airline_rows],
        "summary": [dict(r) for r in rows]
    }


def get_lowest_fare_calendar(route_id: int, days_ahead: int = 30) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            flight_date,
            MIN(price_idr) as cheapest_price,
            airline,
            flight_number,
            departure_time,
            duration_minutes,
            source
        FROM flight_history
        WHERE route_id = ?
        GROUP BY flight_date
        ORDER BY flight_date ASC
    """, (route_id,))
    rows = cursor.fetchall()
    conn.close()

    result_map = {r["flight_date"]: dict(r) for r in rows}
    calendar = []
    today = datetime.now()

    for i in range(1, days_ahead + 1):
        target = today + timedelta(days=i)
        d_str = target.strftime("%Y-%m-%d")
        if d_str in result_map:
            calendar.append(result_map[d_str])
        else:
            calendar.append({
                "flight_date": d_str,
                "cheapest_price": None,
                "airline": "-",
                "flight_number": "-",
                "departure_time": "-",
                "duration_minutes": 0,
                "source": None
            })

    return calendar


def log_notification(route_id: Optional[int], message: str, price_idr: int, status: str = "SUCCESS"):
    now_str = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notifications_log (route_id, message, price_idr, sent_at, status)
        VALUES (?, ?, ?, ?, ?)
    """, (route_id, message, price_idr, now_str, status))
    conn.commit()
    conn.close()


def get_notifications(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.*, r.label as route_label 
        FROM notifications_log n
        LEFT JOIN routes r ON n.route_id = r.id
        ORDER BY n.sent_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_settings() -> Dict[str, str]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def get_setting(key: str, default: str = "") -> str:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def get_dashboard_stats() -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM routes")
    total_routes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM routes WHERE is_active = 1")
    active_routes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM flight_history")
    total_tracked = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(price_idr) FROM flight_history")
    row_min = cursor.fetchone()[0]
    cheapest_overall = row_min if row_min else 0

    cursor.execute("SELECT COUNT(*) FROM notifications_log")
    total_notifs = cursor.fetchone()[0]

    conn.close()

    return {
        "total_routes": total_routes,
        "active_routes": active_routes,
        "total_tracked_flights": total_tracked,
        "cheapest_price_idr": cheapest_overall,
        "total_notifications": total_notifs
    }
