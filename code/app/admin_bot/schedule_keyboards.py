"""Keyboards for /schedule command."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def schedule_mode_keyboard() -> InlineKeyboardMarkup:
    """Choose schedule mode: cycle, weekdays, or free."""
    buttons = [
        [
            InlineKeyboardButton(text="🔄 Циклический (5/2 и т.д.)", callback_data="schedule:cycle"),
        ],
        [
            InlineKeyboardButton(text="📅 По дням недели", callback_data="schedule:weekdays"),
        ],
        [
            InlineKeyboardButton(text="🆓 Свободный график", callback_data="schedule:free"),
        ],
        [
            InlineKeyboardButton(text="⏱️ Интервал между записями", callback_data="schedule:interval"),
        ],
        [
            InlineKeyboardButton(text="🍽️ Время обеда", callback_data="schedule:break"),
        ],
        [
            InlineKeyboardButton(text="⏰ Время работы (начало/конец)", callback_data="schedule:hours"),
        ],
        
        [
            InlineKeyboardButton(text="✅ Готово", callback_data="schedule:done"),
            InlineKeyboardButton(text="◀ Назад", callback_data="admin:menu"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def schedule_cycle_pattern_keyboard() -> InlineKeyboardMarkup:
    """Predefined cycle patterns: 5/2, 2/2, 4/3, etc."""
    buttons = [
        [
            InlineKeyboardButton(text="5/2 (5 работ, 2 выходных)", callback_data="cycle_pattern:5/2"),
            InlineKeyboardButton(text="2/2 (2 работ, 2 выходных)", callback_data="cycle_pattern:2/2"),
        ],
        [
            InlineKeyboardButton(text="4/3 (4 работ, 3 выходных)", callback_data="cycle_pattern:4/3"),
            InlineKeyboardButton(text="3/3 (3 работ, 3 выходных)", callback_data="cycle_pattern:3/3"),
        ],
        [
            InlineKeyboardButton(text="✍️ Свой паттерн", callback_data="cycle_pattern:custom"),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:main"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def weekday_keyboard(
    selected_days: set[int] | None = None,
    toggle_cb_name: str = "weekday_toggle",
    confirm_cb_name: str = "weekday_confirm",
    cancel_cb_name: str = "schedule:main",
) -> InlineKeyboardMarkup:
    """Select working days of the week (0=Пн, 1=Вт, ..., 6=Вс).

    `toggle_cb_name`, `confirm_cb_name` and `cancel_cb_name` allow callers
    to customize callback_data names (used by the setup wizard vs main
    schedule handlers). Defaults preserve existing behaviour.
    """
    if selected_days is None:
        selected_days = {0, 1, 2, 3, 4}  # Mon-Fri by default

    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    buttons = []

    # Days in rows
    for i in range(0, 7, 3):
        row = []
        for j in range(3):
            if i + j < 7:
                day_idx = i + j
                is_selected = day_idx in selected_days
                row.append(InlineKeyboardButton(
                    text=f"{'✅' if is_selected else '❌'} {days[day_idx]}",
                    callback_data=f"{toggle_cb_name}:{day_idx}"
                ))
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=confirm_cb_name),
        InlineKeyboardButton(text="◀ Отмена", callback_data=cancel_cb_name),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def interval_selection_keyboard() -> InlineKeyboardMarkup:
    """Select time slot interval in minutes."""
    buttons = [
        [
            InlineKeyboardButton(text="15 минут", callback_data="interval:15"),
            InlineKeyboardButton(text="30 минут", callback_data="interval:30"),
        ],
        [
            InlineKeyboardButton(text="45 минут", callback_data="interval:45"),
            InlineKeyboardButton(text="60 минут", callback_data="interval:60"),
        ],
        [
            InlineKeyboardButton(text="Другое", callback_data="interval:custom"),
        ],
        [
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:main"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def schedule_back_keyboard() -> InlineKeyboardMarkup:
    """Back button to schedule menu."""
    buttons = [
        [
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:main"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
