import logging

from aiogram import Dispatcher

__all__ = [
    "register_routers",
    "register_user_routers",
    "register_admin_routers",
]

logger = logging.getLogger(__name__)


def register_user_routers(dispatcher: Dispatcher) -> None:
    from app.user_bot import booking_router, user_router

    dispatcher.include_router(booking_router)
    dispatcher.include_router(user_router)


def register_admin_routers(dispatcher: Dispatcher) -> None:
    from app.admin_bot import router as admin_router

    dispatcher.include_router(admin_router)


def register_routers(dispatcher: Dispatcher, include_admin: bool = False) -> None:
    if include_admin:
        register_admin_routers(dispatcher)
    else:
        register_user_routers(dispatcher)
