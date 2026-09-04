import argparse
import os
import subprocess
import sys
import time
import logging
from pathlib import Path

RESTART_CODE = 1
STOP_CODE    = 0
RESTART_DELAY = int(os.environ.get("RESTART_DELAY", "3"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("launcher")

def parse_args():
    parser = argparse.ArgumentParser(description="salon_sandbox Bot Launcher")
    parser.add_argument(
        "--instance", "-i",
        required=True,
        help="Путь к папке инстанса (где лежат .env и data/)"
    )
    parser.add_argument(
        "--mode",
        choices=["bot", "admin", "both"],
        default="both",
        help="Что запускать: bot, admin или both (по умолчанию both)"
    )
    return parser.parse_args()


def run_process(cmd, env, name):
    """Запускает процесс с автоперезапуском."""
    while True:
        logger.info(f"[launcher] Запуск {name}...")
        p = subprocess.Popen(cmd, env=env)
        code = p.wait()

        if code == STOP_CODE:
            logger.info(f"[launcher] {name} остановлен штатно")
            break
        elif code == RESTART_CODE:
            logger.info(f"[launcher] {name} запросил перезапуск, ждём {RESTART_DELAY}с...")
            time.sleep(RESTART_DELAY)
        else:
            logger.error(f"[launcher] {name} упал с кодом {code}, перезапуск через {RESTART_DELAY}с...")
            time.sleep(RESTART_DELAY)


def main():
    args = parse_args()
    instance_path = Path(args.instance).resolve()

    if not instance_path.exists():
        logger.error(f"[ERROR] Папка инстанса не найдена: {instance_path}")
        sys.exit(1)

    core_dir = Path(__file__).resolve().parent

    env = os.environ.copy()
    env["INSTANCE_DIR"] = str(instance_path)

    logger.info(f"[launcher] Ядро:    {core_dir}")
    logger.info(f"[launcher] Инстанс: {instance_path}")
    logger.info(f"[launcher] Режим:   {args.mode}")

    import threading

    threads = []

    if args.mode in ("bot", "both"):
        threads.append(threading.Thread(
            target=run_process,
            args=([sys.executable, str(core_dir / "main.py")], env, "bot"),
            daemon=True,
            name="bot-thread",
        ))

    if args.mode in ("admin", "both"):
        threads.append(threading.Thread(
            target=run_process,
            args=([sys.executable, str(core_dir / "admin_main.py")], env, "admin"),
            daemon=True,
            name="admin-thread",
        ))

    for t in threads:
        t.start()

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logger.info("\n[launcher] Остановка...")
        sys.exit(0)


if __name__ == "__main__":
    main()