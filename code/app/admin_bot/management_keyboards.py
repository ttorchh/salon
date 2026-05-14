from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def appointment_admin_keyboard(appointment_id: int, view_type: str = "today", page: int = 1) -> InlineKeyboardMarkup:
    """Keyboard for managing an appointment in admin panel."""
    from app.admin_bot.handlers import AdminReschedule, AdminCancel, AppointmentBack

    buttons = [
        [
            InlineKeyboardButton(text="📅 Перенести", callback_data=AdminReschedule(appointment_id=appointment_id).pack()),
            InlineKeyboardButton(text="❌ Отменить", callback_data=AdminCancel(appointment_id=appointment_id).pack()),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data=AppointmentBack(view_type=view_type, page=page).pack()),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def appointments_view_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing how to view appointments."""
    from app.admin_bot.handlers import ViewAppointments, AdminMenu

    buttons = [
        [
            InlineKeyboardButton(text="🗒 На сегодня", callback_data=ViewAppointments(view_type="today").pack()),
            InlineKeyboardButton(text="📆 На неделю", callback_data=ViewAppointments(view_type="week").pack()),
        ],
        [InlineKeyboardButton(text="⏳ Предстоящие", callback_data=ViewAppointments(view_type="upcoming").pack())],
        [InlineKeyboardButton(text="◀ Назад", callback_data=AdminMenu().pack())]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_services_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for managing services."""
    from app.admin_bot.handlers import ServiceCreate, ServiceList, AdminMenu

    buttons = [
        [
            InlineKeyboardButton(text="➕ Добавить услугу", callback_data=ServiceCreate().pack()),
            InlineKeyboardButton(text="📋 Список услуг", callback_data=ServiceList().pack()),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data=AdminMenu().pack()),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def services_list_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard showing all services with edit and delete buttons."""
    from app.admin_bot.handlers import ServiceEdit, ServiceDelete, ServiceCreate, AdminServices

    buttons = []
    for service in services:
        buttons.append([
            InlineKeyboardButton(
                text=f"{service['name']} - {service['price']}₽",
                callback_data=ServiceEdit(service_id=service["id"]).pack(),
            ),
            InlineKeyboardButton(text="🗑️", callback_data=ServiceDelete(service_id=service["id"]).pack()),
        ])
    buttons.append([InlineKeyboardButton(text="➕ Добавить услугу", callback_data=ServiceCreate().pack())])
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data=AdminServices().pack())])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def service_edit_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Keyboard for editing a service."""
    from app.admin_bot.handlers import ServiceEditField, ServiceDelete, ServiceList

    buttons = [
        [
            InlineKeyboardButton(text="📝 Имя", callback_data=ServiceEditField(service_id=service_id, field="name").pack()),
            InlineKeyboardButton(text="💰 Цена", callback_data=ServiceEditField(service_id=service_id, field="price").pack()),
        ],
        [
            InlineKeyboardButton(text="⏱️ Длительность", callback_data=ServiceEditField(service_id=service_id, field="duration").pack()),
            InlineKeyboardButton(text="📄 Описание", callback_data=ServiceEditField(service_id=service_id, field="description").pack()),
        ],
        [
            InlineKeyboardButton(text="🌠 Фото", callback_data=ServiceEditField(service_id=service_id, field="photo").pack()),
        ],
        [
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=ServiceDelete(service_id=service_id).pack()),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data=ServiceList().pack()),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_delete_service_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Confirmation keyboard for deleting service."""
    from app.admin_bot.handlers import ServiceConfirmDelete, ServiceEdit

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить удаление", callback_data=ServiceConfirmDelete(service_id=service_id).pack()),
            InlineKeyboardButton(text="❌ Отменить", callback_data=ServiceEdit(service_id=service_id).pack()),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def blocking_type_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing blocking type."""
    from app.admin_bot.handlers import BlockDay, BlockTime, BlockView, ScheduleOpenDay, AdminMenu, ScheduleSettingsType

    buttons = [
        [
            InlineKeyboardButton(text="📅 Заблокировать день", callback_data=BlockDay().pack()),
            InlineKeyboardButton(text="⏰ Заблокировать время", callback_data=BlockTime().pack()),
        ],
        [
            InlineKeyboardButton(text="👁️ Посмотреть блокировки", callback_data=BlockView().pack()),
            InlineKeyboardButton(text="📖 Открыть выходной", callback_data=ScheduleOpenDay().pack()),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настроить график", callback_data=ScheduleSettingsType(schedule_type="settings").pack()),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data=AdminMenu().pack()),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def blocked_slots_keyboard(blocked_slots: list[dict], blocked_days: list[str] = None) -> InlineKeyboardMarkup:
    """Keyboard showing blocked time slots and entire days."""
    from app.admin_bot.handlers import BlockingMenu

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
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data=BlockingMenu().pack())])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def blocked_day_keyboard() -> InlineKeyboardMarkup:
    """Keyboard after blocking entire day."""
    from app.admin_bot.handlers import BlockingMenu

    buttons = [
        [InlineKeyboardButton(text="◀ Назад", callback_data=BlockingMenu().pack())]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def pricelist_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for pricelist management."""
    from app.admin_bot.handlers import PricelistUpload, ServiceList, AdminMenu

    buttons = [
        [
            InlineKeyboardButton(text="📤 Загрузить прайс", callback_data=PricelistUpload().pack()),
            InlineKeyboardButton(text="📋 Услуги", callback_data=ServiceList().pack()),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data=AdminMenu().pack()),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def service_edit_cancel_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Keyboard with cancel button for editing service fields."""
    from app.admin_bot.handlers import ServiceEdit

    buttons = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data=ServiceEdit(service_id=service_id).pack())]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def clients_root_keyboard() -> InlineKeyboardMarkup:
    """Top-level clients menu."""
    from app.admin_bot.handlers import AdminMenu, ClientsBans, ClientsList
    
    buttons = [
        [
            InlineKeyboardButton(text="👥 Клиенты", callback_data=ClientsList(page=1).pack()),
            InlineKeyboardButton(text="⛔ Банлист", callback_data=ClientsBans(page=1).pack()),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data=AdminMenu().pack()),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def client_list_keyboard(items: list[dict], page: int, has_prev: bool, has_next: bool, *, banned: bool = False) -> InlineKeyboardMarkup:
    """Paginated list of clients or banned users."""
    from app.admin_bot.handlers import ClientsBanView, ClientsBans, ClientsList, ClientsMenu, ClientsView

    buttons = []

    for item in items:
        telegram_id = item["telegram_id"]
        first_name = item.get("first_name") or ""
        last_name = item.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip() or "Без имени"
        callback_data = (
            ClientsBanView(telegram_id=telegram_id, page=page).pack()
            if banned
            else ClientsView(telegram_id=telegram_id, page=page).pack()
        )
        buttons.append([
            InlineKeyboardButton(
                text=f"{telegram_id} | {full_name}",
                callback_data=callback_data,
            )
        ])

    nav_row = []
    if has_prev:
        nav_row.append(
            InlineKeyboardButton(
                text="◀",
                callback_data=(ClientsBans(page=page - 1).pack() if banned else ClientsList(page=page - 1).pack()),
            )
        )
    nav_row.append(InlineKeyboardButton(text="Назад", callback_data=ClientsMenu().pack()))
    if has_next:
        nav_row.append(
            InlineKeyboardButton(
                text="▶",
                callback_data=(ClientsBans(page=page + 1).pack() if banned else ClientsList(page=page + 1).pack()),
            )
        )
    buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def client_detail_keyboard(telegram_id: int, source: str, page: int, *, is_banned: bool) -> InlineKeyboardMarkup:
    """Actions for a client card."""
    from app.admin_bot.handlers import ClientsBan, ClientsBans, ClientsBook, ClientsHistory, ClientsList, ClientsMessage, ClientsUnban

    buttons = [
        [
            InlineKeyboardButton(
                text="👤 История",
                callback_data=ClientsHistory(telegram_id=telegram_id, source=source, page=page).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text="⛔ Заблокировать" if not is_banned else "⛔ Уже в бане",
                callback_data=ClientsBan(telegram_id=telegram_id, source=source, page=page).pack(),
            ),
            InlineKeyboardButton(
                text="✅ Разблокировать" if is_banned else "✅ Не заблокирован",
                callback_data=ClientsUnban(telegram_id=telegram_id, source=source, page=page).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text="💬 Написать",
                callback_data=ClientsMessage(telegram_id=telegram_id, source=source, page=page).pack(),
            ),
            InlineKeyboardButton(
                text="📝 Записать",
                callback_data=ClientsBook(telegram_id=telegram_id, source=source, page=page).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text="◀ Назад",
                callback_data=(ClientsBans(page=page).pack() if source == "bans" else ClientsList(page=page).pack()),
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
