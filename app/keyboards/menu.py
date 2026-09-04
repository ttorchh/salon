from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


'''def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu with callback buttons (can be easily customized with emojis)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌸 Записаться", callback_data="booking:start"),
                InlineKeyboardButton(text=" Прайс", callback_data="show_price"),
            ],
            [
                InlineKeyboardButton(text="🌷 Мои записи", callback_data="my_apts"),
                InlineKeyboardButton(text="Контакты", callback_data="show_contacts"),
            ],
        ]
    )'''

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🌸 Записаться"),
                KeyboardButton(text="💰 Прайс"),
            ],
            [
                KeyboardButton(text="🌷 Мои записи"),
                KeyboardButton(text="📞 Контакты"),
            ],
        ],
        resize_keyboard=True
    )