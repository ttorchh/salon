"""Schedule command handlers for admin bot."""

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime
import logging

from app.config import get_tz_sync
from app.date_utils import format_date_for_display, normalize_date_to_iso
from app.services.admin_service import AdminService
from app.admin_bot.schedule_keyboards import (
    schedule_mode_keyboard,
    schedule_cycle_pattern_keyboard,
    weekday_keyboard,
    interval_selection_keyboard,
)

logger = logging.getLogger(__name__)
schedule_router = Router()


# FSM States
class AdminScheduleStates(StatesGroup):
    choose_mode = State()  # cycle, weekdays, free
    cycle_pattern = State()  # e.g. 5/2
    cycle_start_date = State()  # e.g. 20-04-2026
    weekdays_select = State()  # Multi-day selection
    select_interval = State()  # 15, 30, 45, 60 min
    custom_interval = State()  # Custom interval input
    set_break_start = State()  # HH:MM
    set_break_end = State()  # HH:MM
    set_start_time = State()  # HH:MM (начало разлиновки)
    set_end_time = State()  # HH:MM (конец разлиновки)


def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    from app.config import ADMIN_IDS
    return user_id in ADMIN_IDS

def today_display_date() -> str:
    """Return today's date in DD-MM-YYYY for prompts."""
    return format_date_for_display(datetime.now(get_tz_sync()).date().isoformat())

