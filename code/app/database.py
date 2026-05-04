import aiosqlite
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta

from .config import DB_PATH, DATA_DIR, IMAGES_DIR, SERVICE_IMAGES_DIR, FEEDBACK_IMAGES_DIR, EXPORTS_DIR
from .date_utils import normalize_date_to_iso

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    price INTEGER NOT NULL,
    duration INTEGER NOT NULL,
    photo_file_id TEXT
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    first_name TEXT,
    last_name TEXT,
    phone TEXT
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT NOT NULL,
    FOREIGN KEY(client_id) REFERENCES clients(id),
    FOREIGN KEY(service_id) REFERENCES services(id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id INTEGER,
    telegram_id INTEGER,
    comment TEXT,
    photo_filename TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(appointment_id) REFERENCES appointments(id)
);

CREATE TABLE IF NOT EXISTS work_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_date TEXT NOT NULL UNIQUE,
    is_working INTEGER NOT NULL DEFAULT 1,
    note TEXT
);

CREATE TABLE IF NOT EXISTS unavailable_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_date TEXT NOT NULL,
    slot_time TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(slot_date, slot_time)
);

CREATE TABLE IF NOT EXISTS salon_info (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS schedule_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS banned_users (
    telegram_id INTEGER PRIMARY KEY,
    reason TEXT,
    banned_at TEXT NOT NULL,
    banned_by INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1
);

-- ──── INDEXES FOR OPTIMIZATION ────
CREATE INDEX IF NOT EXISTS idx_appointments_date_status 
    ON appointments(appointment_date, status);
CREATE INDEX IF NOT EXISTS idx_appointments_created_at 
    ON appointments(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_created_at 
    ON feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_unavailable_slots_date 
    ON unavailable_slots(slot_date);
CREATE INDEX IF NOT EXISTS idx_work_days_date 
    ON work_days(work_date);
"""
logger = logging.getLogger(__name__)

async def normalize_stored_dates(connection) -> None:
    """Normalize legacy DD-MM-YYYY values in storage to ISO format."""
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT value FROM schedule_settings WHERE key = 'cycle_start_date'")
        row = await cursor.fetchone()
        if row and row[0]:
            normalized = normalize_date_to_iso(row[0])
            if normalized != row[0]:
                await cursor.execute(
                    "UPDATE schedule_settings SET value = ? WHERE key = 'cycle_start_date'",
                    (normalized,),
                )

        await cursor.execute("SELECT id, appointment_date FROM appointments")
        for row_id, appointment_date in await cursor.fetchall():
            normalized = normalize_date_to_iso(appointment_date)
            if normalized != appointment_date:
                await cursor.execute(
                    "UPDATE appointments SET appointment_date = ? WHERE id = ?",
                    (normalized, row_id),
                )

        await cursor.execute("SELECT id, work_date, is_working, note FROM work_days")
        for row_id, work_date, is_working, note in await cursor.fetchall():
            normalized = normalize_date_to_iso(work_date)
            if normalized != work_date:
                await cursor.execute("DELETE FROM work_days WHERE id = ?", (row_id,))
                await cursor.execute(
                    "INSERT OR REPLACE INTO work_days (work_date, is_working, note) VALUES (?, ?, ?)",
                    (normalized, is_working, note),
                )

        await cursor.execute("SELECT id, slot_date, slot_time, reason, created_at FROM unavailable_slots")
        for row_id, slot_date, slot_time, reason, created_at in await cursor.fetchall():
            normalized = normalize_date_to_iso(slot_date)
            if normalized != slot_date:
                await cursor.execute("DELETE FROM unavailable_slots WHERE id = ?", (row_id,))
                await cursor.execute(
                    "INSERT OR REPLACE INTO unavailable_slots (slot_date, slot_time, reason, created_at) VALUES (?, ?, ?, ?)",
                    (normalized, slot_time, reason, created_at),
                )

        await connection.commit()

def init_data_dirs() -> None:
    """Initialize all data directories."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    SERVICE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    FEEDBACK_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    init_data_dirs()
    database_path = Path(DB_PATH)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(database_path) as connection:
        # Enable WAL mode for better concurrency support
        await connection.execute("PRAGMA journal_mode=WAL")
        await connection.commit()
        
        await connection.executescript(SCHEMA_SQL)
        await connection.commit()
        
        # Migration: add photo_filename column to feedback if it doesn't exist
        async with connection.cursor() as cursor:
            try:
                await cursor.execute("PRAGMA table_info(feedback)")
                columns = await cursor.fetchall()
                column_names = [row[1] for row in columns]
                if 'photo_filename' not in column_names:
                    await cursor.execute("ALTER TABLE feedback ADD COLUMN photo_filename TEXT")
                    await connection.commit()
            except Exception:
                pass
        
        # Migration: add reminder tracking columns to appointments
        async with connection.cursor() as cursor:
            try:
                await cursor.execute("PRAGMA table_info(appointments)")
                columns = await cursor.fetchall()
                column_names = [row[1] for row in columns]
                if 'reminder_sent' not in column_names:
                    await cursor.execute("ALTER TABLE appointments ADD COLUMN reminder_sent INTEGER DEFAULT 0")
                    await connection.commit()
                if 'completion_reminder_sent' not in column_names:
                    await cursor.execute("ALTER TABLE appointments ADD COLUMN completion_reminder_sent INTEGER DEFAULT 0")
                    await connection.commit()
                if 'completion_message_sent' not in column_names:
                    await cursor.execute("ALTER TABLE appointments ADD COLUMN completion_message_sent INTEGER DEFAULT 0")
                    await connection.commit()
                if 'admin_notification_sent' not in column_names:
                    await cursor.execute("ALTER TABLE appointments ADD COLUMN admin_notification_sent INTEGER DEFAULT 0")
                    await connection.commit()
                if 'service_duration_minutes' not in column_names:
                    await cursor.execute("ALTER TABLE appointments ADD COLUMN service_duration_minutes INTEGER DEFAULT 0")
                    await connection.commit()
                    # Backfill existing appointments with current service durations
                    await cursor.execute(
                        "UPDATE appointments SET service_duration_minutes = "
                        "(SELECT s.duration FROM services s WHERE s.id = appointments.service_id) "
                        "WHERE service_duration_minutes = 0"
                    )
                    await connection.commit()
            except Exception:
                pass
        
        # Migration: add photo_file_id column to services
        async with connection.cursor() as cursor:
            try:
                await cursor.execute("PRAGMA table_info(services)")
                columns = await cursor.fetchall()
                column_names = [row[1] for row in columns]
                if 'photo_file_id' not in column_names:
                    await cursor.execute("ALTER TABLE services ADD COLUMN photo_file_id TEXT")
                    await connection.commit()
            except Exception:
                pass
        
        # Migration: initialize schedule_settings with defaults if empty
        async with connection.cursor() as cursor:
            try:
                await cursor.execute("SELECT COUNT(*) FROM schedule_settings")
                count = await cursor.fetchone()
                if count[0] == 0:
                    # Set default schedule settings
                    defaults = {
                        "mode": "cycle",
                        "cycle_pattern": "5/2",
                        "cycle_start_date": "2026-04-20",
                        "interval_minutes": "30",
                        "start_time": "10:00",
                        "end_time": "20:00",
                    }
                    for key, value in defaults.items():
                        await cursor.execute(
                            "INSERT INTO schedule_settings (key, value) VALUES (?, ?)",
                            (key, value)
                        )
                    await connection.commit()
            except Exception:
                pass

        # Migration: normalize all stored dates to ISO
        try:
            await normalize_stored_dates(connection)
        except Exception:
            pass

# ── Бекап ────────────────────────────────────────────────────────────────────
async def backup_db() -> Path | None:
    """Копирует БД в BACKUPS_DIR с меткой времени. Оставляет последние 7 бекапов."""
    from .config import BACKUPS_DIR
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_path = BACKUPS_DIR / f"salon_{timestamp}.db"
        shutil.copy2(DB_PATH, backup_path)

        # Удаляем старые бекапы, оставляем последние 7
        backups = sorted(BACKUPS_DIR.glob("salon_*.db"))
        for old in backups[:-7]:
            old.unlink()

        return backup_path
    except Exception as e:
        logger.error(f"Ошибка бекапа БД: {e}")
        return None

async def cleanup_db(bot, admin_ids: list[int], days: int = 90) -> dict:
    """
    Перед очисткой — экспортирует удаляемые записи в CSV и шлёт админам.
    Затем чистит старые данные.
    """
    from .config import BACKUPS_DIR, EXPORTS_DIR
    from datetime import datetime, timedelta
    import csv, io

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    result = {}

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # ── 1. Собираем записи под удаление ──────────────────────────────────
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT 
                    a.id, a.appointment_date, a.appointment_time,
                    a.status, a.note, a.created_at,
                    c.first_name, c.last_name, c.phone, c.telegram_id,
                    s.name as service_name, s.price
                FROM appointments a
                JOIN clients c ON c.id = a.client_id
                JOIN services s ON s.id = a.service_id
                WHERE a.status IN ('cancelled', 'completed')
                AND a.appointment_date < ?
                ORDER BY a.appointment_date
            """, (cutoff,))
            rows = await cur.fetchall()

        # ── 2. Экспортируем в CSV и шлём админам ─────────────────────────────
        if rows and bot and admin_ids:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Дата", "Время", "Статус", "Имя", "Фамилия",
                "Телефон", "Telegram ID", "Услуга", "Цена", "Заметка", "Создана"
            ])
            total_revenue = 0
            for r in rows:
                writer.writerow([
                    r["appointment_date"], r["appointment_time"], r["status"],
                    r["first_name"], r["last_name"], r["phone"], r["telegram_id"],
                    r["service_name"], r["price"], r["note"], r["created_at"]
                ])
                if r["status"] == "completed":
                    total_revenue += r["price"] or 0

            csv_bytes = output.getvalue().encode("utf-8-sig")

            # Сохраняем копию в EXPORTS_DIR
            export_filename = EXPORTS_DIR / f"cleanup_{cutoff}_{datetime.now().strftime('%H-%M-%S')}.csv"
            export_filename.write_bytes(csv_bytes)

            from aiogram.types import BufferedInputFile
            for admin_id in admin_ids:
                try:
                    await bot.send_document(
                        chat_id=admin_id,
                        document=BufferedInputFile(csv_bytes, filename=export_filename.name),
                        caption=(
                            f"🗂 Архив перед очисткой БД\n"
                            f"📅 Записи старше {days} дней (до {cutoff})\n"
                            f"📊 Записей: {len(rows)}\n"
                            f"💰 Выручка (завершённые): {total_revenue} ₽"
                        )
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить архив админу {admin_id}: {e}")

        # ── 3. Удаляем ────────────────────────────────────────────────────────
        async with conn.cursor() as cur:
            await cur.execute("""
                DELETE FROM appointments
                WHERE status IN ('cancelled', 'completed')
                AND appointment_date < ?
            """, (cutoff,))
            result["appointments"] = cur.rowcount

        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM unavailable_slots WHERE slot_date < ?", (cutoff,))
            result["unavailable_slots"] = cur.rowcount

        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM work_days WHERE work_date < ?", (cutoff,))
            result["work_days"] = cur.rowcount

        # feedback чистим мягче — за 180 дней
        soft_cutoff = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM feedback WHERE created_at < ?", (soft_cutoff,))
            result["feedback"] = cur.rowcount

        await conn.commit()

    logger.info(f"Очистка БД завершена: {result}")
    return result

def get_connection():
    """Get an async context manager for database connection."""
    return aiosqlite.connect(DB_PATH)
