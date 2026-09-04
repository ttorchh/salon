import asyncio
import logging
import sys

from aiohttp import web

from app.bot import create_bot, create_dispatcher
from app.config import ADMIN_BOT_TOKEN, USE_WEBHOOK, WEBHOOK_HOST, WEBHOOK_PATH_ADMIN, API_HOST, ADMIN_API_PORT
from app.database import init_db, init_data_dirs
from app.services.catalog_service import CatalogService
from app.background_tasks import start_admin_background_tasks
from aiogram.types import BotCommand

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

async def setup_bot_commands(bot):
    commands = [
        BotCommand(command="setup", description="первичная настройка"),
        BotCommand(command="info", description="информация о командах"),
        BotCommand(command="data", description="информация о дате"),
        BotCommand(command="time", description="информация о расписании"),
        BotCommand(command="reload", description="перезагрузка"),
    ]
    try:
        await bot.set_my_commands(commands)
        logger.info("Команды бота успешно зарегистрированы")
    except Exception as e:
        logger.warning(f"Не удалось зарегистрировать команды бота: {e}")


async def start_polling(bot, dispatcher) -> None:
    """Start polling mode."""
    logger.info("🚀 Запуск админ-бота в режиме поллинга...")
    try:
        await dispatcher.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске админ-бота: {e}")
        raise
    finally:
        logger.info("Закрытие сессии админ-бота...")
        await bot.session.close()


async def start_webhook(bot, dispatcher, app: web.Application) -> None:
    """Start webhook mode."""
    logger.info(f"🚀 Запуск админ-бота в режиме вебхука: {WEBHOOK_HOST}{WEBHOOK_PATH_ADMIN}")

    try:
        await bot.set_webhook(
            url=f"{WEBHOOK_HOST}{WEBHOOK_PATH_ADMIN}",
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        logger.info("✅ Вебхук админ-бота установлен")

        async def telegram_webhook(request):
            try:
                from aiogram.types import Update
                data = await request.json()
                update = Update.model_validate(data)
                await dispatcher.feed_update(bot, update)
                return web.Response()
            except Exception as e:
                logger.error(f"Ошибка при обработке вебхука админ-бота: {e}")
                return web.Response(status=400)

        async def health_check(request):
            return web.json_response({"status": "ok"})

        app.router.add_post(WEBHOOK_PATH_ADMIN, telegram_webhook)
        app.router.add_get("/health", health_check)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, API_HOST, ADMIN_API_PORT)
        await site.start()

        logger.info(f"🌐 Веб-сервер админ-бота запущен на {API_HOST}:{ADMIN_API_PORT}")

        try:
            while True:
                await asyncio.sleep(1)
        finally:
            await runner.cleanup()

    except Exception as e:
        logger.error(f"Ошибка при запуске вебхука администратора: {e}")
        raise
    finally:
        logger.info("Закрытие сессии админ-бота...")
        await bot.session.close()


async def main() -> None:
    init_data_dirs()
    await init_db()
    await CatalogService.seed_services()
    await CatalogService.restore_service_photos()

    start_admin_background_tasks()

    bot = create_bot(ADMIN_BOT_TOKEN)
    dispatcher = create_dispatcher(bot, admin=True)

    await setup_bot_commands(bot)
    
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