@schedule_router.message(Command("schedule"))
async def schedule_command(message: types.Message, state: FSMContext) -> None:
    """Start schedule configuration."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    await message.answer(
        "⚙️ <b>Настройка расписания работы</b>\n\n"
        "Выберите режим работы:",
        parse_mode="HTML",
        reply_markup=schedule_mode_keyboard()
    )
    await state.set_state(AdminScheduleStates.choose_mode)

@schedule_router.callback_query(F.data == "schedule:settings")
async def schedule_settings(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    await callback.message.answer(
        "⚙️ <b>Настройка расписания работы</b>\n\n"
        "Выберите режим работы:",
        parse_mode="HTML",
        reply_markup=schedule_mode_keyboard()
    )
    await state.set_state(AdminScheduleStates.choose_mode)

    await callback.answer()

@schedule_router.callback_query(F.data == "schedule:cycle")
async def schedule_cycle_mode(query: types.CallbackQuery, state: FSMContext) -> None:
    """Start cyclic schedule setup."""
    await query.message.edit_text(
        "🔄 <b>Циклический график</b>\n\n"
        "Выберите паттерн (например, 5/2 = 5 дней работы, 2 дня выходных):",
        parse_mode="HTML",
        reply_markup=schedule_cycle_pattern_keyboard()
    )
    await state.set_state(AdminScheduleStates.cycle_pattern)


@schedule_router.callback_query(F.data.startswith("cycle_pattern:"))
async def set_cycle_pattern(query: types.CallbackQuery, state: FSMContext) -> None:
    """Set cycle pattern."""
    pattern = query.data.split(":")[1]
    
    if pattern == "custom":
        await query.message.edit_text(
            "Введите паттерн в формате X/Y (например 5/2):\n\n"
            "Где X - количество рабочих дней, Y - количество выходных",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀ Назад", callback_data="schedule:cycle")
            ]])
        )
        await state.update_data(cycle_pattern="custom_input")
        await state.set_state(AdminScheduleStates.cycle_pattern)
        return
    
    await state.update_data(cycle_pattern=pattern)
    
    today = datetime.now(get_tz_sync()).strftime("%d-%m-%Y")
    
    await query.message.edit_text(
        f"Паттерн установлен: <b>{pattern}</b>\n\n"
        f"Введите дату начала цикла (формат DD-MM-YYYY):\n"
        f"<i>Текущая дата: {today}</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:cycle")
        ]])
    )
    await state.set_state(AdminScheduleStates.cycle_start_date)



@schedule_router.message(AdminScheduleStates.cycle_pattern)
async def handle_custom_cycle_pattern(message: types.Message, state: FSMContext) -> None:
    """Handle custom cycle pattern input (X/Y format)."""
    pattern_str = message.text.strip()
    
    # Validate format X/Y
    if '/' not in pattern_str:
        await message.answer("❌ Неверный формат. Используйте X/Y (например 5/2)")
        return
    
    try:
        parts = pattern_str.split('/')
        if len(parts) != 2:
            raise ValueError("Должны быть две части через слеш")
        work_days = int(parts[0])
        rest_days = int(parts[1])
        if work_days <= 0 or rest_days <= 0:
            raise ValueError("Оба числа должны быть больше нуля")
    except (ValueError, IndexError) as e:
        await message.answer("❌ Неверный формат. Введите две положительные цифры через слеш (например 5/2)")
        return
    
    # Store the pattern and ask for start date
    await state.update_data(cycle_pattern=pattern_str)
    
    today = datetime.now(get_tz_sync()).strftime("%d-%m-%Y")
    
    await message.answer(
        f"✅ Паттерн установлен: <b>{pattern_str}</b>\n\n"
        f"Введите дату начала цикла (формат DD-MM-YYYY):\n"
        f"<i>Текущая дата: {today}</i>",
        parse_mode="HTML",
    )
    await state.set_state(AdminScheduleStates.cycle_start_date)


@schedule_router.message(AdminScheduleStates.cycle_start_date)
async def set_cycle_start_date(message: types.Message, state: FSMContext) -> None:
    """Set cycle start date or open a non-working day."""
    date_str = message.text.strip()
    
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте DD-MM-YYYY (например 20-04-2026)")
        return
    
    data = await state.get_data()
    
    # Check if we're in "open day" mode
    if data.get("open_day_mode"):
        await AdminService.open_nonworking_day(date_str)
        await message.answer(
            f"✅ <b>Выходной день открыт!</b>\n\n"
            f"📅 Дата: {date_str}\n"
            f"✓ День теперь доступен для бронирования",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
        await state.set_state(AdminScheduleStates.choose_mode)
        return
    
    # Normal cycle pattern mode
    pattern = data.get("cycle_pattern")
    
    success, msg = await AdminService.set_schedule_cycle(pattern, date_str)
    
    if success:
        await message.answer(
            f"✅ {msg}\n\n"
            f"📋 Установлено:\n"
            f"  • Паттерн: {pattern}\n"
            f"  • Начало: {date_str}",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await message.answer(
            f"⚠️ {msg}\n\n"
            f"Возможно, есть записи на выходные дни. "
            f"Удалите их или выберите другую дату.",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:weekdays")
async def schedule_weekdays_mode(query: types.CallbackQuery, state: FSMContext) -> None:
    """Start weekdays schedule setup."""
    await query.message.edit_text(
        "📅 <b>Выберите рабочие дни недели</b>\n\n"
        "Нажмите на день чтобы переключить (✅ = работаем):",
        parse_mode="HTML",
        reply_markup=weekday_keyboard()
    )
    await state.set_state(AdminScheduleStates.weekdays_select)
    await state.update_data(selected_days={0, 1, 2, 3, 4})


@schedule_router.callback_query(F.data.startswith("weekday_toggle:"))
async def toggle_weekday(query: types.CallbackQuery, state: FSMContext) -> None:
    """Toggle a weekday."""
    day_idx = int(query.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("selected_days", {0, 1, 2, 3, 4}))
    
    if day_idx in selected:
        selected.remove(day_idx)
    else:
        selected.add(day_idx)
    
    await state.update_data(selected_days=selected)
    
    await query.message.edit_reply_markup(
        reply_markup=weekday_keyboard(selected)
    )


@schedule_router.callback_query(F.data == "weekday_confirm")
async def confirm_weekdays(query: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm weekdays selection."""
    data = await state.get_data()
    selected_days = sorted(data.get("selected_days", {0, 1, 2, 3, 4}))
    
    if not selected_days:
        await query.answer("⚠️ Выберите хотя бы один день", show_alert=True)
        return
    
    working_days_str = ",".join(str(d) for d in selected_days)
    days_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    days_text = ", ".join(days_names[d] for d in selected_days)
    
    success, msg = await AdminService.set_schedule_weekdays(working_days_str)
    
    if success:
        await query.message.edit_text(
            f"✅ {msg}\n\n"
            f"📋 Рабочие дни: {days_text}",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await query.message.edit_text(
            f"⚠️ {msg}\n\n"
            f"Возможно, есть записи на выходные дни.",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:free")
async def schedule_free_mode(query: types.CallbackQuery, state: FSMContext) -> None:
    """Set free schedule mode."""
    success, msg = await AdminService.set_schedule_free()
    
    if success:
        await query.message.edit_text(
            f"✅ {msg}\n\n"
            "🆓 В свободном режиме работаем каждый день.\n"
            "Выходные дни можно блокировать кнопкой '📆 График'",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await query.message.edit_text(
            f"❌ Ошибка при установке свободного режима",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:interval")
async def schedule_interval(query: types.CallbackQuery, state: FSMContext) -> None:
    """Set time slot interval."""
    await query.message.edit_text(
        "⏱️ <b>Выберите интервал между записями</b>",
        parse_mode="HTML",
        reply_markup=interval_selection_keyboard()
    )
    await state.set_state(AdminScheduleStates.select_interval)


@schedule_router.callback_query(F.data.startswith("interval:"))
async def set_interval(query: types.CallbackQuery, state: FSMContext) -> None:
    """Set interval."""
    data_part = query.data.split(":")[1]
    
    if data_part == "custom":
        await query.message.edit_text(
            "⏱️ <b>Введите интервал в минутах</b>\n\n"
            "Укажите целое число больше 0 (например, 10, 20, 25):\n\n"
            "<i>Минимальный интервал: 5 минут</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀ Назад", callback_data="schedule:interval")
            ]])
        )
        await state.set_state(AdminScheduleStates.custom_interval)
        await query.answer()
        return
    
    interval = int(data_part)
    
    success = await AdminService.update_interval(interval)
    
    if success:
        await query.message.edit_text(
            f"✅ Интервал установлен: <b>{interval} минут</b>",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await query.message.edit_text(
            "❌ Ошибка при установке интервала",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:break")
async def schedule_break_setup(query: types.CallbackQuery, state: FSMContext) -> None:
    """Start break time setup."""
    await query.message.edit_text(
        "🍽️ <b>Время обеда</b>\n\n"
        "Введите время начала обеда (HH:MM, например 13:00):\n\n"
        "<i>Или отправьте /skip для отключения</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:main")
        ]])
    )
    await state.set_state(AdminScheduleStates.set_break_start)


