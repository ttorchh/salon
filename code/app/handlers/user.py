from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
from pathlib import Path
import logging
import re

from aiogram.filters.callback_data import CallbackData

from app.config import ADMIN_IDS, get_tz_sync, DATA_DIR
from app.keyboards.booking import booking_keyboard, service_selection_keyboard, BookingAction
from app.handlers.booking import BookingStates
from app.keyboards.menu import main_menu_keyboard
from app.services.catalog_service import CatalogService
from app.services.booking_service import BookingService
from app.database import get_connection

router = Router()
logger = logging.getLogger(__name__)

# Global cache for static images to optimize sending
_PHOTO_FILE_ID_CACHE = {
    'pricelist': None,  # Will be set on first use
}


class PhoneAction(CallbackData, prefix="phone"):
    action: str


class ShowPrice(CallbackData, prefix="show_price"):
    pass


class ShowContacts(CallbackData, prefix="show_contacts"):
    pass


class MyApts(CallbackData, prefix="my_apts"):
    page: int = 1


class Feedback(CallbackData, prefix="feedback"):
    appointment_id: int


class CancelFeedback(CallbackData, prefix="cancel_feedback"):
    pass


class MenuAction(CallbackData, prefix="menu"):
    action: str


class Reschedule(CallbackData, prefix="reschedule"):
    appointment_id: int


class CancelApt(CallbackData, prefix="cancel_apt"):
    appointment_id: int

class FeedbackStates(StatesGroup):
    appointment_id = State()
    feedback_content = State()


class StartDialogStates(StatesGroup):
    """States for initial greeting dialog."""
    awaiting_name = State()
    awaiting_phone = State()


def main_menu_keyboard_inline() -> InlineKeyboardMarkup:
    """Inline fallback for callback screens that need a "back to main menu" action."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
        ]
    )


def is_appointment_passed(appointment_date: str, appointment_time: str) -> bool:
    """Check if appointment date/time has passed."""
    try:
        apt_datetime = datetime.fromisoformat(f"{appointment_date} {appointment_time}").replace(tzinfo=get_tz_sync())
        return apt_datetime < datetime.now(get_tz_sync())
    except:
        return False


def format_date_for_display(date_str: str) -> str:
    """Convert date from YYYY-MM-DD to DD-MM-YYYY format for display."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%m-%Y")
    except:
        return date_str


@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext) -> None:
    """Start command with greeting dialog."""
    user_id = message.from_user.id
    
    # Check if user is already in database
    async with get_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT first_name, last_name FROM clients WHERE telegram_id = ?",
                (user_id,),
            )
            client = await cursor.fetchone()
    
    # If user is already known, go directly to main menu
    if client:
        text = f"Добро пожаловать, {client[0]}! Какие планы на сегодня?😊"
        await message.answer(
            text,
            reply_markup=main_menu_keyboard()
        )
        return
    
    # New user - start greeting dialog
    await state.set_state(StartDialogStates.awaiting_name)
    text = (
        "Добро пожаловать! Я бот записи к мастеру.\n\n"
        "Давайте знакомиться. Как к вам обращаться? 😊"
    )
    await message.answer(text)


