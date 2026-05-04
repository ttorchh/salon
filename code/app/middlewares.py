from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.services.admin_service import AdminService


def format_ban_message(reason: str | None) -> str:
    """Build a standard ban message for the user bot."""
    if reason:
        return f"⛔ Вы заблокированы в боте.\nПричина: {reason}"
    return "⛔ Вы заблокированы в боте."


class BanCheckMiddleware(BaseMiddleware):
    """Prevent banned users from interacting with the user bot."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        ban_info = await AdminService.get_ban_info(user.id)
        if not ban_info:
            return await handler(event, data)

        text = format_ban_message(ban_info.get("reason"))
        if isinstance(event, Message):
            await event.answer(text)
            return None
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
            return None

        return None