@schedule_router.message(AdminScheduleStates.set_break_start)
async def set_break_start(message: types.Message, state: FSMContext) -> None:
    """Set break start time."""
    if message.text == "/skip":
        await AdminService.set_break_time(None, None)
        await message.answer(
            "✅ Время обеда отключено",
            reply_markup=schedule_mode_keyboard()
        )
        await state.set_state(AdminScheduleStates.choose_mode)
        return
    
    time_str = message.text.strip()
    
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте HH:MM (например 13:00)")
        return
    
    await state.update_data(break_start=time_str)
    
    await message.answer(
        f"Начало обеда: <b>{time_str}</b>\n\n"
        "Введите время конца обеда (HH:MM):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:break")
        ]])
    )
    await state.set_state(AdminScheduleStates.set_break_end)


@schedule_router.message(AdminScheduleStates.set_break_end)
async def set_break_end(message: types.Message, state: FSMContext) -> None:
    """Set break end time."""
    time_str = message.text.strip()
    
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте HH:MM (например 14:00)")
        return
    
    data = await state.get_data()
    break_start = data.get("break_start")
    
    success = await AdminService.set_break_time(break_start, time_str)
    
    if success:
        await message.answer(
            f"✅ Время обеда установлено\n\n"
            f"📋 Обед: {break_start} - {time_str}",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await message.answer(
            "❌ Ошибка при установке времени обеда",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:hours")
async def schedule_hours_setup(query: types.CallbackQuery, state: FSMContext) -> None:
    """Start working hours setup."""
    await query.message.edit_text(
        "⏰ <b>Время работы (разлиновка)</b>\n\n"
        "Введите время начала работы (HH:MM, например 09:00):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:main")
        ]])
    )
    await state.set_state(AdminScheduleStates.set_start_time)


@schedule_router.message(AdminScheduleStates.set_start_time)
async def set_start_time(message: types.Message, state: FSMContext) -> None:
    """Set working hours start time."""
    time_str = message.text.strip()
    
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте HH:MM (например 09:00)")
        return
    
    await state.update_data(start_time=time_str)
    
    await message.answer(
        f"Начало работы: <b>{time_str}</b>\n\n"
        "Введите время конца работы (HH:MM):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:hours")
        ]])
    )
    await state.set_state(AdminScheduleStates.set_end_time)


