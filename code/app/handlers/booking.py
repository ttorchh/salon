from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from datetime import datetime
import logging
from app.config import get_tz_sync

from aiogram.filters.callback_data import CallbackData

from app.keyboards.calendar import CalendarAction, CalendarDate, TimeSelect, time_selection_keyboard, get_calendar_with_blocked_dates
from app.keyboards.booking import (
    BookingAction, ServiceSelect, MenuAction,
    confirm_booking_keyboard, service_selection_keyboard,
)
from app.services.booking_service import BookingService
from app.services.notification_service import NotificationService
from app.services.catalog_service import CatalogService

router = Router()
logger = logging.getLogger(__name__)


class NoteAction(CallbackData, prefix="note"):
    action: str


class CancelApt(CallbackData, prefix="cancel_apt"):
    appointment_id: int


class Reschedule(CallbackData, prefix="reschedule"):
    appointment_id: int


def format_date_for_display(date_str: str) -> str:
    """Convert date from YYYY-MM-DD to DD-MM-YYYY format for display."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%m-%Y")
    except:
        return date_str


class BookingStates(StatesGroup):
    service = State()
    date = State()
    time = State()
    note = State()
    confirming = State()  # Flag to prevent duplicate confirmation processing


class RescheduleStates(StatesGroup):
    reschedule_date = State()
    reschedule_time = State()


@router.callback_query(BookingAction.filter(F.action == "start"))
async def booking_start(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    services = await CatalogService.list_services()
    if not services:
        await callback_query.answer("Пока нет доступных услуг. Попробуйте позже.", show_alert=True)
        return

    await state.set_state(BookingStates.service)
    await callback_query.message.edit_text(
        "Выберите услугу для записи:",
        reply_markup=service_selection_keyboard(services),
    )
    await callback_query.answer()

@router.callback_query(ServiceSelect.filter(), BookingStates.service)
async def service_selected(callback_query: types.CallbackQuery, state: FSMContext, callback_data: ServiceSelect) -> None:
    service_id = callback_data.service_id
    service = await CatalogService.get_service(service_id)
    if not service:
        await callback_query.answer("Услуга не найдена", show_alert=True)
        return
    
    await state.update_data(service_id=service_id, service_name=service["name"], service_duration=service["duration"])
    await state.set_state(BookingStates.date)
    
    # Show calendar with blocked dates
    today = datetime.now(get_tz_sync())
    calendar_kb = await get_calendar_with_blocked_dates(today.year, today.month)
    
    # Send service photo if available
    from app.services.admin_service import AdminService
    from app.config import SERVICE_IMAGES_DIR
    from pathlib import Path
    
    photo_filename = await AdminService.get_service_photo(service_id)
    
    if photo_filename:
        photo_path = SERVICE_IMAGES_DIR / photo_filename
        if photo_path.exists():
            try:
                await callback_query.message.delete()
                await callback_query.message.answer_photo(
                    photo=FSInputFile(str(photo_path)),
                    caption=f"📸 {service['name']}\n💰 Цена: {service['price']}₽\n⏱️ Длительность: {service['duration']} мин\n\nВыберите дату записи:",
                    reply_markup=calendar_kb,
                )
            except Exception as e:
                logger.error(f"Error sending service photo: {e}")
                await callback_query.message.edit_text(
                    f"📸 {service['name']}\n💰 Цена: {service['price']}₽\n⏱️ Длительность: {service['duration']} мин\n\nВыберите дату записи:",
                    reply_markup=calendar_kb,
                )
        else:
            # Photo file not found, show without photo
            await callback_query.message.edit_text(
                f"📸 {service['name']}\n💰 Цена: {service['price']}₽\n⏱️ Длительность: {service['duration']} мин\n\nВыберите дату записи:",
                reply_markup=calendar_kb,
            )
    else:
        await callback_query.message.edit_text(
            f"Вы выбрали: {service['name']}\n💰 Цена: {service['price']}₽\n⏱️ Длительность: {service['duration']} мин\n\nВыберите дату записи:",
            reply_markup=calendar_kb,
        )
    await callback_query.answer()

@router.callback_query(CalendarAction.filter(), StateFilter(BookingStates.date, RescheduleStates.reschedule_date))
async def calendar_month_change(callback_query: types.CallbackQuery, callback_data: CalendarAction) -> None:
    year = callback_data.year
    month = callback_data.month
    
    calendar_kb = await get_calendar_with_blocked_dates(year, month)
    await callback_query.message.edit_reply_markup(
        reply_markup=calendar_kb,
    )
    await callback_query.answer()

@router.callback_query(CalendarDate.filter(), BookingStates.date)
async def calendar_date_selected(callback_query: types.CallbackQuery, state: FSMContext, callback_data: CalendarDate) -> None:
    import logging
    logger = logging.getLogger(__name__)
    
    appointment_date = callback_data.date
    data = await state.get_data()
    service_id = data.get("service_id")
    
    logger.debug(f"calendar_date_selected: date={appointment_date}, service_id={service_id}")
    
    # Check if service_id is set
    if not service_id:
        logger.warning(f"No service_id found in state for booking")
        await callback_query.answer("❌ Ошибка: услуга не выбрана. Начните бронирование заново.", show_alert=True)
        return
    
    # Get available times
    try:
        available_times = await BookingService.get_available_times(appointment_date, service_id)
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        await callback_query.answer(f"❌ Ошибка валидации: {e}", show_alert=True)
        return
    except Exception as e:
        logger.error(f"Unexpected error getting available times: {e}")
        await callback_query.answer(f"❌ Ошибка при загрузке времени: {e}", show_alert=True)
        return
    
    if not available_times:
        await callback_query.answer("На эту дату нет доступных времени", show_alert=True)
        return
    
    await state.update_data(appointment_date=appointment_date)
    await state.set_state(BookingStates.time)
    
    # Delete old message (may contain photo) and send new one with time selection
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    
    await callback_query.message.answer(
        f"Выберите время записи для {format_date_for_display(appointment_date)}:",
        reply_markup=time_selection_keyboard(available_times),
    )
    await callback_query.answer()

@router.callback_query(TimeSelect.filter(), BookingStates.time)
async def time_selected(callback_query: types.CallbackQuery, state: FSMContext, callback_data: TimeSelect) -> None:
    appointment_time = callback_data.time.replace('.', ':')
    await state.update_data(appointment_time=appointment_time)
    await state.set_state(BookingStates.note)
    
    # Delete old message and send new one
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    
    await callback_query.message.answer(
        "Напишите пожелания мастеру или отправьте «Нет», если без пожеланий.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Без пожеланий", callback_data=NoteAction(action="none").pack())]
        ]),
    )
    await callback_query.answer()

@router.message(BookingStates.note)
async def booking_note(message: types.Message, state: FSMContext) -> None:
    note = message.text.strip()
    data = await state.get_data()
    service = await CatalogService.get_service(data["service_id"])
    
    duration_info = f"({data['service_duration']} мин)" if data.get("service_duration") else ""
    
    summary = (
        f"Проверка записи:\n\n"
        f"Услуга: {service['name']} {duration_info}\n"
        f"Дата: {format_date_for_display(data['appointment_date'])}\n"
        f"Время: {data['appointment_time']}\n"
        f"Пожелания: {note if note.lower() != 'нет' else 'без пожеланий'}"
    )
    await state.update_data(note=note)
    await message.answer(summary, reply_markup=confirm_booking_keyboard())

@router.callback_query(NoteAction.filter(), BookingStates.note)
async def quick_note(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    await callback_query.answer()
    
    data = await state.get_data()
    service = await CatalogService.get_service(data["service_id"])
    
    duration_info = f"({data['service_duration']} мин)" if data.get("service_duration") else ""
    
    summary = (
        f"Проверка записи:\n\n"
        f"Услуга: {service['name']} {duration_info}\n"
        f"Дата: {format_date_for_display(data['appointment_date'])}\n"
        f"Время: {data['appointment_time']}\n"
        f"Пожелания: без пожеланий"
    )
    await state.update_data(note="Нет")
    
    # Delete old message and send new one
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    
    await callback_query.message.answer(summary, reply_markup=confirm_booking_keyboard())

@router.callback_query(BookingAction.filter(F.action == "confirm"), StateFilter(BookingStates.note, BookingStates.confirming))
async def confirm_booking(callback_query: types.CallbackQuery, state: FSMContext, bot: Bot) -> None:
    current_state = await state.get_state()
    if current_state == "BookingStates:confirming":
        await callback_query.answer()
        return

    # Mark as confirming to prevent duplicates
    await state.set_state(BookingStates.confirming)

    # Answer immediately to avoid timeout
    await callback_query.answer()

    # Show loading state - delete old message and send new one
    loading_message = None
    try:
        await callback_query.message.delete()
        loading_message = await callback_query.message.answer("⏳ Обрабатываю запись...")
    except Exception:
        try:
            await callback_query.message.edit_text("⏳ Обрабатываю запись...")
        except Exception:
            pass

    try:
        data = await state.get_data()
        client_id = await BookingService.get_or_create_client(
            telegram_id=callback_query.from_user.id,
            first_name=callback_query.from_user.first_name,
            last_name=callback_query.from_user.last_name,
        )

        apt_id = await BookingService.create_appointment(
            client_id=client_id,
            service_id=data["service_id"],
            appointment_date=data["appointment_date"],
            appointment_time=data["appointment_time"],
            note=data["note"],
        )

        # Get service name for notification
        from app.database import get_connection
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT name FROM services WHERE id = ?", (data["service_id"],))
                row = await cursor.fetchone()
                service_name = row[0] if row else "Услуга"

        # Get client data for notification
        client = await BookingService.get_client(callback_query.from_user.id)

        first_name = ""
        last_name = ""
        phone = ""

        if client:
            first_name = client.get("first_name", "") or ""
            last_name = client.get("last_name", "") or ""
            phone = client.get("phone", "") or ""

        # Fallback to Telegram names if not in database
        if not first_name:
            first_name = callback_query.from_user.first_name or ""
        if not last_name:
            last_name = callback_query.from_user.last_name or ""

        # Also check FSM data for phone if database doesn't have it
        if not phone:
            phone = data.get("phone", "")

        # Get note from state
        note = data.get("note", "")

        # Send notification to admin
        await NotificationService.notify_admin_appointment_created(
            appointment_id=apt_id,
            first_name=first_name,
            last_name=last_name,
            service_name=service_name,
            date=data["appointment_date"],
            time=data["appointment_time"],
            phone=phone,
            note=note,
        )

        await state.clear()

        # Edit loading message with success
        target = loading_message or callback_query.message
        await target.edit_text(
            "✅ Запись принята! Напомним за день и за час до визита.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
            ]),
        )
    except Exception as e:
        logger.error(f"Error confirming booking: {e}")

        target = loading_message or callback_query.message
        try:
            await target.delete()
        except Exception:
            pass

        await callback_query.message.answer(
            f"❌ Ошибка при подтверждении записи: {e}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
            ]),
        )
@router.callback_query(
    BookingAction.filter(F.action == "cancel"),
    StateFilter(
        BookingStates.service,
        BookingStates.date,
        BookingStates.time,
        BookingStates.note,
        BookingStates.confirming,
    ),
)
async def cancel_booking_process(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    await callback_query.answer()
    
    await state.clear()
    
    # Delete old message and send cancellation message
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    
    await callback_query.message.answer(
        "❌ Бронирование отменено. Вернёмся в главное меню.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
        ]),
    )


@router.callback_query(CancelApt.filter())
async def cancel_appointment(callback_query: types.CallbackQuery, callback_data: CancelApt) -> None:
    appointment_id = callback_data.appointment_id
    
    # Show loading state - delete old message and send new one
    try:
        await callback_query.message.delete()
        await callback_query.message.answer("⏳ Отменяю запись...")
    except Exception:
        try:
            await callback_query.message.edit_text("⏳ Отменяю запись...")
        except Exception:
            pass
    
    try:
        # Get appointment details before cancellation
        from app.database import get_connection
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT c.first_name, c.last_name, c.phone, s.name, a.appointment_date, a.appointment_time "
                    "FROM appointments a "
                    "JOIN clients c ON c.id = a.client_id "
                    "JOIN services s ON s.id = a.service_id "
                    "WHERE a.id = ?",
                    (appointment_id,),
                )
                row = await cursor.fetchone()
        
        if row:
            first_name, last_name, phone, service_name, date, time = row
            
            # Send notification to user via user bot
            await NotificationService.notify_appointment_cancelled(
                callback_query.bot,
                appointment_id,
                reason="Отмена клиентом",
            )
            
            # Send admin notification
            await NotificationService.notify_admin_appointment_cancelled(
                first_name=first_name,
                last_name=last_name,
                service_name=service_name,
                date=date,
                time=time,
                phone=phone,
                reason="Отмена клиентом",
            )
        
        await BookingService.cancel_appointment(appointment_id)
        
        # Delete old message and send confirmation
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        
        await callback_query.message.answer(
            "❌ Запись отменена. Вы всегда можете записаться повторно.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
            ]),
        )
    except Exception as e:
        logger.error(f"Error cancelling appointment: {e}")
        
        # Delete old message and send error
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        
        await callback_query.message.answer(
            f"❌ Ошибка при отмене записи: {e}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
            ]),
        )


@router.callback_query(Reschedule.filter())
async def reschedule_appointment(callback_query: types.CallbackQuery, state: FSMContext, callback_data: Reschedule) -> None:
    appointment_id = callback_data.appointment_id
    await state.update_data(appointment_id=appointment_id)
    await state.set_state(RescheduleStates.reschedule_date)
    
    today = datetime.now(get_tz_sync())
    calendar_kb = await get_calendar_with_blocked_dates(today.year, today.month)
    await callback_query.message.edit_text(
        "📅 Выберите новую дату для записи:",
        reply_markup=calendar_kb,
    )
    await callback_query.answer()

@router.callback_query(CalendarDate.filter(), RescheduleStates.reschedule_date)
async def reschedule_select_date(callback_query: types.CallbackQuery, state: FSMContext, callback_data: CalendarDate) -> None:
    import logging
    logger = logging.getLogger(__name__)
    
    new_date = callback_data.date
    data = await state.get_data()
    appointment_id = data.get("appointment_id")
    
    logger.debug(f"Reschedule: appointment_id={appointment_id}, new_date={new_date}")
    
    if not appointment_id:
        await callback_query.answer("❌ Ошибка: ID записи не найден", show_alert=True)
        return
    
    # Fetch original appointment to get service_id
    from ..database import get_connection
    try:
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT service_id FROM appointments WHERE id = ?",
                    (appointment_id,),
                )
                row = await cursor.fetchone()
    except Exception as e:
        logger.error(f"Error fetching appointment: {e}")
        await callback_query.answer(f"❌ Ошибка при загрузке записи: {e}", show_alert=True)
        return
    
    if not row:
        logger.error(f"Appointment not found: id={appointment_id}")
        await callback_query.answer("❌ Запись не найдена", show_alert=True)
        return
    
    service_id = row[0]
    logger.debug(f"Fetched service_id={service_id} for appointment {appointment_id}")
    
    if service_id is None or service_id <= 0:
        logger.error(f"Invalid service_id: {service_id} for appointment {appointment_id}")
        await callback_query.answer("❌ Услуга не найдена в записи", show_alert=True)
        return
    
    await state.update_data(reschedule_date=new_date, service_id=service_id)
    await state.set_state(RescheduleStates.reschedule_time)
    
    # Get available times with correct service duration (exclude current appointment)
    try:
        available_times = await BookingService.get_available_times(new_date, service_id, exclude_appointment_id=appointment_id)
    except ValueError as e:
        logger.error(f"Validation error getting available times: {e}")
        await callback_query.answer(f"❌ Ошибка валидации: {e}", show_alert=True)
        return
    except Exception as e:
        logger.error(f"Unexpected error getting available times: {e}")
        await callback_query.answer(f"❌ Ошибка при загрузке времени: {e}", show_alert=True)
        return
    
    if not available_times:
        await callback_query.answer("На эту дату нет доступных времени", show_alert=True)
        return
    
    await callback_query.message.edit_text(
        f"⏰ Выберите время для {new_date}:",
        reply_markup=time_selection_keyboard(available_times),
    )
    await callback_query.answer()

@router.callback_query(TimeSelect.filter(), RescheduleStates.reschedule_time)
async def reschedule_select_time(callback_query: types.CallbackQuery, state: FSMContext, callback_data: TimeSelect) -> None:
    # Answer immediately to avoid timeout
    await callback_query.answer()
    
    new_time = callback_data.time.replace('.', ':')
    data = await state.get_data()
    appointment_id = data.get("appointment_id")
    reschedule_date = data.get("reschedule_date")
    telegram_id = callback_query.from_user.id
    
    # Show loading state to user
    await callback_query.message.edit_text("⏳ Обновляю запись...")
    
    try:
        # Get appointment details before moving (for notifications)
        from app.database import get_connection
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT c.first_name, c.last_name, c.phone, s.name, a.appointment_date, a.appointment_time "
                    "FROM appointments a "
                    "JOIN clients c ON c.id = a.client_id "
                    "JOIN services s ON s.id = a.service_id "
                    "WHERE a.id = ?",
                    (appointment_id,),
                )
                row = await cursor.fetchone()
        
        if not row:
            await callback_query.message.edit_text(
                "❌ Ошибка: запись не найдена",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
                ]),
            )
            return
        
        first_name, last_name, phone, service_name, old_date, old_time = row
        
        await BookingService.move_appointment(appointment_id, reschedule_date, new_time)
        
        # Send notification to user with old date/time passed explicitly
        await NotificationService.notify_appointment_rescheduled(
            callback_query.bot,
            appointment_id,
            reschedule_date,
            new_time,
            old_date=old_date,
            old_time=old_time,
        )
        
        # Send notification to admin
        await NotificationService.notify_admin_appointment_rescheduled(
            first_name=first_name,
            last_name=last_name,
            service_name=service_name,
            old_date=old_date,
            old_time=old_time,
            new_date=reschedule_date,
            new_time=new_time,
            phone=phone,
        )
        
        await state.clear()
        
        await callback_query.message.edit_text(
            f"✅ Запись перенесена на {reschedule_date} {new_time}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
            ]),
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error rescheduling appointment: {e}")
        await callback_query.message.edit_text(
            f"❌ Ошибка при переносе записи: {e}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
            ]),
        )
