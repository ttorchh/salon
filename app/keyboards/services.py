from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.admin_bot.handlers import (
    AdminMenuCB,
    AdminServices,
    ServiceCreate,
    ServiceDelete,
    ServiceEdit,
    ServiceEditField,
    ServiceList,
    ServiceConfirmDelete,
)


class ServiceSelect(CallbackData, prefix="service_select"):
    service_id: int


def services_manage_keyboard() -> InlineKeyboardMarkup:
    """Admin keyboard for managing services."""
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить услугу", callback_data=ServiceCreate().pack())],
        [InlineKeyboardButton(text="📋 Просмотр услуг", callback_data=ServiceList().pack())],
        [InlineKeyboardButton(text="◀ Назад", callback_data=AdminMenuCB().pack())],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def services_list_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard with list of services for selection."""
    buttons = []
    for service in services:
        text = f"{service['name']} ({service['price']}₽, {service['duration']}мин)"
        buttons.append([InlineKeyboardButton(text=text, callback_data=ServiceSelect(service_id=service['id']).pack())])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data=AdminServices().pack())])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def service_action_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Keyboard for editing or deleting a service."""
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data=ServiceEditField(service_id=service_id, field="name").pack())],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data=ServiceEditField(service_id=service_id, field="price").pack())],
        [InlineKeyboardButton(text="⏱️ Изменить длительность", callback_data=ServiceEditField(service_id=service_id, field="duration").pack())],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=ServiceDelete(service_id=service_id).pack())],
        [InlineKeyboardButton(text="◀ Назад", callback_data=ServiceList().pack())],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_delete_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Confirmation keyboard for deleting service."""
    buttons = [
        [InlineKeyboardButton(text="✅ Удалить", callback_data=ServiceConfirmDelete(service_id=service_id).pack())],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=ServiceEdit(service_id=service_id).pack())],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
