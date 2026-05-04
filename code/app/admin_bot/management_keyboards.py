from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def appointment_admin_keyboard(appointment_id: int) -> InlineKeyboardMarkup:
    """Keyboard for managing an appointment in admin panel."""
    buttons = [
        [
            InlineKeyboardButton(text="📅 Перенести", callback_data=f"admin_reschedule:{appointment_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"admin_cancel:{appointment_id}"),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data="admin:menu"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def appointments_view_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing how to view appointments."""
    buttons = [
        [
            InlineKeyboardButton(text="🗒 На сегодня", callback_data="view:today"),
            InlineKeyboardButton(text="📆 На неделю", callback_data="view:week"),
        ],
        [InlineKeyboardButton(text="⏳ Предстоящие", callback_data="view:upcoming")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="admin:menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_services_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for managing services."""
    buttons = [
        [
            InlineKeyboardButton(text="➕ Добавить услугу", callback_data="service:create"),
            InlineKeyboardButton(text="📋 Список услуг", callback_data="service:list"),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data="admin:menu"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def services_list_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard showing all services with edit and delete buttons."""
    buttons = []
    for service in services:
        buttons.append([
            InlineKeyboardButton(
                text=f"{service['name']} - {service['price']}₽",
                callback_data=f"service:edit:{service['id']}",
            ),
            InlineKeyboardButton(text="🗑️", callback_data=f"service:delete:{service['id']}"),
        ])
    buttons.append([InlineKeyboardButton(text="➕ Добавить услугу", callback_data="service:create")])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="admin:services")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def service_edit_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Keyboard for editing a service."""
    buttons = [
        [
            InlineKeyboardButton(text="📝 Имя", callback_data=f"service:edit_field:{service_id}:name"),
            InlineKeyboardButton(text="💰 Цена", callback_data=f"service:edit_field:{service_id}:price"),
        ],
        [
            InlineKeyboardButton(text="⏱️ Длительность", callback_data=f"service:edit_field:{service_id}:duration"),
            InlineKeyboardButton(text="📄 Описание", callback_data=f"service:edit_field:{service_id}:description"),
        ],
        [
            InlineKeyboardButton(text="🌠 Фото", callback_data=f"service:edit_field:{service_id}:photo"),
        ],
        [
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"service:delete:{service_id}"),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data="service:list"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_delete_service_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Confirmation keyboard for deleting service."""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить удаление", callback_data=f"service:confirm_delete:{service_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"service:edit:{service_id}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def blocking_type_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing blocking type."""
    buttons = [
        [
            InlineKeyboardButton(text="📅 Заблокировать день", callback_data="block:day"),
            InlineKeyboardButton(text="⏰ Заблокировать время", callback_data="block:time"),
        ],
        [
            InlineKeyboardButton(text="👁️ Посмотреть блокировки", callback_data="block:view"),
            InlineKeyboardButton(text="📖 Открыть выходной", callback_data="schedule:open_day"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настроить график", callback_data="schedule:settings"),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data="admin:menu"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def blocked_slots_keyboard(blocked_slots: list[dict], blocked_days: list[str] = None) -> InlineKeyboardMarkup:
    """Keyboard showing blocked time slots and entire days."""
    buttons = []
    
    # Add buttons for fully blocked days first
    if blocked_days:
        for day in sorted(blocked_days):
            buttons.append([
                InlineKeyboardButton(
                    text=f"📅 {day} - День полностью заблокирован (удалить)",
                    callback_data=f"unblock_day:{day}"
                )
            ])
    
    # Add buttons for individual time slots
    for slot in blocked_slots:
        buttons.append([
            InlineKeyboardButton(
                text=f"{slot['time']} - {slot['reason']}",
                callback_data=f"unblock:{slot['date']}:{slot['time']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="blocking:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def blocked_day_keyboard() -> InlineKeyboardMarkup:
    """Keyboard after blocking entire day."""
    buttons = [
        [InlineKeyboardButton(text="◀ Назад", callback_data="blocking:menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def pricelist_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for pricelist management."""
    buttons = [
        [
            InlineKeyboardButton(text="🌠 Прайс-лист", callback_data="pricelist:upload"),
            InlineKeyboardButton(text="📋 Услуги", callback_data="service:list"),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data="admin:menu"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def service_edit_cancel_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Keyboard with cancel button for editing service fields."""
    buttons = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"service:edit:{service_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def clients_root_keyboard() -> InlineKeyboardMarkup:
    """Top-level clients menu."""
    buttons = [
        [
            InlineKeyboardButton(text="👥 Клиенты", callback_data="clients:list:1"),
            InlineKeyboardButton(text="⛔ Банлист", callback_data="clients:bans:1"),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data="admin:menu"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def client_list_keyboard(items: list[dict], page: int, has_prev: bool, has_next: bool, *, banned: bool = False) -> InlineKeyboardMarkup:
    """Paginated list of clients or banned users."""
    buttons = []
    prefix = "clients:banview" if banned else "clients:view"

    for item in items:
        telegram_id = item["telegram_id"]
        first_name = item.get("first_name") or ""
        last_name = item.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip() or "Без имени"
        buttons.append([
            InlineKeyboardButton(
                text=f"{telegram_id} | {full_name}",
                callback_data=f"{prefix}:{telegram_id}:{page}",
            )
        ])

    nav_row = []
    if has_prev:
        nav_row.append(InlineKeyboardButton(text="◀", callback_data=f"{'clients:bans' if banned else 'clients:list'}:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text="Назад", callback_data="clients:menu"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="▶", callback_data=f"{'clients:bans' if banned else 'clients:list'}:{page + 1}"))
    buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def client_detail_keyboard(telegram_id: int, source: str, page: int, *, is_banned: bool) -> InlineKeyboardMarkup:
    """Actions for a client card."""
    back_target = "clients:bans" if source == "bans" else "clients:list"
    buttons = [
        [
            InlineKeyboardButton(text="👤 История", callback_data=f"clients:history:{telegram_id}:{source}:{page}"),
        ],
        [
            InlineKeyboardButton(
                text="⛔ Заблокировать" if not is_banned else "⛔ Уже в бане",
                callback_data=f"clients:ban:{telegram_id}:{source}:{page}",
            ),
            InlineKeyboardButton(
                text="✅ Разблокировать" if is_banned else "✅ Не заблокирован",
                callback_data=f"clients:unban:{telegram_id}:{source}:{page}",
            ),
        ],
        [
            InlineKeyboardButton(text="💬 Написать", callback_data=f"clients:message:{telegram_id}:{source}:{page}"),
            InlineKeyboardButton(text="📝 Записать", callback_data=f"clients:book:{telegram_id}:{source}:{page}"),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data=f"{back_target}:{page}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
