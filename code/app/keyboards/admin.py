from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main admin menu with text buttons."""
    buttons = [
        [KeyboardButton(text="📋 Записи"), KeyboardButton(text="📢 Рассылка")],
        [KeyboardButton(text="📆 График"), KeyboardButton(text="⚙️ Прайс")],
        [KeyboardButton(text="💬 Отзывы"), KeyboardButton(text="👥 Клиенты")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


__all__ = ["admin_menu_keyboard"]

