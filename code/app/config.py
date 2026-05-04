import os
from pathlib import Path
from datetime import timezone, timedelta
from dotenv import load_dotenv

# SALON/code/app/config.py
# .parent       → SALON/code/app
# .parent.parent → SALON/code
CORE_DIR = Path(__file__).resolve().parent.parent

# ── Папка инстанса ────────────────────────────────────────────────────────────
_instance_env = os.environ.get("INSTANCE_DIR")
if not _instance_env:
    raise RuntimeError(
        "INSTANCE_DIR не задан. "
        "Запускайте через launcher.py --instance <путь> "
        "или задайте переменную окружения INSTANCE_DIR."
    )

INSTANCE_DIR = Path(_instance_env).resolve()
if not INSTANCE_DIR.exists():
    raise RuntimeError(f"Папка инстанса не найдена: {INSTANCE_DIR}")

# ── .env из папки инстанса ────────────────────────────────────────────────────
ENV_PATH = INSTANCE_DIR / ".env"
if not ENV_PATH.exists():
    raise RuntimeError(f".env не найден: {ENV_PATH}")

load_dotenv(ENV_PATH)

# ── Токены и ID ───────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError(f"BOT_TOKEN не найден в {ENV_PATH}")

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "") or BOT_TOKEN

ADMIN_IDS = [
    int(item)
    for item in os.getenv("ADMIN_IDS", "").split(",")
    if item.strip().isdigit()
]

TELEGRAM_PROXY = (
    os.getenv("TELEGRAM_PROXY")
    or os.getenv("HTTPS_PROXY")
    or os.getenv("HTTP_PROXY")
)

DEFAULT_PARSE_MODE = os.getenv("DEFAULT_PARSE_MODE", "HTML")

# ── Webhook (опционально, для использования вместо polling) ───────────────────
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "false").lower() == "true"
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://yourdomain.com")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))
WEBHOOK_PATH_USER = os.getenv("WEBHOOK_PATH_USER", "/webhook/user")
WEBHOOK_PATH_ADMIN = os.getenv("WEBHOOK_PATH_ADMIN", "/webhook/admin")
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8443"))
ADMIN_API_PORT = int(os.getenv("ADMIN_API_PORT", "8444"))  # ← добавить

# ── Restart delay при перезагрузке ────────────────────────────────────────────
RESTART_DELAY = float(os.getenv("RESTART_DELAY", "1.0"))  # секунды перед выходом

# ── Пути к данным (всё внутри инстанса) ──────────────────────────────────────
DATA_DIR            = INSTANCE_DIR / "data"
DB_PATH             = os.getenv("DB_PATH", str(DATA_DIR / "salon.db"))
IMAGES_DIR          = DATA_DIR / "images"
SERVICE_IMAGES_DIR  = IMAGES_DIR / "services"
FEEDBACK_IMAGES_DIR = IMAGES_DIR / "feedback"
EXPORTS_DIR         = DATA_DIR / "exports"
LOGS_DIR    = INSTANCE_DIR / "logs"
BACKUPS_DIR = INSTANCE_DIR / "backups"

for _dir in (DATA_DIR, IMAGES_DIR, SERVICE_IMAGES_DIR, FEEDBACK_IMAGES_DIR, EXPORTS_DIR, LOGS_DIR, BACKUPS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ── Timezone ──────────────────────────────────────────────────────────────────
DEFAULT_TZ_OFFSET = 3
TZ      = timezone(timedelta(hours=DEFAULT_TZ_OFFSET))
TZ_NAME = "Europe/Moscow"

async def get_tz():
    try:
        from app.services.admin_service import AdminService
        offset = await AdminService.get_timezone_offset()
        return timezone(timedelta(hours=offset))
    except Exception:
        return TZ

def get_tz_sync():
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT value FROM schedule_settings WHERE key = 'timezone_offset'")
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return timezone(timedelta(hours=int(row[0])))
    except Exception:
        pass
    return TZ