@schedule_router.message(AdminScheduleStates.set_end_time)
async def set_end_time(message: types.Message, state: FSMContext) -> None:
    """Set working hours end time."""
    time_str = message.text.strip()
    
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте HH:MM (например 21:00)")
        return
    
    data = await state.get_data()
    start_time = data.get("start_time")
    
    success = await AdminService.set_working_hours(start_time, time_str)
    
    if success:
        await message.answer(
            f"✅ Время работы установлено\n\n"
            f"📋 Работа: {start_time} - {time_str}",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await message.answer(
            "❌ Ошибка при установке времени работы",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:main")
async def schedule_back_to_main(query: types.CallbackQuery, state: FSMContext) -> None:
    """Back to main schedule menu."""
    await query.message.edit_text(
        "⚙️ <b>Настройка расписания работы</b>\n\n"
        "Выберите опцию:",
        parse_mode="HTML",
        reply_markup=schedule_mode_keyboard()
    )
    await state.set_state(AdminScheduleStates.choose_mode)

@schedule_router.callback_query(F.data.startswith("cycle_pattern:"))
async def set_cycle_pattern(query: types.CallbackQuery, state: FSMContext) -> None:
    """Set cycle pattern."""
    from app.admin_bot.handlers import AdminScheduleStates
    from datetime import datetime
    
    pattern = query.data.split(":")[1]
    
    if pattern == "custom":
        await query.message.edit_text(
            "Введите паттерн в формате X/Y (например 5/2):\n\n"
            "Где X - количество рабочих дней, Y - количество выходных",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀ Назад", callback_data="schedule:cycle")
            ]])
        )
        await state.update_data(cycle_pattern="custom_input")
        await state.set_state(AdminScheduleStates.cycle_pattern)
        return
    
    await state.update_data(cycle_pattern=pattern)
    
    today = datetime.now(get_tz_sync()).strftime("%d-%m-%Y")
    
    await query.message.edit_text(
        f"Паттерн установлен: <b>{pattern}</b>\n\n"
        f"Введите дату начала цикла (формат DD-MM-YYYY):\n"
        f"<i>Текущая дата: {today}</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:cycle")
        ]])
    )
    await state.set_state(AdminScheduleStates.cycle_start_date)