@router.message(StartDialogStates.awaiting_name)
async def process_user_name(message: Message, state: FSMContext) -> None:
    """Process user's name."""
    name = message.text.strip()
    
    if not name or len(name) > 100:
        await message.answer("❌ Пожалуйста, введите корректное имя (не более 100 символов)")
        return
    
    await state.update_data(name=name)
    await state.set_state(StartDialogStates.awaiting_phone)
    
    # Show skip button for phone
    buttons = [[InlineKeyboardButton(text="⏭️ Пропустить", callback_data=PhoneAction(action="skip").pack())]]
    
    text = f"Спасибо, {name}! 😊\n\nПодскажите ваш номер телефона (или пропустите):"
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.message(StartDialogStates.awaiting_phone)
async def process_user_phone(message: Message, state: FSMContext) -> None:
    """Process user's phone."""
    phone = message.text.strip()

    # Проверка допустимых символов
    if not re.fullmatch(r"[+\-\d\s]+", phone):
        await message.answer("❌ Номер может содержать только цифры, +, - и пробелы")
        return

    # Убираем всё кроме цифр для проверки длины
    digits = re.sub(r"\D", "", phone)

    if len(digits) < 7 or len(digits) > 15:
        await message.answer("❌ Некорректная длина номера телефона")
        return
    
    data = await state.get_data()
    name = data.get("name", "")
    
    # Save user to database
    await BookingService.get_or_create_client(
        telegram_id=message.from_user.id,
        first_name=name,
        last_name=message.from_user.last_name,
    )
    
    # Update phone if provided
    if phone:
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE clients SET phone = ? WHERE telegram_id = ?",
                    (phone, message.from_user.id),
                )
                await connection.commit()
    
    await state.clear()
    
    text = f"❤️ Спасибо! Теперь выбе​рите действие:"
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.callback_query(PhoneAction.filter(F.action == "skip"), StartDialogStates.awaiting_phone)
async def skip_phone(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Skip phone input."""
    data = await state.get_data()
    name = data.get("name", "")
    
    # Save user to database without phone
    await BookingService.get_or_create_client(
        telegram_id=callback_query.from_user.id,
        first_name=name,
        last_name=callback_query.from_user.last_name,
    )
    
    await state.clear()
    
    text = f"❤️ Спасибо! Теперь выберите действие:"
    await callback_query.answer()
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await callback_query.message.answer(text, reply_markup=main_menu_keyboard())

@router.message(F.text.in_(["🌸 Записаться", "записаться", "Записаться", "прийти", "Прийти", "забронировать", "Забронировать"]))
async def start_booking(message: Message, state: FSMContext | None = None) -> None:
    """Handle booking start from reply button (legacy support)."""
    services = await CatalogService.list_services()
    if not services:
        await message.answer('Пока нет доступных услуг. Попробуйте позже.')
        return
    if state is not None:
        await state.clear()
        await state.set_state(BookingStates.service)
    await message.answer(
        "Выберите услугу для записи:",
        reply_markup=service_selection_keyboard(services),
    )

@router.callback_query(ShowPrice.filter())
async def show_price_callback(callback_query: types.CallbackQuery) -> None:
    """Handle show price from inline button."""
    services = await CatalogService.list_services()
    if not services:
        await callback_query.answer("Прайс временно недоступен.", show_alert=True)
        return
    
    # Build text with services
    text = "💫 *НАШЕ МЕНЮ УСЛУГ:*\n\n"
    for item in services:
        text += f"*{item['name']}* — {item['price']} ₽\n⏱️ {item['duration']} мин\n{item['description']}\n\n"
    
    # Send image first if it exists
    price_image_path = Path(DATA_DIR) / "images" / "pricelist.jpg"
    if price_image_path.exists():
        try:
            await callback_query.message.answer_photo(
                photo=FSInputFile(str(price_image_path)),
                caption="✨ Прайс-лист",
            )
        except Exception as e:
            logger.error(f"Error sending pricelist image: {e}")
    
    await callback_query.message.answer(text, parse_mode="Markdown")
    await callback_query.answer()

@router.message(F.text.in_(["💰 Прайс", "прайс", "Прайс", "wtyf","прайс-лист", "Прайс-лист", "цена", "Цена", "стоимость", "Стоимость", "услуги", "Услуги"]))
async def show_price(message: Message) -> None:
    """Handle show price from reply button (legacy support)."""
    services = await CatalogService.list_services()
    if not services:
        await message.answer("Прайс временно недоступен.")
        return
    
    # Send image first if it exists
    price_image_path = Path(DATA_DIR) / "images" / "pricelist.jpg"
    if price_image_path.exists():
        try:
            await message.answer_photo(
                photo=FSInputFile(str(price_image_path)),
                caption="Прайс-лист",
            )
        except Exception as e:
            logger.error(f"Error sending pricelist image: {e}")
    
    # Then build and send text with services
    text = "💫 *НАШЕ МЕНЮ УСЛУГ:*\n\n"
    for item in services:
        text += f"*{item['name']}* — {item['price']} ₽\n⏱️ {item['duration']} мин\n{item['description']}\n\n"
    
    await message.answer(text, parse_mode="Markdown")

@router.callback_query(ShowContacts.filter())
async def show_contacts_callback(callback_query: types.CallbackQuery) -> None:
    """Handle show contacts from inline button."""
    from app.services.admin_service import AdminService
    
    contacts_text = await AdminService.get_salon_sandbox_contacts()
    
    if contacts_text:
        text = f"КОНТАКТЫ САЛОНА\n\n{contacts_text}"
    else:
        text = "❌ Контакты еще не добавлены администратором"
    
    await callback_query.message.edit_text(text)
    await callback_query.answer()

@router.message(F.text.in_(["📞 Контакты", "Контакты", "контакты", "rjynfrns", "адрес", "Адрес", "номер", "Номер"]))
async def show_contacts(message: Message) -> None:
    """Handle show contacts from reply button (legacy support)."""
    from app.services.admin_service import AdminService
    
    contacts_text = await AdminService.get_salon_sandbox_contacts()
    
    if contacts_text:
        text = f"КОНТАКТЫ САЛОНА\n\n{contacts_text}"
    else:
        text = "❌ Контакты еще не добавлены администратором"
    
    await message.answer(text)

@router.callback_query(MyApts.filter(F.page == 1))
async def my_appointments_callback(callback_query: types.CallbackQuery) -> None:
    """Handle my appointments from inline button."""
    appointments = await BookingService.list_client_appointments(callback_query.from_user.id)
    if not appointments:
        await callback_query.message.edit_text(
            "👤 У вас пока нет записей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]]),
        )
        await callback_query.answer()
        return
    
    # Show appointments with management buttons
    text = "📋 Ваши записи:\n\n"
    upcoming = []
    past = []
    
    for item in appointments:
        is_passed = is_appointment_passed(item['date'], item['time'])
        # Determine emoji based on status
        if item['status'] == 'cancelled':
            status_emoji = "❌"
        elif item['status'] == 'no-show':
            status_emoji = "👻"
        elif is_passed:
            status_emoji = "✨"
        else:
            status_emoji = "✅"
        
        text += (
            f"{status_emoji} {item['service_name']}\n"
            f"📅 {format_date_for_display(item['date'])} {item['time']}\n"
            f"💬 {item['note'] or 'без заметок'}\n"
        )
        
        # Skip cancelled and no-show appointments from action lists
        if item['status'] in ('cancelled', 'no-show'):
            continue
        if is_passed:
            past.append(item)
        else:
            upcoming.append(item)
    
    # Create inline keyboard with action buttons
    keyboard_buttons = []
    
    # Upcoming appointments
    for item in upcoming:
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"Перенести", callback_data=Reschedule(appointment_id=item['id']).pack()),
            InlineKeyboardButton(text="Отменить", callback_data=CancelApt(appointment_id=item['id']).pack()),
        ])
    
    # Past appointments
    for item in past:
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"Оставить отзыв", callback_data=Feedback(appointment_id=item['id']).pack()),
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())])
    
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))
    await callback_query.answer()

@router.message(Command("admin"))
async def admin_command(message: Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к админской панели.")
        return
    await message.answer(
        "Переходите в админ-бота для управления записями и услугами. "
        "Используйте отдельный токен админ-бота."
    )

@router.message(Command("book"))
async def book_command(message: Message, state: FSMContext | None = None) -> None:
    """Shortcut command for booking."""
    services = await CatalogService.list_services()
    if not services:
        await message.answer('Пока нет доступных услуг. Попробуйте позже.')
        return
    if state is not None:
        await state.clear()
        await state.set_state(BookingStates.service)
    await message.answer(
        "Выберите услугу:",
        reply_markup=service_selection_keyboard(services),
    )

@router.message(Command("feedback"))
async def feedback_command(message: Message) -> None:
    """Shortcut command to view appointments and leave feedback."""
    appointments = await BookingService.list_client_appointments(message.from_user.id)
    if not appointments:
        await message.answer(
            "👤 У вас пока нет записей.",
            reply_markup=main_menu_keyboard(),
        )
        return
    
    # Show appointments with structured format and feedback buttons
    text = "📋 Ваши записи:\n\n"
    upcoming = []
    past = []
    
    for item in appointments:
        is_passed = is_appointment_passed(item['date'], item['time'])
        
        # Build appointment text with structured format
        text += f"⏰ {item['time']} — {item['service_name']}\n"
        text += f"📅 {format_date_for_display(item['date'])}\n"
        
        if item['note']:
            text += f"💬 Пожелания: {item['note']}\n"
        else:
            text += f"💬 Пожелания: Нет\n"
        
        text += "\n"
        
        if is_passed:
            past.append(item)
        else:
            upcoming.append(item)
    
    # Build keyboard with past appointments' feedback buttons
    buttons = []
    for item in past:
        buttons.append([InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=Feedback(appointment_id=item['id']).pack())])
    
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

PER_PAGE_UPCOMING = 10
PER_PAGE_PAST = 10


async def render_my_appointments(message_obj, user_id: int, page: int = 1, edit: bool = False) -> None:
    appointments = await BookingService.list_client_appointments(user_id)

    if not appointments:
        text = "👤 У вас пока нет записей."
        if edit:
            await message_obj.edit_text(text, reply_markup=main_menu_keyboard_inline())
        else:
            await message_obj.answer(text, reply_markup=main_menu_keyboard())
        return

    upcoming = []
    past = []

    for item in appointments:
        if item["status"] == "cancelled":
            continue
        if is_appointment_passed(item["date"], item["time"]):
            past.append(item)
        else:
            upcoming.append(item)

    upcoming.sort(key=lambda x: (x["date"], x["time"]))
    past.sort(key=lambda x: (x["date"], x["time"]), reverse=True)

    total_items = upcoming + past
    total_pages = max((len(total_items) + PER_PAGE_UPCOMING - 1) // PER_PAGE_UPCOMING, 1)
    page = max(1, min(page, total_pages))
    page_items = total_items[(page - 1) * PER_PAGE_UPCOMING : page * PER_PAGE_UPCOMING]

    text = f"📋 Ваши записи (стр. {page}/{total_pages}):\n\n"
    keyboard_buttons = []

    for item in page_items:
        is_passed = is_appointment_passed(item["date"], item["time"])
        icon = "✔️" if is_passed else "⏰"
        text += f"{icon} {item['time']} — {item['service_name']}\n"
        text += f"📅 {format_date_for_display(item['date'])}\n"
        text += f"💬 Пожелания: {item['note'] or 'Нет'}\n\n"

        if is_passed:
            has_feedback = await BookingService.has_feedback(item["id"])
            if not has_feedback:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"🌟 Оставить отзыв: {format_date_for_display(item['date'])}",
                        callback_data=Feedback(appointment_id=item['id']).pack(),
                    )
                ])
        else:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"Перенести: {format_date_for_display(item['date'])} {item['time']}",
                    callback_data=Reschedule(appointment_id=item['id']).pack(),
                ),
                InlineKeyboardButton(text="Отменить", callback_data=CancelApt(appointment_id=item['id']).pack()),
            ])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀", callback_data=MyApts(page=page - 1).pack()))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="▶", callback_data=MyApts(page=page + 1).pack()))
    if nav:
        keyboard_buttons.append(nav)

    keyboard_buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    if edit:
        await message_obj.edit_text(text, reply_markup=markup)
    else:
        await message_obj.answer(text, reply_markup=markup)


@router.message(F.text.in_(["🌷 Мои записи", "мои записи", "Мои записи", "запись", "Запись", "Отзывы", "отзывы", "feedback", "Feedback", "Отзыв", "отзыв"]))
async def my_appointments_command(message: Message) -> None:
    await render_my_appointments(message, message.from_user.id)


@router.callback_query(BookingAction.filter(F.action == "list"))
async def booking_list_callback(callback_query: types.CallbackQuery) -> None:
    await render_my_appointments(callback_query.message, callback_query.from_user.id, edit=True)
    await callback_query.answer()

@router.callback_query(MyApts.filter())
async def my_appointments_page_callback(callback_query: types.CallbackQuery, callback_data: MyApts) -> None:
    page = callback_data.page
    await render_my_appointments(callback_query.message, callback_query.from_user.id, page=page, edit=True)
    await callback_query.answer()

@router.callback_query(Feedback.filter())
async def leave_feedback(callback_query: types.CallbackQuery, state: FSMContext, callback_data: Feedback) -> None:
    """Start feedback process with validation."""
    appointment_id = callback_data.appointment_id
    
    # Validate appointment exists and belongs to user
    async with get_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT a.id, a.status, a.appointment_date, a.appointment_time, s.duration "
                "FROM appointments a "
                "JOIN clients c ON c.id = a.client_id "
                "JOIN services s ON s.id = a.service_id "
                "WHERE a.id = ? AND c.telegram_id = ?",
                (appointment_id, callback_query.from_user.id)
            )
            row = await cursor.fetchone()
    
    if not row:
        await callback_query.answer("Запись не найдена или вам не принадлежит", show_alert=True)
        return
    
    apt_id, status, apt_date, apt_time, duration = row
    
    # Check if appointment is already completed
    apt_datetime = datetime.fromisoformat(f"{apt_date} {apt_time}").replace(tzinfo=get_tz_sync())
    apt_end_time = apt_datetime + timedelta(minutes=duration)

    if datetime.now(get_tz_sync()) < apt_end_time:
        await callback_query.answer("Запись еще не завершена", show_alert=True)
        return
    
    if status != 'planned':
        await callback_query.answer("Эта запись отменена или завершена", show_alert=True)
        return
    
    # Valid feedback request
    await state.update_data(appointment_id=appointment_id)
    await state.set_state(FeedbackStates.feedback_content)
    
    await callback_query.message.edit_text(
        f"💬 Отправьте обратную связь о вашем визите:\n\n"
        f"Вы можете отправить:\n"
        f"• Текстовый отзыв\n"
        f"• Фото\n"
        f"• Фото с описанием\n\n"
        f"Строго одно сообщение!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=CancelFeedback().pack())]
        ]),
    )
    await callback_query.answer()

@router.callback_query(CancelFeedback.filter(), FeedbackStates.feedback_content)
async def cancel_feedback(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel feedback."""
    await state.clear()
    await callback_query.message.edit_text(
        "❌ Отзыв отменен",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuAction(action="main").pack())]
        ]),
    )
    await callback_query.answer()

