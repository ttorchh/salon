from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData
from app.keyboards.callbacks import MenuAction

class BookingAction(CallbackData, prefix="booking"):
    action: str


class ServiceSelect(CallbackData, prefix="service"):
    service_id: int



def booking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Выбрать услугу", callback_data=BookingAction(action="start").pack())],
            [InlineKeyboardButton(text="Мои записи", callback_data=BookingAction(action="list").pack())],
            [InlineKeyboardButton(text="Назад в меню", callback_data=MenuAction(action="main").pack())],
        ]
    )


def service_selection_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for service in services:
        buttons.append([
            InlineKeyboardButton(
                text=f"{service['name']} — {service['price']} ₽",
                callback_data=ServiceSelect(service_id=service['id']).pack(),
            )
        ])
    buttons.append([InlineKeyboardButton(text="➖ Отмена", callback_data=MenuAction(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_booking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить запись", callback_data=BookingAction(action="confirm").pack())],
            [InlineKeyboardButton(text="➖ Отменить", callback_data=BookingAction(action="cancel").pack())],
        ]
    )
