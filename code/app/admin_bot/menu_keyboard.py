from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def admin_schedule_menu_keyboard() -> InlineKeyboardMarkup:
    """Submenu for schedule management (blocking/unblocking time)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📆 График", callback_data="admin:block_time"),
                InlineKeyboardButton(text="🔓 Разблокировать", callback_data="admin:unblock_time"),
            ],
            [
                InlineKeyboardButton(text="📖 Открыть выходной", callback_data="schedule:open_day"),
            ],
            [
                InlineKeyboardButton(text="◀ Назад", callback_data="admin:menu"),
            ]
        ]
    )
