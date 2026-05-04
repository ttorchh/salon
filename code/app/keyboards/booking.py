from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def booking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Выбрать услугу", callback_data="booking:start")],
            [InlineKeyboardButton(text="Мои записи", callback_data="booking:list")],
            [InlineKeyboardButton(text="Назад в меню", callback_data="menu:main")],
        ]
    )


def service_selection_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for service in services:
        buttons.append([
            InlineKeyboardButton(
                text=f"{service['name']} — {service['price']} ₽",
                callback_data=f"service:{service['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="➖ Отмена", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_booking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="booking:confirm")],
            [InlineKeyboardButton(text="➖ Отменить", callback_data="booking:cancel")],
        ]
    )
