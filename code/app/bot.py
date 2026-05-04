import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from .config import TELEGRAM_PROXY
from .middlewares import BanCheckMiddleware
from .routers import register_admin_routers, register_user_routers

logger = logging.getLogger(__name__)


def create_bot(token: str, is_admin_bot: bool = False) -> Bot:
    session = AiohttpSession(proxy=TELEGRAM_PROXY) if TELEGRAM_PROXY else AiohttpSession()
    
    if TELEGRAM_PROXY:
        logger.info(f"Используется прокси: {TELEGRAM_PROXY}")

    return Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=None),
    )


def create_dispatcher(bot: Bot, *, admin: bool = False) -> Dispatcher:
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)

    if admin:
        register_admin_routers(dispatcher)
    else:
        ban_middleware = BanCheckMiddleware()
        dispatcher.message.outer_middleware(ban_middleware)
        dispatcher.callback_query.outer_middleware(ban_middleware)
        register_user_routers(dispatcher)

    return dispatcher
