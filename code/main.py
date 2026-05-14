import asyncio
import logging
import sys

from aiogram import Bot
from aiohttp import web

from app.bot import create_dispatcher, create_bot
from app.config import BOT_TOKEN, USE_WEBHOOK, WEBHOOK_HOST, WEBHOOK_PORT, WEBHOOK_PATH_USER, API_HOST, API_PORT
from app.database import init_db, init_data_dirs
from app.services.catalog_service import CatalogService
from app.background_tasks import start_background_tasks

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logging.getLogger("aiogram").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

async def start_polling(bot: Bot, dispatcher) -> None:
    """Start polling mode."""
    logger.info("🚀 Запуск бота в режиме поллинга...")
    try:
        await dispatcher.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise
    finally:
        logger.info("Закрытие сессии бота...")
        await bot.session.close()


async def start_webhook(bot: Bot, dispatcher, app: web.Application) -> None:
    """Start webhook mode."""
    logger.info(f"🚀 Запуск бота в режиме вебхука: {WEBHOOK_HOST}{WEBHOOK_PATH_USER}")
    
    try:
        # Set webhook for user bot
        await bot.set_webhook(
            url=f"{WEBHOOK_HOST}{WEBHOOK_PATH_USER}",
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        logger.info("✅ Вебхук установлен")
        
        # Register webhook handler
        async def telegram_webhook(request):
            try:
                from aiogram.types import Update
                data = await request.json()
                update = Update.model_validate(data)
                await dispatcher.feed_update(bot, update)
                return web.Response()
            except Exception as e:
                logger.error(f"Ошибка при обработке вебхука: {e}")
                return web.Response(status=400)
        
        app.router.add_post(WEBHOOK_PATH_USER, telegram_webhook)
        
        # Health check endpoint
        async def health_check(request):
            return web.json_response({"status": "ok"})
        
        app.router.add_get("/health", health_check)
        
        # Start web server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, API_HOST, API_PORT)
        await site.start()
        
        logger.info(f"🌐 Веб-сервер запущен на {API_HOST}:{API_PORT}")
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        finally:
            await runner.cleanup()
            
    except Exception as e:
        logger.error(f"Ошибка при запуске вебхука: {e}")
        raise
    finally:
        logger.info("Закрытие сессии бота...")
        await bot.session.close()


async def main() -> None:
    init_data_dirs()
    await init_db()
    await CatalogService.seed_services()
    await CatalogService.restore_service_photos()
    
    # Start all background tasks (user reminders + admin notifications)
    # NOTE: Only called in main.py, not in admin_main.py to avoid duplicate tasks
    start_background_tasks()

    bot = create_bot(BOT_TOKEN)
    dispatcher = create_dispatcher(bot, admin=False)

    try:
        if USE_WEBHOOK:
            app = web.Application()
            await start_webhook(bot, dispatcher, app)
        else:
            await start_polling(bot, dispatcher)
    except KeyboardInterrupt:
        logger.info("Получен сигнал SIGINT, завершение...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
    loop.close()
