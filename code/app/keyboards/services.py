from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def services_manage_keyboard() -> InlineKeyboardMarkup:
    """Admin keyboard for managing services."""
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить услугу", callback_data="service:add")],
        [InlineKeyboardButton(text="✏️ Редактировать услугу", callback_data="service:edit")],
        [InlineKeyboardButton(text="🗑️ Удалить услугу", callback_data="service:delete")],
        [InlineKeyboardButton(text="📋 Просмотр услуг", callback_data="service:list")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def services_list_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard with list of services for selection."""
    buttons = []
    for service in services:
        text = f"{service['name']} ({service['price']}₽, {service['duration']}мин)"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"service:select:{service['id']}")])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="service:manage")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def service_action_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Keyboard for editing or deleting a service."""
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"service:edit_name:{service_id}")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"service:edit_price:{service_id}")],
        [InlineKeyboardButton(text="⏱️ Изменить длительность", callback_data=f"service:edit_duration:{service_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"service:delete_confirm:{service_id}")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="service:list")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_delete_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Confirmation keyboard for deleting service."""
    buttons = [
        [InlineKeyboardButton(text="✅ Удалить", callback_data=f"service:delete_yes:{service_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="service:list")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