@router.message(FeedbackStates.feedback_content)
async def handle_feedback_content(message: Message, state: FSMContext) -> None:
    """Handle feedback content (text, photo, or photo with caption)."""
    data = await state.get_data()
    appointment_id = data.get("appointment_id")
    
    comment_text = ""
    photo_filename = None
    
    # Handle text message
    if message.text:
        comment_text = message.text
    # Handle photo with or without caption
    elif message.photo:
        comment_text = message.caption or ""
        # Save photo
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        
        date_str = datetime.now(get_tz_sync()).strftime("%d-%m-%Y")
        filename = f"feedback_{message.from_user.id}_{date_str}.jpg"
        photo_filename = filename   
        
        # Save photo to disk
        feedback_dir = Path(DATA_DIR) / "images" / "feedback"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = feedback_dir / filename
        await message.bot.download_file(file_info.file_path, str(file_path))
    else:
        await message.answer("❌ Пожалуйста, отправьте текст, фото или фото с подписью")
        return
    
    # Save feedback to database
    created_at = datetime.now(get_tz_sync()).isoformat()
    async with get_connection() as connection:
        async with connection.cursor() as cursor:
            try:
                await cursor.execute(
                    "INSERT INTO feedback (appointment_id, telegram_id, comment, photo_filename, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (appointment_id, message.from_user.id, comment_text, photo_filename, created_at),
                )
                await connection.commit()
            except Exception as e:
                import logging
                logging.error(f"Error saving feedback: {e}")
                # Fallback: try without photo_filename if column doesn't exist
                try:
                    await cursor.execute(
                        "INSERT INTO feedback (appointment_id, telegram_id, comment, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (appointment_id, message.from_user.id, comment_text, created_at),
                    )
                    await connection.commit()
                except Exception as e2:
                    logging.error(f"Error saving feedback (fallback): {e2}")
                    raise
    
    # Notify admin about new feedback
    from app.services.notification_service import NotificationService
    
    # Get client data from database (name from DB, not Telegram)
    client = await BookingService.get_client(message.from_user.id)
    client_name = ""
    if client:
        first_name = client.get("first_name", "") or ""
        last_name = client.get("last_name", "") or ""
        client_name = first_name
        if last_name:
            client_name += f" {last_name}"
    
    if not client_name:
        client_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
    
    await NotificationService.notify_admin_new_feedback(
        client_name=client_name,
        text=comment_text,
        has_photo=photo_filename is not None,
    )
    
    await state.clear()
    await message.answer(
        "✅ Спасибо за вашу обратную связь!\n\n"
        "Мы обязательно прочитаем ваш отзыв и учтем ваши пожелания 😊",
        reply_markup=main_menu_keyboard(),
    )

@router.callback_query(MenuAction.filter(F.action == "main"))
async def return_to_main(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback_query.message.delete()
    await callback_query.answer()
