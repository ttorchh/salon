from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData

class AdminBlockTime(CallbackData, prefix="admin_block_time"):
    pass

class AdminUnblockTime(CallbackData, prefix="admin_unblock_time"):
    pass

class ScheduleOpenDay(CallbackData, prefix="schedule_open_day"):
    pass

class AdminMenu(CallbackData, prefix="admin_menu"):
    pass

def admin_schedule_menu_keyboard() -> InlineKeyboardMarkup:
    """Submenu for schedule management (blocking/unblocking time)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📆 График", callback_data=AdminBlockTime().pack()),
                InlineKeyboardButton(text="🔓 Разблокировать", callback_data=AdminUnblockTime().pack()),
            ],
            [
                InlineKeyboardButton(text="📖 Открыть выходной", callback_data=ScheduleOpenDay().pack()),
            ],
            [
                InlineKeyboardButton(text="◀ Назад", callback_data=AdminMenu().pack()),
            ]
        ]
    )