@schedule_router.message(AdminScheduleStates.cycle_start_date)
async def set_cycle_start_date(message: types.Message, state: FSMContext) -> None:
    """Set cycle start date."""
    from app.admin_bot.handlers import AdminScheduleStates
    from datetime import datetime
    
    date_str = message.text.strip()
    
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте DD-MM-YYYY (например 20-04-2026)")
        return
    
    data = await state.get_data()
    pattern = data.get("cycle_pattern")
    
    success, msg = await AdminService.set_schedule_cycle(pattern, date_str)
    
    if success:
        await message.answer(
            f"✅ {msg}\n\n"
            f"📋 Установлено:\n"
            f"  • Паттерн: {pattern}\n"
            f"  • Начало: {date_str}",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await message.answer(
            f"⚠️ {msg}\n\n"
            f"Возможно, есть записи на выходные дни. "
            f"Удалите их или выберите другую дату.",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:weekdays")
async def schedule_weekdays_mode(query: types.CallbackQuery, state: FSMContext) -> None:
    """Start weekdays schedule setup."""
    from app.admin_bot.handlers import AdminScheduleStates
    
    await query.message.edit_text(
        "📅 <b>Выберите рабочие дни недели</b>\n\n"
        "Нажмите на день чтобы переключить (✅ = работаем):",
        parse_mode="HTML",
        reply_markup=weekday_keyboard()
    )
    await state.set_state(AdminScheduleStates.weekdays_select)
    await state.update_data(selected_days={0, 1, 2, 3, 4})


@schedule_router.callback_query(F.data.startswith("weekday_toggle:"))
async def toggle_weekday(query: types.CallbackQuery, state: FSMContext) -> None:
    """Toggle a weekday."""
    day_idx = int(query.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("selected_days", {0, 1, 2, 3, 4}))
    
    if day_idx in selected:
        selected.remove(day_idx)
    else:
        selected.add(day_idx)
    
    await state.update_data(selected_days=selected)
    
    await query.message.edit_reply_markup(
        reply_markup=weekday_keyboard(selected)
    )


@schedule_router.callback_query(F.data == "weekday_confirm")
async def confirm_weekdays(query: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm weekdays selection."""
    from app.admin_bot.handlers import AdminScheduleStates
    
    data = await state.get_data()
    selected_days = sorted(data.get("selected_days", {0, 1, 2, 3, 4}))
    
    if not selected_days:
        await query.answer("⚠️ Выберите хотя бы один день", show_alert=True)
        return
    
    working_days_str = ",".join(str(d) for d in selected_days)
    days_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    days_text = ", ".join(days_names[d] for d in selected_days)
    
    success, msg = await AdminService.set_schedule_weekdays(working_days_str)
    
    if success:
        await query.message.edit_text(
            f"✅ {msg}\n\n"
            f"📋 Рабочие дни: {days_text}",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await query.message.edit_text(
            f"⚠️ {msg}\n\n"
            f"Возможно, есть записи на выходные дни.",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:free")
async def schedule_free_mode(query: types.CallbackQuery, state: FSMContext) -> None:
    """Set free schedule mode."""
    from app.admin_bot.handlers import AdminScheduleStates
    
    success, msg = await AdminService.set_schedule_free()
    
    if success:
        await query.message.edit_text(
            f"✅ {msg}\n\n"
            "🆓 В свободном режиме работаем каждый день.\n"
            "Выходные дни можно блокировать кнопкой '📆 График'",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await query.message.edit_text(
            f"❌ Ошибка при установке свободного режима",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:interval")
async def schedule_interval(query: types.CallbackQuery, state: FSMContext) -> None:
    """Set time slot interval."""
    from app.admin_bot.handlers import AdminScheduleStates
    
    await query.message.edit_text(
        "⏱️ <b>Выберите интервал между записями</b>",
        parse_mode="HTML",
        reply_markup=interval_selection_keyboard()
    )
    await state.set_state(AdminScheduleStates.select_interval)


@schedule_router.callback_query(F.data.startswith("interval:"))
async def set_interval(query: types.CallbackQuery, state: FSMContext) -> None:
    """Set interval."""
    from app.admin_bot.handlers import AdminScheduleStates
    
    data_part = query.data.split(":")[1]
    
    if data_part == "custom":
        await query.message.edit_text(
            "⏱️ <b>Введите интервал в минутах</b>\n\n"
            "Укажите целое число больше 0 (например, 10, 20, 25):\n\n"
            "<i>Минимальный интервал: 5 минут</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀ Назад", callback_data="schedule:interval")
            ]])
        )
        await state.set_state(AdminScheduleStates.custom_interval)
        await query.answer()
        return
    
    interval = int(data_part)
    
    success = await AdminService.update_interval(interval)
    
    if success:
        await query.message.edit_text(
            f"✅ Интервал установлен: <b>{interval} минут</b>",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await query.message.edit_text(
            "❌ Ошибка при установке интервала",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:break")
async def schedule_break_setup(query: types.CallbackQuery, state: FSMContext) -> None:
    """Start break time setup."""
    from app.admin_bot.handlers import AdminScheduleStates
    
    await query.message.edit_text(
        "🍽️ <b>Время обеда</b>\n\n"
        "Введите время начала обеда (HH:MM, например 13:00):\n\n"
        "<i>Или отправьте /skip для отключения</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:main")
        ]])
    )
    await state.set_state(AdminScheduleStates.set_break_start)


@schedule_router.message(AdminScheduleStates.set_break_start)
async def set_break_start(message: types.Message, state: FSMContext) -> None:
    """Set break start time."""
    from app.admin_bot.handlers import AdminScheduleStates
    from datetime import datetime
    
    if message.text == "/skip":
        await AdminService.set_break_time(None, None)
        await message.answer(
            "✅ Время обеда отключено",
            reply_markup=schedule_mode_keyboard()
        )
        await state.set_state(AdminScheduleStates.choose_mode)
        return
    
    time_str = message.text.strip()
    
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте HH:MM (например 13:00)")
        return
    
    await state.update_data(break_start=time_str)
    
    await message.answer(
        f"Начало обеда: <b>{time_str}</b>\n\n"
        "Введите время конца обеда (HH:MM):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:break")
        ]])
    )
    await state.set_state(AdminScheduleStates.set_break_end)


@schedule_router.message(AdminScheduleStates.set_break_end)
async def set_break_end(message: types.Message, state: FSMContext) -> None:
    """Set break end time."""
    from app.admin_bot.handlers import AdminScheduleStates
    from datetime import datetime
    
    time_str = message.text.strip()
    
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте HH:MM (например 14:00)")
        return
    
    data = await state.get_data()
    break_start = data.get("break_start")
    
    success = await AdminService.set_break_time(break_start, time_str)
    
    if success:
        await message.answer(
            f"✅ Время обеда установлено\n\n"
            f"📋 Обед: {break_start} - {time_str}",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await message.answer(
            "❌ Ошибка при установке времени обеда",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:main")
async def schedule_back_to_main(query: types.CallbackQuery, state: FSMContext) -> None:
    """Back to main schedule menu."""
    from app.admin_bot.handlers import AdminScheduleStates
    
    await query.message.edit_text(
        "⚙️ <b>Настройка расписания работы</b>\n\n"
        "Выберите опцию:",
        parse_mode="HTML",
        reply_markup=schedule_mode_keyboard()
    )
    await state.set_state(AdminScheduleStates.choose_mode)


@schedule_router.callback_query(F.data == "schedule:done")
async def schedule_done(query: types.CallbackQuery, state: FSMContext) -> None:
    """Finish schedule setup and show instructions."""
    await state.clear()
    
    # Get current settings
    settings = await AdminService.get_schedule_settings()
    mode = settings.get("mode", "cycle")
    
    # Build mode description
    if mode == "cycle":
        pattern = settings.get("cycle_pattern", "5/2")
        start_date = settings.get("cycle_start_date", "не установлено")
        mode_desc = f"🔄 Циклический: {pattern}\nНачало: {start_date}"
    elif mode == "weekdays":
        working_days = settings.get("working_days", "0,1,2,3,4")
        days_idx = [int(d) for d in working_days.split(",")]
        days_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        days_text = ", ".join(days_names[d] for d in days_idx)
        mode_desc = f"📅 По дням: {days_text}"
    else:  # free
        mode_desc = "🆓 Свободный график (все дни работаем)"
    
    interval = settings.get("interval_minutes", "30")
    break_info = ""
    if settings.get("break_start"):
        break_info = f"\n🍽️ Обед: {settings.get('break_start')} - {settings.get('break_end')}"
    
    instruction = f"""
    ✅ <b>Расписание сохранено!</b>

    {mode_desc}
    ⏱️ Интервал: {interval} минут{break_info}

    Управление расписанием — кнопка «📅 График» в меню.
    Изменить настройки — /schedule
    """
    
    await query.message.delete()
    await query.message.answer(instruction, parse_mode="HTML")
    await query.answer()


@schedule_router.callback_query(F.data == "schedule:open_day")
async def open_nonworking_day(query: types.CallbackQuery, state: FSMContext) -> None:
    """Start opening a non-working day."""
    await state.set_state(AdminScheduleStates.cycle_start_date)
    await state.update_data(open_day_mode=True)
    
    await query.message.edit_text(
        "📖 <b>Открыть выходной день</b>\n\n"
        "Введите дату в формате DD-MM-YYYY\n"
        "Пример: 20-04-2026",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ Назад", callback_data="schedule:main")
        ]])
    )
    await query.answer()


@schedule_router.message(AdminScheduleStates.custom_interval)
async def set_custom_interval(message: types.Message, state: FSMContext) -> None:
    """Process custom interval input."""
    from app.admin_bot.handlers import AdminScheduleStates
    try:
        interval = int(message.text.strip())
        if interval <= 0:
            raise ValueError("Interval must be positive")
        if interval < 5:
            await message.answer(
                "❌ Минимальный интервал: <b>5 минут</b>\n\n"
                "Введите число от 5 и выше:",
                parse_mode="HTML"
            )
            return
    except ValueError:
        await message.answer(
            "❌ Неверный формат\n\n"
            "Введите целое число больше 0 (например, 10, 20, 25):",
            parse_mode="HTML"
        )
        return
    
    success = await AdminService.update_interval(interval)
    
    if success:
        await message.answer(
            f"✅ Интервал установлен: <b>{interval} минут</b>",
            parse_mode="HTML",
            reply_markup=schedule_mode_keyboard()
        )
    else:
        await message.answer(
            "❌ Ошибка при установке интервала",
            reply_markup=schedule_mode_keyboard()
        )
    
    await state.set_state(AdminScheduleStates.choose_mode)


