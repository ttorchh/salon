from datetime import date, datetime, timedelta
from pathlib import Path
import asyncio
import os
from app.config import get_tz_sync
from aiogram import Router, types, F, Bot
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
import logging

from app.config import ADMIN_IDS, DATA_DIR
from app.keyboards.admin import admin_menu_keyboard
from app.admin_bot.management_keyboards import (
    appointment_admin_keyboard,
    admin_services_keyboard,
    services_list_keyboard,
    service_edit_keyboard,
    confirm_delete_service_keyboard,
    blocking_type_keyboard,
    blocked_slots_keyboard,
    blocked_day_keyboard,
    pricelist_keyboard,
    service_edit_cancel_keyboard,
    appointments_view_keyboard,
    clients_root_keyboard,
    client_list_keyboard,
    client_detail_keyboard,
)
from app.admin_bot.menu_keyboard import admin_schedule_menu_keyboard, AdminBlockTime, AdminUnblockTime, ScheduleOpenDay, AdminMenu as AdminMenuCB
from app.keyboards.calendar import CalendarAction, CalendarDate, TimeSelect, calendar_keyboard, time_selection_keyboard, get_calendar_with_blocked_dates
from app.services.admin_service import AdminService
from app.services.booking_service import BookingService
from app.services.catalog_service import CatalogService
from app.services.notification_service import NotificationService
from app.database import get_connection
from app.date_utils import format_date_for_display, normalize_date_to_iso

router = Router()

# Logger
logger = logging.getLogger(__name__)

# Global cache for photos to optimize sending
_ADMIN_PHOTO_CACHE = {}  # {feedback_id: file_id}

class AdminBlockingStates(StatesGroup):
    block_type = State()  # Choose: block_day or block_time
    block_date = State()
    block_time = State()
    upload_pricelist = State()  # For uploading pricelist image

class AdminRescheduleStates(StatesGroup):
    reschedule_date = State()
    reschedule_time = State()

class AdminAppointmentCancelStates(StatesGroup):
    reason = State()

class AdminNotificationStates(StatesGroup):
    set_time = State()  # Set notification time (HH:MM)

class AdminScheduleStates(StatesGroup):
    choose_mode = State()  # cycle, weekdays, free
    cycle_pattern = State()  # e.g. 5/2
    cycle_start_date = State()  # e.g. 20-04-2026
    weekdays_select = State()  # Multi-day selection
    select_interval = State()  # 15, 30, 45, 60 min
    custom_interval = State()  # Custom interval input
    set_break_start = State()  # HH:MM
    set_break_end = State()  # HH:MM

class ServiceManagementStates(StatesGroup):
    create_name = State()
    create_description = State()
    create_price = State()
    create_duration = State()
    edit_field = State()
    edit_photo = State()

class BroadcastStates(StatesGroup):
    broadcast_text = State()
    broadcast_photo = State()

class AdminFeedbackReplyStates(StatesGroup):
    """States for replying to feedback."""
    reply_text = State()

class ContactsEditStates(StatesGroup):
    """States for editing salon_sandbox contacts."""
    editing = State()

class TimezoneStates(StatesGroup):
    """States for setting timezone offset."""
    set_offset = State()

class ReloadStates(StatesGroup):
    """States for bot reload confirmation."""
    confirm_reload = State()

# ============ CallbackData Classes ============

# Menu & Navigation
class AdminMenu(CallbackData, prefix="admin_menu"):
    pass

class AdminContactsMenu(CallbackData, prefix="admin_contacts"):
    pass

class AdminServices(CallbackData, prefix="admin_services"):
    pass

class AdminScheduleMenu(CallbackData, prefix="admin_schedule_menu"):
    pass

class MenuMain(CallbackData, prefix="menu_main"):
    pass

class ManualBookNote(CallbackData, prefix="manualbook_note_none"):
    pass

# Appointments & Views
class ViewAppointments(CallbackData, prefix="view"):
    view_type: str  # today, week, upcoming

class AppointmentDetail(CallbackData, prefix="apt_detail"):
    appointment_id: int

class AppointmentNav(CallbackData, prefix="apt_nav"):
    view_type: str  # today, week, upcoming
    direction: str  # prev, next

class AppointmentBack(CallbackData, prefix="apt_back"):
    view_type: str  # today, week, upcoming
    page: int = 1

class AdminCancel(CallbackData, prefix="admin_cancel"):
    appointment_id: int

class AdminReschedule(CallbackData, prefix="admin_reschedule"):
    appointment_id: int

class NoShow(CallbackData, prefix="no_show"):
    appointment_id: int

# Blocking & Scheduling
class BlockDay(CallbackData, prefix="block_day"):
    pass

class BlockTime(CallbackData, prefix="block_time"):
    pass

class BlockView(CallbackData, prefix="block_view"):
    pass

class BlockingMenu(CallbackData, prefix="blocking_menu"):
    pass

class UnblockDay(CallbackData, prefix="unblock_day"):
    date: str

class Unblock(CallbackData, prefix="unblock"):
    date: str
    time: str

# Services
class ServiceCreate(CallbackData, prefix="service_create"):
    pass

class ServiceList(CallbackData, prefix="service_list"):
    pass

class ServiceEdit(CallbackData, prefix="service_edit"):
    service_id: int

class ServiceEditField(CallbackData, prefix="service_edit_field"):
    service_id: int
    field: str

class ServiceDelete(CallbackData, prefix="service_delete"):
    service_id: int

class ServiceConfirmDelete(CallbackData, prefix="service_confirm_delete"):
    service_id: int

# Clients
class ClientsMenu(CallbackData, prefix="clients_menu"):
    pass

class ClientsList(CallbackData, prefix="clients_list"):
    page: int

class ClientsBans(CallbackData, prefix="clients_bans"):
    page: int

class ClientsView(CallbackData, prefix="clients_view"):
    telegram_id: int
    page: int

class ClientsBanView(CallbackData, prefix="clients_banview"):
    telegram_id: int
    page: int

class ClientsHistory(CallbackData, prefix="clients_history"):
    telegram_id: int
    source: str
    page: int

class ClientsBan(CallbackData, prefix="clients_ban"):
    telegram_id: int
    source: str
    page: int

class ClientsUnban(CallbackData, prefix="clients_unban"):
    telegram_id: int
    source: str
    page: int

class ClientsMessage(CallbackData, prefix="clients_message"):
    telegram_id: int
    source: str
    page: int

class ClientsBook(CallbackData, prefix="clients_book"):
    telegram_id: int
    source: str
    page: int

class ClientsCancel(CallbackData, prefix="clients_cancel"):
    telegram_id: int
    source: str
    page: int

# Calendar & Time (from manual booking)
class ManualBookService(CallbackData, prefix="manualbook_service"):
    service_id: int

# Setup Wizard
class SetupScheduleType(CallbackData, prefix="setup_schedule_type"):
    schedule_type: str

class ScheduleSettingsType(CallbackData, prefix="schedule_settings_type"):
    schedule_type: str

class SetupInterval(CallbackData, prefix="setup_interval"):
    interval: str

class ScheduleSettingsInterval(CallbackData, prefix="schedule_settings_interval"):
    interval: str

class ScheduleCyclePattern(CallbackData, prefix="cycle_pattern"):
    pattern: str  # 5/2, 2/2, 4/3, 3/3, custom

class ScheduleSettingsCyclePattern(CallbackData, prefix="schedule_settings_cycle_pattern"):
    pattern: str  # 5/2, 2/2, 4/3, 3/3, custom

class SetupWeekday(CallbackData, prefix="setup_weekday"):
    weekday: int

class ScheduleSettingsWeekday(CallbackData, prefix="schedule_settings_weekday"):
    weekday: int

class SetupBackToInterval(CallbackData, prefix="setup_back_to_interval"):
    pass

class SetupSkipScheduleType(CallbackData, prefix="setup_skip_schedule_type"):
    pass

class ScheduleSettingsWeekdaysConfirm(CallbackData, prefix="schedule_settings_weekdays_confirm"):
    pass

class SetupSkipBreaks(CallbackData, prefix="setup_skip_breaks"):
    pass

class SetupSkipContacts(CallbackData, prefix="setup_skip_contacts"):
    pass

class SetupSkipHours(CallbackData, prefix="setup_skip_hours"):
    pass

class SetupSkipInterval(CallbackData, prefix="setup_skip_interval"):
    pass

class SetupSkipNotification(CallbackData, prefix="setup_skip_notification"):
    pass

class SetupSkipTimezone(CallbackData, prefix="setup_skip_timezone"):
    pass

class SetupWeekdaysConfirm(CallbackData, prefix="setup_weekdays_confirm"):
    pass

# Feedbacks
class ViewFeedback(CallbackData, prefix="view_feedback"):
    feedback_id: int

class FeedbacksPage(CallbackData, prefix="feedbacks_page"):
    page: int

class ReplyFeedback(CallbackData, prefix="reply_feedback"):
    telegram_id: int

class AdminCancelReasonSkip(CallbackData, prefix="admin_cancel_reason_skip"):
    appointment_id: int

class BackToFeedbacks(CallbackData, prefix="back_to_feedbacks"):
    pass

class CancelReply(CallbackData, prefix="cancel_reply"):
    pass

# Pricelist & Broadcast & Notifications
class PricelistUpload(CallbackData, prefix="pricelist_upload"):
    pass

class PricelistCancel(CallbackData, prefix="pricelist_cancel"):
    pass

class BroadcastCancel(CallbackData, prefix="broadcast_cancel"):
    pass

class NotificationCancel(CallbackData, prefix="notification_cancel"):
    pass

# Timezone & Reload & Contacts
class TimezoneCancel(CallbackData, prefix="timezone_cancel"):
    pass

class ReloadConfirm(CallbackData, prefix="reload_confirm"):
    pass

class ReloadCancel(CallbackData, prefix="reload_cancel"):
    pass

class ContactEditAll(CallbackData, prefix="contact_edit_all"):
    pass


class AdminClientStates(StatesGroup):
    ban_reason = State()
    message_text = State()


class AdminClientsViewStates(StatesGroup):
    """States for clients/bans list navigation and viewing."""
    viewing_list = State()  # In clients/bans list: stores view_type (clients/bans), current_page
    viewing_detail = State()  # In client detail card: stores telegram_id, source, page


class AdminAppointmentsViewStates(StatesGroup):
    """States for appointments viewing with pagination."""
    viewing_appointments = State()  # Stores view_type (today/week/upcoming), current_page


class AdminManualBookingStates(StatesGroup):
    select_service = State()
    select_date = State()
    select_time = State()
    note = State()

class SetupWizardStates(StatesGroup):
    """States for admin initial setup wizard."""
    step_timezone          = State()  # Input timezone offset
    step_schedule_type     = State()  # Choose schedule type: цикличный/weekdays/свободный
    step_schedule_cycle_pattern = State()  # Input cycle pattern N/M
    step_schedule_cycle_date = State()  # Input cycle start date
    step_schedule_weekdays = State()  # Select weekdays for work
    step_schedule_hours    = State()  # Input work hours HH:MM-HH:MM
    step_schedule_breaks   = State()  # Input break times HH:MM-HH:MM
    step_schedule_interval = State()  # Select interval size: 15/30/45/60
    step_custom_interval   = State()  # Custom interval input
    step_notification_time = State()  # Input notification time HH:MM
    step_contacts          = State()  # Input salon_sandbox contacts

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_sandbox_restricted(feature_name: str = "Эта функция") -> str:
    """Return error message if in sandbox mode. Used for restricted features."""
    from app.config import SANDBOX_MODE
    if SANDBOX_MODE:
        return (
            f"🔒 {feature_name} недоступна в режиме сандбокса.\n\n"
            f"⚠️ Это ограничение введено для безопасности тестирования."
        )
    return None


def format_client_name(item: dict) -> str:
    """Format a readable client name."""
    first_name = item.get("first_name") or ""
    last_name = item.get("last_name") or ""
    full_name = f"{first_name} {last_name}".strip()
    return full_name or "Без имени"


def admin_main_menu_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data=AdminMenu().pack())]
        ]
    )


async def render_clients_page(message_obj, page: int = 1) -> None:
    """Render paginated clients list."""
    page_size = 8
    items, total = await AdminService.get_clients_page(page=page, page_size=page_size)
    total_pages = max((total + page_size - 1) // page_size, 1)
    current_page = min(max(page, 1), total_pages)
    if current_page != page:
        items, total = await AdminService.get_clients_page(page=current_page, page_size=page_size)

    if not items:
        text = "👥 Клиентов пока нет."
    else:
        text = f"👥 Клиенты\n\nСтраница {current_page}/{total_pages}\nВыберите клиента:"

    await message_obj.edit_text(
        text,
        reply_markup=client_list_keyboard(
            items,
            current_page,
            has_prev=current_page > 1,
            has_next=current_page < total_pages,
            banned=False,
        ),
    )


async def render_appointments_page(message_obj, view_type: str, page: int = 1) -> None:
    """Render paginated appointments list for the given view type."""
    now = datetime.now(get_tz_sync())
    
    if view_type == "today":
        today = now.date().isoformat()
        appointments = await AdminService.list_appointments_for_day(today)
    elif view_type == "week":
        start = now.date().isoformat()
        appointments = await AdminService.list_appointments_for_week(start)
    elif view_type == "upcoming":
        today = now.date().isoformat()
        appointments = await AdminService.list_upcoming_appointments(today)
    else:
        # Default to week
        start = now.date().isoformat()
        appointments = await AdminService.list_appointments_for_week(start)
        view_type = "week"

    total_pages = (len(appointments) + PER_PAGE - 1) // PER_PAGE
    page = max(1, min(page, total_pages))
    page_items = appointments[(page - 1) * PER_PAGE : page * PER_PAGE]

    by_date: dict[str, list] = {}
    for item in page_items:
        by_date.setdefault(item["date"], []).append(item)

    if not appointments:
        if view_type == "week":
            text = "📅 Записей на неделю не найдено."
        else:
            text = "📅 Предстоящих записей не найдено."

        await message_obj.edit_text(
            text,
            reply_markup=appointments_view_keyboard(),
        )
        return

    if view_type == "today":
        text = f"📅 Записи на сегодня (стр. {page}/{total_pages}):\n\n"
    elif view_type == "week":
        text = f"📅 Записи на неделю (стр. {page}/{total_pages}):\n\n"
    else:
        text = f"📅 Предстоящие записи (стр. {page}/{total_pages}):\n\n"
    
    buttons = []

    for date_str in sorted(by_date.keys()):
        text += f"📆 {date_str}\n"
        for item in by_date[date_str]:
            client_info = item.get("client_name", "Unknown")
            if item.get("phone"):
                client_info += f" ({item['phone']})"

            status = item.get("status", "planned")
            if status == "planned" and is_appointment_passed(item["date"], item["time"]):
                status = "is_passed"
            emoji = STATUS_EMOJI.get(status, "📅")

            text += f"  {emoji} {item['time']} — {item['service_name']}\n  👤 {client_info}\n"

            apt_datetime = datetime.strptime(
                f"{date_str} {item['time']}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=get_tz_sync())

            row = [
                InlineKeyboardButton(
                    text=f"{emoji} {date_str} {item['time']}",
                    callback_data=AppointmentDetail(appointment_id=item['id']).pack(),
                )
            ]

            if status == "planned" and now < apt_datetime:
                row.append(
                    InlineKeyboardButton(
                        text="📅 Перенести",
                        callback_data=AdminReschedule(appointment_id=item['id']).pack(),
                    )
                )

            buttons.append(row)

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀", callback_data=AppointmentNav(view_type=view_type, direction="prev").pack()))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="▶", callback_data=AppointmentNav(view_type=view_type, direction="next").pack()))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data=AdminMenu().pack())])

    await message_obj.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


async def render_banlist_page(message_obj, page: int = 1) -> None:
    """Render paginated ban list."""
    page_size = 8
    items, total = await AdminService.get_banned_users_page(page=page, page_size=page_size)
    total_pages = max((total + page_size - 1) // page_size, 1)
    current_page = min(max(page, 1), total_pages)
    if current_page != page:
        items, total = await AdminService.get_banned_users_page(page=current_page, page_size=page_size)

    if not items:
        text = "⛔ Банлист пуст."
    else:
        text = f"⛔ Банлист\n\nСтраница {current_page}/{total_pages}\nВыберите пользователя:"

    await message_obj.edit_text(
        text,
        reply_markup=client_list_keyboard(
            items,
            current_page,
            has_prev=current_page > 1,
            has_next=current_page < total_pages,
            banned=True,
        ),
    )


async def render_client_card(message_obj, telegram_id: int, source: str, page: int) -> None:
    """Render a client card with history/ban/message actions."""
    client = await AdminService.get_client_by_telegram_id(telegram_id)
    ban_info = await AdminService.get_ban_info(telegram_id)

    if not client and not ban_info:
        await message_obj.edit_text(
            f"❌ Пользователь {telegram_id} не найден.",
            reply_markup=clients_root_keyboard(),
        )
        return

    merged = client or {
        "telegram_id": telegram_id,
        "first_name": None,
        "last_name": None,
        "phone": None,
        "total_appointments": 0,
    }
    client_name = format_client_name(merged)
    lines = [
        f"👤 Клиент: {client_name}",
        f"ID: {telegram_id}",
        f"Телефон: {merged.get('phone') or 'не указан'}",
        f"Записей: {merged.get('total_appointments', 0)}",
    ]
    if ban_info:
        lines.extend([
            "",
            "⛔ Пользователь заблокирован",
            f"Причина: {ban_info.get('reason') or 'не указана'}",
            f"Когда: {ban_info.get('banned_at', '')[:16].replace('T', ' ')}",
        ])

    await message_obj.edit_text(
        "\n".join(lines),
        reply_markup=client_detail_keyboard(
            telegram_id,
            source,
            page,
            is_banned=ban_info is not None,
        ),
    )


async def send_user_manual_booking_notification(telegram_id: int, appointment_id: int, service_name: str, appointment_date: str, appointment_time: str, client_name: str, phone: str, note: str) -> None:
    """Send manual booking notification to user in background (doesn't block the handler)."""
    from app.config import BOT_TOKEN
    from app.bot import create_bot
    
    user_bot = None
    try:
        logger.info(f"[BG] Creating user bot to notify {telegram_id} about manual booking {appointment_id}")
        user_bot = create_bot(BOT_TOKEN)
        await NotificationService.notify_appointment_created(
            bot=user_bot,
            telegram_id=telegram_id,
            service_name=service_name,
            date=format_date_for_display(appointment_date),
            time=appointment_time,
            client_name=client_name,
            phone=phone or "",
            note=note or "",
        )
        logger.info(f"[BG] User notification sent for manual booking {appointment_id} to {telegram_id}")
    except Exception as e:
        logger.error(f"[BG] Failed to notify user about manual booking: {e}", exc_info=True)
    finally:
        if user_bot:
            await user_bot.session.close()

async def finalize_manual_booking(message_obj, state: FSMContext, from_user, *, note: str) -> None:
    """Create a manual appointment for a selected client."""
    data = await state.get_data()
    telegram_id = int(data["manual_telegram_id"])
    service_id = int(data["manual_service_id"])
    appointment_date = data["manual_date"]
    appointment_time = data["manual_time"]

    client = await BookingService.get_client(telegram_id)
    service = await CatalogService.get_service(service_id)
    if not client or not service:
        await message_obj.answer("❌ Не удалось создать запись: клиент или услуга не найдены.")
        await state.clear()
        return

    appointment_id = await BookingService.create_appointment(
        client_id=client["id"],
        service_id=service_id,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        note=note or None,
    )

    # Notify admin about new manual booking
    try:
        await NotificationService.notify_admin_appointment_created(
            appointment_id=appointment_id,
            first_name=client.get("first_name") or "",
            last_name=client.get("last_name") or "",
            service_name=service["name"],
            date=format_date_for_display(appointment_date),
            time=appointment_time,
            phone=client.get("phone") or "",
            note=note or "",
        )
        logger.info(f"Admin notification sent for manual booking {appointment_id}")
    except Exception as e:
        logger.error(f"Failed to notify admin about manual booking: {e}")

    # Send user notification in background (don't block the handler)
    asyncio.create_task(
        send_user_manual_booking_notification(
            telegram_id=telegram_id,
            appointment_id=appointment_id,
            service_name=service["name"],
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            client_name=format_client_name(client),
            phone=client.get("phone") or "",
            note=note or "",
        )
    )

    await state.clear()
    
    # Show confirmation and list of appointments for this day
    confirmation_msg = (
        "✅ Ручная запись создана\n\n"
        f"Клиент: {format_client_name(client)}\n"
        f"Услуга: {service['name']}\n"
        f"Дата: {format_date_for_display(appointment_date)}\n"
        f"Время: {appointment_time}"
    )
    
    await message_obj.answer(confirmation_msg)
    

def is_appointment_passed(appointment_date: str, appointment_time: str) -> bool:
    """Check if appointment date/time has passed."""
    try:
        apt_datetime = datetime.fromisoformat(f"{appointment_date} {appointment_time}").replace(tzinfo=get_tz_sync())
        return apt_datetime < datetime.now(get_tz_sync())
    except:
        return False

STATUS_EMOJI = {
        "is_passed":  "✔️",
        "planned":    "📅",
        "cancelled":  "✖️",
        "no-show":    "👻",
    }

PER_PAGE = 20

@router.message(Command("start"))
async def admin_start_command(message: types.Message, state: FSMContext) -> None:
    """Admin bot start command."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-панели.")
        return
    
    await state.clear()

    start_text = start_text = """
👨‍💼 Добро пожаловать в админ-панель!

    Для начала работы настройте бота командой /setup, вас проведут по необходимым настройкам.
    """

    await message.answer(
        start_text,
        reply_markup=admin_menu_keyboard()
    )

@router.message(F.text == "📋 Записи")
async def admin_appointments_menu(message: types.Message) -> None:
    """Show menu to choose how to view appointments."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-меню")
        return
    

    await message.answer(
        "📋 Выберите как просмотреть записи:",
        reply_markup=appointments_view_keyboard(),
    )

@router.callback_query(ViewAppointments.filter(F.view_type == "today"))
async def admin_today_callback(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Show appointments for today."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    # Set FSM state to track that we're viewing appointments
    await state.set_state(AdminAppointmentsViewStates.viewing_appointments)
    await state.update_data(view_type="today", current_page=1)
    
    today = datetime.now(get_tz_sync()).date().isoformat()
    appointments = await AdminService.list_appointments_for_day(today)
    
    if not appointments:
        await callback_query.message.edit_text(
            f"📅 Записей на сегодня ({today}) не найдено.",
            reply_markup=appointments_view_keyboard(),
        )
        await callback_query.answer()
        return
    

    now = datetime.now(get_tz_sync())
    
    if len(appointments) == 1:
        apt = appointments[0]
        client_info = apt.get("client_name", "Unknown")
        if apt.get("phone"):
            client_info += f" ({apt['phone']})"
        text = (
            f"📅 Запись на сегодня:\n\n"
            f"⏰ {apt['time']} — {apt['service_name']}\n"
            f"👤 Клиент: {client_info}\n"
            f"💬 Пожелания: {apt['note'] or 'нет'}\n"
        )
        
        apt_datetime = datetime.strptime(f"{today} {apt['time']}", "%Y-%m-%d %H:%M")
        apt_datetime = apt_datetime.replace(tzinfo=get_tz_sync())
        
        if now > apt_datetime:
            buttons = [[InlineKeyboardButton(text="👻 Клиент не пришел", callback_data=NoShow(appointment_id=apt['id']).pack())]]
            buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data=AppointmentBack(view_type="today", page=1).pack())])
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            )
        else:
            await callback_query.message.edit_text(
                text,
                reply_markup=appointment_admin_keyboard(apt['id'], view_type="today", page=1),
            )
    else:
        text = f"📅 Записи на сегодня ({today}):\n\n"
        buttons = []
        for item in appointments:
            client_info = item.get("client_name", "Unknown")
            status = item.get("status", "planned")
            if status == "planned" and is_appointment_passed(item["date"], item["time"]):
                status = "is_passed"
            emoji = STATUS_EMOJI.get(status, "📅")
            if item.get("phone"):
                client_info += f" ({item['phone']})"
            text += f"{emoji} {item['time']} — {item['service_name']}\n👤 {client_info}\n\n"
        

            apt_datetime = datetime.strptime(f"{today} {item['time']}", "%Y-%m-%d %H:%M")
            apt_datetime = apt_datetime.replace(tzinfo=get_tz_sync())
            
            if now > apt_datetime:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{emoji} {item['time']}",
                        callback_data=AppointmentDetail(appointment_id=item['id']).pack()
                    ),
                    InlineKeyboardButton(
                        text="👻 Неявка",
                        callback_data=NoShow(appointment_id=item['id']).pack()
                    )
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{emoji} {item['time']}",
                        callback_data=AppointmentDetail(appointment_id=item['id']).pack()
                    ),
                    InlineKeyboardButton(
                        text="📅 Перенести",
                        callback_data=AdminReschedule(appointment_id=item['id']).pack()
                    )
                ])
        buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data=AdminMenu().pack())])
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    
    await callback_query.answer()

@router.callback_query(ViewAppointments.filter(F.view_type == "week"))
async def admin_week_callback(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Show appointments for the week with FSM state tracking."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return

    parts = callback_query.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    
    await state.set_state(AdminAppointmentsViewStates.viewing_appointments)
    await state.update_data(view_type="week", current_page=page)
    await render_appointments_page(callback_query.message, "week", page)
    await callback_query.answer()

@router.callback_query(ViewAppointments.filter(F.view_type == "upcoming"))
async def admin_upcoming_callback(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Show all upcoming appointments with FSM state tracking."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return

    parts = callback_query.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    
    await state.set_state(AdminAppointmentsViewStates.viewing_appointments)
    await state.update_data(view_type="upcoming", current_page=page)
    await render_appointments_page(callback_query.message, "upcoming", page)
    await callback_query.answer()

@router.callback_query(AppointmentDetail.filter())
async def show_appointment_detail(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Show appointment details with management buttons."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    appointment_id = int(callback_query.data.split(":", 1)[1])
    details = await AdminService.get_appointment_details(appointment_id)
    
    if not details:
        await callback_query.answer("Запись не найдена", show_alert=True)
        return
    
    text = (
        f"📋 Детали записи:\n\n"
        f"Услуга: {details['service_name']}\n"
        f"Дата: {details['date']}\n"
        f"Время: {details['time']}\n"
        f"Длительность: {details['duration']} мин\n"
        f"Цена: {details['price']}₽\n\n"
        f"👤 Клиент: {details['first_name']} {details['last_name']}\n"
        f"💬 Пожелания: {details['note'] or 'нет'}"
    )
    
    # Get current view type and page from state to pass to keyboard
    data = await state.get_data()
    view_type = data.get("view_type", "today")
    current_page = data.get("current_page", 1)
    
    await callback_query.message.edit_text(
        text,
        reply_markup=appointment_admin_keyboard(appointment_id, view_type=view_type, page=current_page),
    )
    await callback_query.answer()

@router.callback_query(AdminScheduleMenu.filter())
async def admin_schedule_menu_callback(callback_query: types.CallbackQuery) -> None:
    """Show schedule management menu."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback_query.message.edit_text(
        "📅 Выберите действие:",
        reply_markup=admin_schedule_menu_keyboard(),
    )
    await callback_query.answer()

@router.callback_query(AdminBlockTime.filter())
async def admin_block_time_callback(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Handle block time from callback."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback_query.message.edit_text(
        "📆 Управление графиком:",
        reply_markup=blocking_type_keyboard(),
    )
    await callback_query.answer()

@router.callback_query(AdminUnblockTime.filter())
async def admin_unblock_time_callback(callback_query: types.CallbackQuery) -> None:
    """Handle unblock time from callback."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    today = datetime.now(get_tz_sync()).date().isoformat()
    blocked = await AdminService.get_blocked_slots_for_week(today)
    
    # Filter out past dates
    now = datetime.now(get_tz_sync())
    blocked = [
        s for s in blocked 
        if s['date'] > today or (s['date'] == today and s['time'] > now.strftime("%H:%M"))
    ]
    
    if not blocked:
        await callback_query.answer("Нет заблокированных времени", show_alert=True)
        return
    
    text = "🔓 Заблокированные времена:\n\n"
    buttons = []
    for item in blocked:
        text += f"📅 {item['date']} {item['time']}\n"
        buttons.append([InlineKeyboardButton(
            text=f"{item['date']} {item['time']}", 
            callback_data=f"unblock:{item['date']}:{item['time']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="admin_schedule_menu")])
    
    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback_query.answer()

@router.callback_query(AdminServices.filter())
async def admin_services_callback(callback_query: types.CallbackQuery) -> None:
    """Show services management from callback."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return

    await callback_query.answer()

    try:
        from pathlib import Path
        from app.config import DATA_DIR

        pricelist_path = Path(DATA_DIR) / "images" / "pricelist.jpg"

        if pricelist_path.exists():
            await callback_query.message.delete()  # удаляем старое перед фото
            await callback_query.message.answer_photo(
                photo=FSInputFile(str(pricelist_path)),
                caption="✨ Наш прайс-лист",
                reply_markup=pricelist_keyboard(),
            )
        else:
            await callback_query.message.edit_text(
                "⚙️ Управление услугами:",
                reply_markup=service_edit_keyboard(),
            )
    except Exception as e:
        logger.error(f"Error showing services: {e}")
        await callback_query.answer("Ошибка при загрузке услуг", show_alert=True)

@router.message(F.text == "📆 График")
async def admin_block_time_text(message: types.Message, state: FSMContext) -> None:
    """Legacy text button handler."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-меню")
        return
    
    await message.answer(
        "📆 Управление графиком:",
        reply_markup=blocking_type_keyboard(),
    )


@router.callback_query(BlockDay.filter())
async def block_entire_day(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Start blocking entire day."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminBlockingStates.block_date)
    await state.update_data(block_type="day")
    today = datetime.now(get_tz_sync()).date()
    calendar_kb = await get_calendar_with_blocked_dates(today.year, today.month)
    calendar_kb.inline_keyboard.append([
        InlineKeyboardButton(text="◀ Назад", callback_data=BlockingMenu().pack())
    ])
    await callback_query.message.edit_text(
        "📅 Выберите дату для блокировки всего дня:",
        reply_markup=calendar_kb,
    )
    await callback_query.answer()


@router.callback_query(BlockTime.filter())
async def block_time_slot(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Start blocking specific time."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminBlockingStates.block_date)
    await state.update_data(block_type="time")
    today = datetime.now(get_tz_sync()).date()
    calendar_kb = await get_calendar_with_blocked_dates(today.year, today.month)
    calendar_kb.inline_keyboard.append([
        InlineKeyboardButton(text="◀ Назад", callback_data=BlockingMenu().pack())
    ])
    await callback_query.message.edit_text(
        "📅 Выберите дату для блокировки времени:",
        reply_markup=calendar_kb,
    )
    await callback_query.answer()


@router.callback_query(BlockingMenu.filter())
async def back_to_blocking_menu(callback_query: types.CallbackQuery) -> None:
    """Return to blocking menu."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback_query.message.edit_text(
        "📆 Управление графиком:",
        reply_markup=blocking_type_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(BlockView.filter())
async def view_blocked_slots(callback_query: types.CallbackQuery) -> None:
    """View all blocked slots for today and upcoming."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    today = datetime.now(get_tz_sync()).date().isoformat()
    blocked = await AdminService.get_blocked_slots_for_week(today)
    
    # Filter out past dates
    now = datetime.now(get_tz_sync())
    blocked = [
        s for s in blocked 
        if s['date'] > today or (s['date'] == today and s['time'] > now.strftime("%H:%M"))
    ]
    
    if not blocked:
        await callback_query.message.edit_text(
            "✓ Нет активных блокировок",
            reply_markup=blocking_type_keyboard(),
        )
    else:
        # Group by date and check if any are full day blocks
        by_date = {}
        for slot in blocked:
            if slot['date'] not in by_date:
                by_date[slot['date']] = []
            by_date[slot['date']].append(slot)
        
        text = "🔒 Заблокированные слоты:\n\n"
        
        # First pass: identify full day blocks
        full_days = set()
        for date_str, slots in by_date.items():
            for slot in slots:
                if slot['reason'] == "День заблокирован":
                    full_days.add(date_str)
                    break
        
        # Display blocked items - full days first, then individual times
        for date_str in sorted(by_date.keys()):
            if date_str in full_days:
                text += f"📅 {date_str} - День полностью заблокирован\n"
            else:
                # Show only individual time slots for this date
                for slot in by_date[date_str]:
                    text += f"📅 {slot['date']} ⏰ {slot['time']}\n"
        
        # Build blocked list without full-day entries for the keyboard
        blocked_for_keyboard = [s for s in blocked if s['reason'] != "День заблокирован"]
        
        await callback_query.message.edit_text(
            text,
            reply_markup=blocked_slots_keyboard(blocked_for_keyboard, list(full_days)),
        )
    
    await callback_query.answer()


@router.callback_query(CalendarAction.filter(), AdminBlockingStates.block_date)
async def admin_calendar_month_change(callback_query: types.CallbackQuery, state: FSMContext, callback_data: CalendarAction) -> None:
    """Handle calendar month navigation for blocking dates."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    year = callback_data.year
    month = callback_data.month
    
    # Get calendar with blocked dates for current schedule
    calendar_kb = await get_calendar_with_blocked_dates(year, month)
    calendar_kb.inline_keyboard.append([
        InlineKeyboardButton(text="◀ Назад", callback_data=BlockingMenu().pack())
    ])
    
    data = await state.get_data()
    block_type = data.get("block_type", "time")
    title = "📅 Выберите дату для блокировки всего дня:" if block_type == "day" else "📅 Выберите дату для блокировки времени:"
    
    await callback_query.message.edit_text(
        title,
        reply_markup=calendar_kb,
    )
    await callback_query.answer()

@router.callback_query(CalendarDate.filter(), AdminBlockingStates.block_date)
async def admin_select_block_date(callback_query: types.CallbackQuery, state: FSMContext, callback_data: CalendarDate) -> None:
    block_date = callback_data.date
    data = await state.get_data()
    block_type = data.get("block_type", "time")
    
    if block_type == "day":
        # Block entire day
        await AdminService.block_entire_day(block_date)
        await state.clear()
        await callback_query.message.edit_text(
            f"✅ День {block_date} полностью заблокирован",
            reply_markup=blocked_day_keyboard(),
        )
    else:
        # Show time selection with schedule settings
        await state.update_data(block_date=block_date)
        await state.set_state(AdminBlockingStates.block_time)
        
        # Get available time slots respecting work day settings
        all_times = await AdminService.get_day_slots_for_blocking(block_date)
        
        if not all_times:
            await callback_query.answer("Этот день выходной", show_alert=True)
            return
        
        await callback_query.message.edit_text(
            f"⏰ Выберите время для блокировки на {block_date}:",
            reply_markup=time_selection_keyboard(all_times),
        )
    
    await callback_query.answer()

@router.callback_query(TimeSelect.filter(), AdminBlockingStates.block_time)
async def admin_select_block_time(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    block_time = callback_query.data.split(":", 1)[1].replace('.', ':')
    data = await state.get_data()
    
    await AdminService.block_time_slot(data["block_date"], block_time)
    await state.clear()
    
    await callback_query.message.edit_text(
        f"✅ Время {block_time} на {data['block_date']} заблокировано",
        reply_markup=blocking_type_keyboard(),
    )
    await callback_query.answer()

@router.callback_query(AdminCancel.filter())
async def admin_cancel_appointment(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Start cancelling an appointment - request reason from admin."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    appointment_id = int(callback_query.data.split(":", 1)[1])
    details = await AdminService.get_appointment_details(appointment_id)
    
    if not details:
        await callback_query.answer("Запись не найдена", show_alert=True)
        return
    
    await state.set_state(AdminBlockingStates.block_type)  # Reuse state temporarily
    await state.update_data(appt_id=appointment_id)
    
    text = (
        f"Отмена записи:\n"
        f"Услуга: {details['service_name']}\n"
        f"Дата: {details['date']}\n"
        f"Время: {details['time']}\n\n"
        f"Введите причину отмены (или отправьте '-' для отмены без комментария):"
    )
    
    await callback_query.message.edit_text(text)
    await callback_query.answer()

@router.message(AdminBlockingStates.block_type, F.text)
async def handle_cancel_reason(message: types.Message, state: FSMContext) -> None:
    """Handle cancellation reason from admin."""
    data = await state.get_data()
    appt_id = data.get("appt_id")
    
    if not appt_id:
        return
    
    reason = message.text if message.text != "-" else "Отменено администратором"
    
    details = await AdminService.get_appointment_details(appt_id)
    
    await AdminService.cancel_appointment(appt_id, reason)
    await NotificationService.notify_appointment_cancelled(message.bot, appt_id, reason)
    
    await state.clear()
    await message.answer(
        f"✅ Запись отменена.\n"
        f"Клиент уведомлен: {reason}",
        reply_markup=admin_menu_keyboard(),
    )

# ==================== APPOINTMENT MANAGEMENT ====================

@router.callback_query(AdminCancel.filter())
async def admin_cancel_appointment(callback_query: types.CallbackQuery, bot: Bot) -> None:
    """Cancel appointment by admin."""
    if not is_admin(callback_query.from_user.id):
        try:
            await callback_query.answer("У вас нет доступа", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")
        return
    
    appointment_id = int(callback_query.data.split(":", 1)[1])
    details = await AdminService.get_appointment_details(appointment_id)
    
    if not details:
        try:
            await callback_query.answer("Запись не найдена", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")
        return
    
    # Answer callback immediately to avoid timeout
    try:
        await callback_query.answer("✅ Запись отменена. Уведомление отправлено клиенту")
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}")
    
    # Send notification BEFORE deleting from database
    try:
        await NotificationService.notify_appointment_cancelled(bot, appointment_id, "Отменено администратором")
    except Exception as e:
        logger.error(f"Failed to send cancellation notification: {e}")
    
    # Send admin notification
    try:
        await NotificationService.notify_admin_appointment_cancelled(
            first_name=details.get('client_first_name', ''),
            last_name=details.get('client_last_name', ''),
            service_name=details['service_name'],
            date=details['appointment_date'],
            time=details['appointment_time'],
            reason="Отменено администратором",
        )
    except Exception as e:
        logger.error(f"Failed to send admin cancellation notification: {e}")
    
    # THEN delete from database
    await AdminService.cancel_appointment(appointment_id, "Отменено администратором")
    
    # Edit message with result
    try:
        await callback_query.message.edit_text(
            f"❌ Запись отменена:\n{details['service_name']}\n{details['date']} в {details['time']}"
        )
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
        await callback_query.message.answer("✅ Запись успешно отменена!")

@router.callback_query(NoShow.filter())
async def mark_appointment_no_show(callback_query: types.CallbackQuery, bot: Bot) -> None:
    """Mark appointment as no-show (client didn't come)."""
    if not is_admin(callback_query.from_user.id):
        try:
            await callback_query.answer("У вас нет доступа", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")
        return
    
    appointment_id = int(callback_query.data.split(":", 1)[1])
    details = await AdminService.get_appointment_details(appointment_id)
    
    if not details:
        try:
            await callback_query.answer("Запись не найдена", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")
        return
    
    # Answer callback immediately to avoid timeout
    try:
        await callback_query.answer("✅ Отмечено: клиент не пришел")
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}")
    
    # Mark as no-show
    await AdminService.mark_appointment_no_show(appointment_id)
    
    # Edit message with result
    try:
        await callback_query.message.edit_text(
            f"👻 Неявка:\n{details['service_name']}\n{details['date']} в {details['time']}"
        )
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
        await callback_query.message.answer("✅ Запись отмечена как неявка!")

@router.callback_query(AdminReschedule.filter())
async def admin_reschedule_appointment(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Start rescheduling an appointment."""
    if not is_admin(callback_query.from_user.id):
        try:
            await callback_query.answer("У вас нет доступа", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")
        return
    
    appointment_id = int(callback_query.data.split(":", 1)[1])
    details = await AdminService.get_appointment_details(appointment_id)
    
    if not details:
        try:
            await callback_query.answer("Запись не найдена", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")
        return
    
    await state.update_data(appointment_id=appointment_id, service_id=details.get('service_id', 1))
    await state.set_state(AdminRescheduleStates.reschedule_date)
    
    today = datetime.now(get_tz_sync()).date()
    try:
        await callback_query.message.edit_text(
            f"📅 Перенести запись:\n{details['service_name']}\nСтарая дата: {details['date']} в {details['time']}\n\nВыберите новую дату:",
            reply_markup=await get_calendar_with_blocked_dates(today.year, today.month),
        )
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
        await callback_query.message.answer(
            f"📅 Перенести запись:\n{details['service_name']}\nСтарая дата: {details['date']} в {details['time']}\n\nВыберите новую дату:",
            reply_markup=await get_calendar_with_blocked_dates(today.year, today.month),
        )
    
    try:
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}")

@router.callback_query(CalendarAction.filter(), AdminRescheduleStates.reschedule_date)
async def admin_reschedule_calendar_month_change(callback_query: types.CallbackQuery) -> None:
    """Navigate calendar while selecting reschedule date."""
    year_month = callback_query.data.split(":", 1)[1]
    year, month = map(int, year_month.split("-"))
    await callback_query.message.edit_reply_markup(
        reply_markup=await get_calendar_with_blocked_dates(year, month),
    )
    await callback_query.answer()


@router.callback_query(CalendarDate.filter(), AdminRescheduleStates.reschedule_date)
async def admin_select_reschedule_date(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Select new date for appointment."""
    new_date = callback_query.data.split(":", 1)[1]
    data = await state.get_data()
    service_id = data.get("service_id", 1)
    appointment_id = data.get("appointment_id")
    
    logger.info(f"Rescheduling: new_date={new_date}, service_id={service_id}, appointment_id={appointment_id}")
    
    await state.update_data(reschedule_date=new_date)
    await state.set_state(AdminRescheduleStates.reschedule_time)
    
    available_times = await BookingService.get_available_times(new_date, service_id, exclude_appointment_id=appointment_id)
    logger.info(f"Available times for {new_date}: {available_times}")
    
    if not available_times:
        try:
            await callback_query.answer("На эту дату нет доступных времён. Выберите другую дату.", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to answer callback query: {e}")
        await state.set_state(AdminRescheduleStates.reschedule_date)
        # Use answer() instead of edit_text() to avoid "message not modified" error
        today = datetime.now(get_tz_sync()).date()
        try:
            await callback_query.message.answer(
                "📅 Выберите новую дату:",
                reply_markup=await get_calendar_with_blocked_dates(today.year, today.month),
            )
        except Exception as e:
            logger.error(f"Ошибка отправки календаря: {e}")
        return
    
    try:
        await callback_query.message.edit_text(
            f"⏰ Выберите время для {new_date}:",
            reply_markup=time_selection_keyboard(available_times),
        )
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения: {e}")
        await callback_query.message.answer(
            f"⏰ Выберите время для {new_date}:",
            reply_markup=time_selection_keyboard(available_times),
        )
    
    try:
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}")

@router.callback_query(TimeSelect.filter(), AdminRescheduleStates.reschedule_time)
async def admin_confirm_reschedule(callback_query: types.CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Confirm rescheduling."""
    new_time = callback_query.data.split(":", 1)[1].replace('.', ':')
    data = await state.get_data()
    appointment_id = data.get("appointment_id")
    new_date = data.get("reschedule_date")
    
    details = await AdminService.get_appointment_details(appointment_id)
    if not details:
        try:
            await callback_query.answer("Ошибка: запись не найдена", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")
        return
    
    # Answer callback immediately to avoid timeout
    try:
        await callback_query.answer("✅ Запись перенесена. Уведомление отправлено клиенту")
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}")
    
    # Send notification BEFORE updating database
    try:
        await NotificationService.notify_appointment_rescheduled(
            bot,
            appointment_id,
            new_date,
            new_time,
            old_date=details['date'],
            old_time=details['time'],
        )
    except Exception as e:
        logger.error(f"Failed to send reschedule notification: {e}")
    
    # Send admin notification
    try:
        await NotificationService.notify_admin_appointment_rescheduled(
            first_name=details.get('first_name', ''),
            last_name=details.get('last_name', ''),
            service_name=details['service_name'],
            old_date=details['date'],
            old_time=details['time'],
            new_date=new_date,
            new_time=new_time,
        )
    except Exception as e:
        logger.error(f"Failed to send admin reschedule notification: {e}")
    
    # THEN update database
    await AdminService.reschedule_appointment_by_admin(appointment_id, new_date, new_time)
    
    await state.clear()
    
    # Edit message with result
    try:
        await callback_query.message.edit_text(
            f"✅ Запись перенесена:\n{details['service_name']}\nНовая дата: {new_date} в {new_time}"
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            # If message is the same, just create a new one
            await callback_query.message.answer(
                f"✅ Запись перенесена:\n{details['service_name']}\nНовая дата: {new_date} в {new_time}",
                reply_markup=admin_menu_keyboard(),
            )
        else:
            logger.error(f"Telegram error during reschedule: {e}")
            await callback_query.message.answer("✅ Запись успешно перенесена!")
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
        await callback_query.message.answer("✅ Запись успешно перенесена!")

# ==================== SERVICE MANAGEMENT ====================

@router.message(F.text == "⚙️ Прайс")
async def admin_services_list_text(message: types.Message) -> None:
    """Show pricelist with image."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-меню")
        return
    
    try:
        from pathlib import Path
        from app.config import DATA_DIR
        
        # Try to find pricelist image
        pricelist_path = Path(DATA_DIR) / "images" / "pricelist.jpg"
        
        if pricelist_path.exists():
            await message.answer_photo(
                photo=FSInputFile(str(pricelist_path)),
                caption="✨ Наш прайс-лист",
                reply_markup=pricelist_keyboard(),
            )
        else:
            await message.answer(
                "⚙️ Управление услугами:",
                reply_markup=admin_services_keyboard(),
            )
    except Exception as e:
        logger.error(f"Error showing pricelist: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.callback_query(PricelistUpload.filter())
async def upload_pricelist(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Request new pricelist image from admin."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminBlockingStates.upload_pricelist)
    await callback_query.message.delete()
    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="pricelist_cancel")]
    ])
    await callback_query.message.answer(
        "📸 Отправьте новую картинку прайса:",
        reply_markup=cancel_keyboard
    )
    await callback_query.answer()

@router.callback_query(PricelistCancel.filter())
async def cancel_pricelist_upload(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel pricelist upload."""
    await state.clear()
    await callback_query.message.edit_text(
        "✨ Прайс-лист:",
        reply_markup=pricelist_keyboard(),
    )
    await callback_query.answer()

@router.message(AdminBlockingStates.upload_pricelist)
async def handle_pricelist_upload(message: types.Message, state: FSMContext) -> None:
    """Handle pricelist image upload."""
    from app.config import DATA_DIR
    from pathlib import Path
    
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте картинку")
        return
    
    try:
        # Get largest resolution photo
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        
        # Create images directory if it doesn't exist
        images_dir = Path(DATA_DIR) / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        # Save photo with absolute path
        pricelist_path = images_dir / "pricelist.jpg"
        await message.bot.download_file(file_info.file_path, str(pricelist_path))
        
        await state.clear()
        await message.answer(
            "✅ Прайс-лист обновлён",
            reply_markup=pricelist_keyboard(),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при загрузке: {str(e)}")

@router.message(F.text == "📢 Рассылка")
async def admin_broadcast_start(message: types.Message, state: FSMContext) -> None:
    """Start broadcast to all users."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-меню")
        return
    
    await state.set_state(BroadcastStates.broadcast_text)
    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast_cancel")]
    ])
    await message.answer(
        "📢 Введите текст, фото или фото с подписью\n\n"
        "Ввод только одним сообщением:\n"
        "• Текст\n"
        "• Фото с подписью (подпись в описании фото)\n"
        "• Просто фото",
        reply_markup=cancel_keyboard
    )

@router.callback_query(BroadcastCancel.filter())
async def cancel_broadcast(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel broadcast."""
    await state.clear()
    await callback_query.message.delete()
    await callback_query.message.answer(
        "👨‍💼 Меню администратора",
        reply_markup=admin_menu_keyboard(),
    )
    await callback_query.answer()

@router.message(BroadcastStates.broadcast_text)
async def handle_broadcast_text(message: types.Message, state: FSMContext) -> None:
    """Handle broadcast message (text, photo, or photo with caption)."""
    # Allow main menu buttons to be processed by their handlers
    if message.text in ["📋 Записи", "📆 График"]:
        await state.clear()
        if message.text == "📋 Записи":
            await admin_appointments_menu(message)
        elif message.text == "📆 График":
            await admin_block_time_text(message, state)
        return
    
    # Handle text message
    if message.text:
        broadcast_text = message.text
        broadcast_photo = None
    # Handle photo with caption
    elif message.photo:
        broadcast_text = message.caption or ""
        broadcast_photo = message.photo[-1]
    else:
        await message.answer("❌ Пожалуйста, отправьте текст, фото или фото с подписью")
        return
    
    # Send broadcast
    import logging
    logger = logging.getLogger(__name__)
    
    async with get_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT telegram_id FROM clients")
            clients = await cursor.fetchall()
    
    logger.info(f"Broadcast started. Clients count: {len(clients)}")
    
    if not clients:
        await message.answer("❌ Нет клиентов в базе данных")
        await state.clear()
        return
    
    sent_count = 0
    failed_count = 0
    
    # Use user bot for sending broadcasts
    from app.config import BOT_TOKEN, TELEGRAM_PROXY
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.client.session.aiohttp import AiohttpSession
    
    # Create session with proxy
    session = AiohttpSession(proxy=TELEGRAM_PROXY)
    
    user_bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=None),
        session=session,
    )
    
    logger.info(f"User bot created. Broadcasting to {len(clients)} clients")
    logger.info(f"Broadcast text: {broadcast_text[:50] if broadcast_text else 'No text'}")
    logger.info(f"Has photo: {broadcast_photo is not None}")
    
    # Download photo once if it exists (file_id is bot-specific and won't work with user bot)
    photo_bytes = None
    if broadcast_photo:
        try:
            logger.info(f"Downloading photo from admin bot...")
            file_info = await message.bot.get_file(broadcast_photo.file_id)
            photo_bytes = await message.bot.download_file(file_info.file_path)
            logger.info(f"Photo downloaded successfully")
        except Exception as e:
            logger.error(f"Failed to download photo: {e}")
            broadcast_photo = None  # Fall back to text only
    
    try:
        cached_file_id = None
        first_send = True
        throttle_delay = 0  # No throttle initially
        
        for (user_id,) in clients:
            try:
                if broadcast_photo and photo_bytes:
                    from aiogram.types import BufferedInputFile
                    
                    if first_send:
                        # First client: send file to get file_id
                        photo_bytes.seek(0)
                        photo_data = photo_bytes.read()
                        buffered_file = BufferedInputFile(photo_data, filename="broadcast.jpg")
                        result = await user_bot.send_photo(
                            chat_id=user_id,
                            photo=buffered_file,
                            caption=broadcast_text,
                        )
                        # Cache file_id for reuse
                        cached_file_id = result.photo[-1].file_id
                        first_send = False
                        logger.info(f"Broadcast: First send complete, cached file_id: {cached_file_id[:20]}...")
                    else:
                        # Other clients: use cached file_id (much faster!)
                        await user_bot.send_photo(
                            chat_id=user_id,
                            photo=cached_file_id,
                            caption=broadcast_text,
                        )
                elif broadcast_text:
                    await user_bot.send_message(
                        chat_id=user_id,
                        text=broadcast_text,
                    )
                
                # Apply throttle delay if needed
                if throttle_delay > 0:
                    await asyncio.sleep(throttle_delay)
                else:
                    # Default: 50ms between messages = ~20 messages/sec (safe, limit is 30/sec)
                    await asyncio.sleep(0.05)
                    
            except TelegramAPIError as e:
                error_msg = str(e)
                
                # Handle throttling (429 Too Many Requests)
                if "429" in error_msg or "too many requests" in error_msg.lower():
                    logger.warning(f"Throttled by Telegram API. Increasing delay...")
                    # Exponential backoff: increase delay on throttle
                    throttle_delay = min(1.0, (throttle_delay or 0.05) * 2)
                    logger.info(f"New throttle delay: {throttle_delay}s")
                    # Retry this message after delay
                    await asyncio.sleep(throttle_delay)
                    try:
                        if broadcast_photo and photo_bytes and cached_file_id:
                            await user_bot.send_photo(
                                chat_id=user_id,
                                photo=cached_file_id,
                                caption=broadcast_text,
                            )
                        elif broadcast_text:
                            await user_bot.send_message(
                                chat_id=user_id,
                                text=broadcast_text,
                            )
                        sent_count += 1
                        logger.info(f"Retry successful for user {user_id}")
                    except Exception as retry_error:
                        logger.error(f"Retry failed for user {user_id}: {retry_error}")
                        failed_count += 1
                else:
                    # Other errors
                    logger.error(f"Failed to send broadcast to {user_id}: {e}")
                    failed_count += 1
            except Exception as e:
                logger.error(f"Unexpected error sending to {user_id}: {e}")
                failed_count += 1
            else:
                sent_count += 1
    finally:
        await user_bot.session.close()
    
    await state.clear()
    await message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"✓ Отправлено: {sent_count}\n"
        f"✗ Ошибок: {failed_count}",
        reply_markup=admin_menu_keyboard(),
    )

# ==================== FEEDBACK MANAGEMENT ====================

PER_PAGE_FEEDBACK = 10

async def render_feedback_page(message_obj, page: int = 1, edit: bool = False) -> None:
    feedbacks = await AdminService.get_recent_feedback(limit=100)

    if not feedbacks:
        text = "💬 Отзывов еще нет"
        if edit:
            await message_obj.edit_text(text, reply_markup=admin_main_menu_inline())
        else:
            await message_obj.answer(text, reply_markup=admin_menu_keyboard())
        return

    total_pages = max((len(feedbacks) + PER_PAGE_FEEDBACK - 1) // PER_PAGE_FEEDBACK, 1)
    page = max(1, min(page, total_pages))
    page_items = feedbacks[(page - 1) * PER_PAGE_FEEDBACK : page * PER_PAGE_FEEDBACK]
    offset = (page - 1) * PER_PAGE_FEEDBACK

    text = f"💬 Последние отзывы (стр. {page}/{total_pages}):\n\n"
    keyboard = []

    for idx, fb in enumerate(page_items, offset + 1):
        date_str = fb["created_at"][:10] if fb["created_at"] else "—"
        client_name = fb["client_name"] or f"ID: {fb['telegram_id']}"
        service_name = fb["service_name"] or "—"
        comment = fb["comment"] or ""
        comment_preview = (comment[:30] + "...") if len(comment) > 30 else comment

        text += f"{idx}. {client_name} ({date_str})\n"
        text += f"   Услуга: {service_name}\n"
        text += f"   Отзыв: {comment_preview or 'только фото'}\n"
        if fb["photo_filename"]:
            text += f"   📷 Есть фото\n"
        text += "\n"

        keyboard.append([
            InlineKeyboardButton(
                text=f"Отзыв {idx}",
                callback_data=ViewFeedback(feedback_id=fb["id"]).pack(),
            )
        ])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀", callback_data=FeedbacksPage(page=page - 1).pack()))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="▶", callback_data=FeedbacksPage(page=page + 1).pack()))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuMain().pack())])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    if edit:
        await message_obj.edit_text(text, reply_markup=markup)
    else:
        await message_obj.answer(text, reply_markup=markup)

@router.message(F.text == "💬 Отзывы")
async def admin_feedback_menu(message: types.Message) -> None:
    """Show recent feedback."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-меню")
        return
    await render_feedback_page(message)


@router.callback_query(FeedbacksPage.filter())
async def admin_feedback_page_callback(callback_query: types.CallbackQuery, callback_data: FeedbacksPage) -> None:
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    await render_feedback_page(callback_query.message, page=callback_data.page, edit=True)
    await callback_query.answer()

@router.callback_query(ViewFeedback.filter())
async def view_feedback_detail(callback_query: types.CallbackQuery, callback_data: ViewFeedback) -> None:
    """View full feedback details."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    feedback_id = callback_data.feedback_id
    
    async with get_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT f.id, c.telegram_id, c.first_name, a.appointment_date, s.name, "
                "f.comment, f.photo_filename, f.created_at "
                "FROM feedback f "
                "LEFT JOIN appointments a ON f.appointment_id = a.id "
                "LEFT JOIN clients c ON f.telegram_id = c.telegram_id "
                "LEFT JOIN services s ON a.service_id = s.id "
                "WHERE f.id = ?",
                (feedback_id,)
            )
            row = await cursor.fetchone()
    
    if not row:
        await callback_query.answer("Отзыв не найден", show_alert=True)
        return
    
    _, telegram_id, client_name, appointment_date, service_name, comment, photo_filename, created_at = row
    
    text = (
        f"💬 Полный отзыв\n\n"
        f"👤 Клиент: {client_name or 'Неизвестно'}\n"
        f"📅 Визит: {appointment_date or 'не указана'}\n"
        f"✨ Услуга: {service_name or 'не указана'}\n"
        f"📝 Отзыв: {comment or '(нет текста)'}\n"
        f"⏰ Дата отзыва: {created_at[:10]}\n"
    )
    
    keyboard = []
    if telegram_id:
        keyboard.append([
            InlineKeyboardButton(text="💬 Ответить клиенту", callback_data=ReplyFeedback(telegram_id=telegram_id).pack())
        ])
    
    keyboard.append([InlineKeyboardButton(text="🏠 Назад к отзывам", callback_data=BackToFeedbacks().pack())])
    
    # If there's a photo, send it with caption
    if photo_filename:
        photo_path = Path(DATA_DIR) / "images" / "feedback" / photo_filename
        if photo_path.exists():
            try:
                cache_key = f"feedback_{feedback_id}"
                await callback_query.message.delete()
                if cache_key in _ADMIN_PHOTO_CACHE:
                    msg = await callback_query.message.answer_photo(
                        photo=_ADMIN_PHOTO_CACHE[cache_key],
                        caption=text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                    )
                else:
                    msg = await callback_query.message.answer_photo(
                        photo=FSInputFile(str(photo_path)),
                        caption=text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                    )
                    if msg.photo:
                        _ADMIN_PHOTO_CACHE[cache_key] = msg.photo[-1].file_id
            except Exception:
                await callback_query.message.answer(
                    text + "\n\n⚠️ (фото не найдено)",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                )
        else:
            try:
                await callback_query.message.edit_text(
                    text + "\n\n⚠️ (фото недоступно)",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                )
            except Exception:
                await callback_query.message.answer(
                    text + "\n\n⚠️ (фото недоступно)",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                )
    else:
        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            )
        except Exception:
            await callback_query.message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            )

    await callback_query.answer()

@router.callback_query(BackToFeedbacks.filter())
async def back_to_feedbacks(callback_query: types.CallbackQuery) -> None:
    """Go back to feedbacks list."""
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await render_feedback_page(callback_query.message, edit=False)
    await callback_query.answer()
@router.callback_query(ReplyFeedback.filter())
async def reply_to_feedback(callback_query: types.CallbackQuery, state: FSMContext, callback_data: ReplyFeedback) -> None:
    """Start replying to feedback."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    telegram_id = callback_data.telegram_id
    await state.update_data(client_telegram_id=telegram_id)
    await state.set_state(AdminFeedbackReplyStates.reply_text)
    
    await callback_query.answer()
    await callback_query.message.answer(
        "💬 Напишите ответное сообщение клиенту:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=CancelReply().pack())]
        ]),
    )

@router.callback_query(CancelReply.filter())
async def cancel_reply(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel replying to feedback."""
    await state.clear()
    await callback_query.answer()
    await callback_query.message.answer(
        "❌ Ответ отменен",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")]
        ]),
    )

@router.message(AdminFeedbackReplyStates.reply_text)
async def send_reply(message: types.Message, state: FSMContext) -> None:
    """Send reply to client."""
    data = await state.get_data()
    client_telegram_id = data.get("client_telegram_id")
    
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте текстовое сообщение")
        return
    
    # Send message to client using user bot
    from app.config import BOT_TOKEN, TELEGRAM_PROXY
    from aiogram.client.default import DefaultBotProperties
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.enums import ParseMode
    
    session = AiohttpSession(proxy=TELEGRAM_PROXY)
    user_bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=None),
        session=session,
    )
    
    try:
        await user_bot.send_message(
            chat_id=client_telegram_id,
            text=f"💬 Ответ от студии:\n\n{message.text}",
        )
        await message.answer(
            "✅ Ответ отправлен клиенту",
            reply_markup=admin_menu_keyboard(),
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка отправки: {str(e)}",
            reply_markup=admin_menu_keyboard(),
        )
    finally:
        await user_bot.session.close()
    
    await state.clear()


@router.message(F.text == "👥 Клиенты")
async def admin_clients_menu(message: types.Message) -> None:
    """Open clients root menu."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-меню")
        return
    
    error = is_sandbox_restricted("📋 Управление клиентами")
    if error:
        await message.answer(error)
        return

    await message.answer(
        "👥 Работа с клиентами",
        reply_markup=clients_root_keyboard(),
    )


@router.callback_query(ClientsMenu.filter())
async def admin_clients_menu_callback(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Open clients root menu from callbacks. Initialize viewing state."""
    await state.clear()
    await callback_query.message.edit_text(
        "👥 Работа с клиентами",
        reply_markup=clients_root_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(ClientsList.filter())
async def clients_list(callback_query: types.CallbackQuery, state: FSMContext, callback_data: ClientsList) -> None:
    """Show clients page with FSM state tracking."""
    page = callback_data.page
    await state.set_state(AdminClientsViewStates.viewing_list)
    await state.update_data(view_type="clients", current_page=page)
    await render_clients_page(callback_query.message, page)
    await callback_query.answer()


@router.callback_query(ClientsBans.filter())
async def clients_banlist(callback_query: types.CallbackQuery, state: FSMContext, callback_data: ClientsBans) -> None:
    """Show ban list page with FSM state tracking."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    error = is_sandbox_restricted("⛔ Управление банлистом")
    if error:
        await callback_query.message.edit_text(error)
        await callback_query.answer()
        return
    
    page = callback_data.page
    await state.set_state(AdminClientsViewStates.viewing_list)
    await state.update_data(view_type="bans", current_page=page)
    await render_banlist_page(callback_query.message, page)
    await callback_query.answer()


@router.callback_query(ClientsView.filter())
@router.callback_query(ClientsBanView.filter())
async def client_view(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    callback_data: ClientsView | ClientsBanView,
) -> None:
    """Show client card from clients list or ban list with FSM state."""
    source = "bans" if isinstance(callback_data, ClientsBanView) else "clients"
    telegram_id = callback_data.telegram_id
    page = callback_data.page
    
    await state.set_state(AdminClientsViewStates.viewing_detail)
    await state.update_data(
        detail_telegram_id=telegram_id,
        detail_source=source,
        detail_page=page,
    )
    await render_client_card(callback_query.message, telegram_id, source, page)
    await callback_query.answer()


@router.callback_query(ClientsHistory.filter())
async def client_history(callback_query: types.CallbackQuery, state: FSMContext, callback_data: ClientsHistory) -> None:
    """Show client appointment history with FSM context."""
    telegram_id = callback_data.telegram_id
    source = callback_data.source
    page = callback_data.page
    
    # Store state for this view
    await state.set_state(AdminClientsViewStates.viewing_detail)
    await state.update_data(
        detail_telegram_id=telegram_id,
        detail_source=source,
        detail_page=page,
        viewing_history=True,
    )
    
    history = await AdminService.get_client_history(telegram_id)
    if not history:
        await callback_query.answer("История пуста", show_alert=True)
        return

    lines = [f"📊 История клиента {telegram_id}", ""]
    total_price = 0
    for apt in history[:15]:
        lines.append(f"• {format_date_for_display(apt['date'])} {apt['time']}")
        lines.append(f"  {apt['service']} | {apt['status']} | {apt['price']} ₽")
        if apt.get("note"):
            lines.append(f"  Заметка: {apt['note']}")
        lines.append("")
        total_price += apt["price"] or 0
    lines.append(f"Итого: {total_price} ₽")

    await callback_query.message.edit_text(
        "\n".join(lines),
        reply_markup=client_detail_keyboard(
            int(telegram_id),
            source,
            page,
            is_banned=await AdminService.is_user_banned(telegram_id),
        ),
    )
    await callback_query.answer()


@router.callback_query(ClientsBan.filter())
async def client_ban_start(callback_query: types.CallbackQuery, state: FSMContext, callback_data: ClientsBan) -> None:
    """Start ban reason capture with FSM context preservation."""
    telegram_id = callback_data.telegram_id
    source = callback_data.source
    page = callback_data.page
    if await AdminService.is_user_banned(telegram_id):
        await callback_query.answer("Пользователь уже в бане", show_alert=True)
        return

    await state.set_state(AdminClientStates.ban_reason)
    await state.update_data(
        target_telegram_id=telegram_id,
        client_source=source,
        client_page=page,
        # Save detail context for restoration after ban
        detail_telegram_id=telegram_id,
        detail_source=source,
        detail_page=page,
    )
    await callback_query.message.answer(
        f"⛔ Введите причину блокировки для {telegram_id}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=ClientsCancel(telegram_id=telegram_id, source=source, page=page).pack())]]
        ),
    )
    await callback_query.answer()


@router.message(AdminClientStates.ban_reason)
async def client_ban_finish(message: types.Message, state: FSMContext) -> None:
    """Save ban reason and ban user, return to detail view with FSM."""
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("❌ Укажите причину блокировки текстом.")
        return

    data = await state.get_data()
    telegram_id = int(data["target_telegram_id"])
    source = data.get("client_source", "clients")
    page = int(data.get("client_page", 1))
    await AdminService.ban_user(telegram_id, message.from_user.id, reason)
    
    # Return to detail view with state
    await state.set_state(AdminClientsViewStates.viewing_detail)
    await state.update_data(
        detail_telegram_id=telegram_id,
        detail_source=source,
        detail_page=page,
    )
    await message.answer(f"✅ Пользователь {telegram_id} заблокирован.\nПричина: {reason}")


@router.callback_query(ClientsUnban.filter())
async def client_unban(callback_query: types.CallbackQuery, callback_data: ClientsUnban) -> None:
    """Unban a user."""
    telegram_id = callback_data.telegram_id
    source = callback_data.source
    page = callback_data.page
    if not await AdminService.is_user_banned(telegram_id):
        await callback_query.answer("Пользователь не заблокирован", show_alert=True)
        return

    await AdminService.unban_user(telegram_id)
    await render_client_card(callback_query.message, telegram_id, source, page)
    await callback_query.answer("Пользователь разблокирован")


@router.callback_query(ClientsMessage.filter())
async def client_message_start(callback_query: types.CallbackQuery, state: FSMContext, callback_data: ClientsMessage) -> None:
    """Start message to client flow with FSM context."""
    telegram_id = callback_data.telegram_id
    source = callback_data.source
    page = callback_data.page
    await state.set_state(AdminClientStates.message_text)
    await state.update_data(
        target_telegram_id=telegram_id,
        client_source=source,
        client_page=page,
        # Save detail context for restoration
        detail_telegram_id=telegram_id,
        detail_source=source,
        detail_page=page,
    )
    await callback_query.message.answer(
        f"💬 Напишите сообщение для {telegram_id}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=ClientsCancel(telegram_id=telegram_id, source=source, page=page).pack())]]
        ),
    )
    await callback_query.answer()


@router.message(AdminClientStates.message_text)
async def client_message_finish(message: types.Message, state: FSMContext) -> None:
    """Send a direct message to client via user bot, return to detail with FSM."""
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Отправьте текстовое сообщение.")
        return

    data = await state.get_data()
    client_telegram_id = int(data["target_telegram_id"])
    source = data.get("client_source", "clients")
    page = int(data.get("client_page", 1))

    from app.config import BOT_TOKEN, TELEGRAM_PROXY
    from aiogram.client.default import DefaultBotProperties
    from aiogram.client.session.aiohttp import AiohttpSession

    session = AiohttpSession(proxy=TELEGRAM_PROXY)
    user_bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=None),
        session=session,
    )
    try:
        await user_bot.send_message(
            chat_id=client_telegram_id,
            text=f"💬 Сообщение от студии:\n\n{text}",
        )
        await message.answer(f"✅ Сообщение отправлено пользователю {client_telegram_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {e}")
    finally:
        await user_bot.session.close()
    
    # Return to detail view with state
    await state.set_state(AdminClientsViewStates.viewing_detail)
    await state.update_data(
        detail_telegram_id=client_telegram_id,
        detail_source=source,
        detail_page=page,
    )


@router.callback_query(ClientsCancel.filter())
async def client_action_cancel(callback_query: types.CallbackQuery, state: FSMContext, callback_data: ClientsCancel) -> None:
    """Cancel a client-side admin flow and return to the client's card."""
    await state.set_state(AdminClientsViewStates.viewing_detail)
    await state.update_data(
        detail_telegram_id=callback_data.telegram_id,
        detail_source=callback_data.source,
        detail_page=callback_data.page,
    )
    await render_client_card(
        callback_query.message,
        callback_data.telegram_id,
        callback_data.source,
        callback_data.page,
    )
    await callback_query.answer()


@router.callback_query(AppointmentNav.filter(), AdminAppointmentsViewStates.viewing_appointments)
async def handle_appointment_navigation(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    callback_data: AppointmentNav,
) -> None:
    """Handle navigation in appointments view with FSM state."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return

    view_type = callback_data.view_type
    direction = callback_data.direction
    
    data = await state.get_data()
    current_page = data.get("current_page", 1)
    
    if direction == "prev":
        new_page = current_page - 1
    elif direction == "next":
        new_page = current_page + 1
    else:
        await callback_query.answer()
        return
    
    # Update state
    await state.update_data(current_page=new_page)
    
    # Re-render the page
    await render_appointments_page(callback_query.message, view_type, new_page)
    await callback_query.answer()


@router.callback_query(AppointmentBack.filter(), AdminAppointmentsViewStates.viewing_appointments)
async def handle_appointment_back(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    callback_data: AppointmentBack,
) -> None:
    """Go back to appointments list from details."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return

    view_type = callback_data.view_type
    page = callback_data.page
    
    # Update state to the previous view
    await state.update_data(view_type=view_type, current_page=page)
    
    # Re-render the list
    await render_appointments_page(callback_query.message, view_type, page)
    await callback_query.answer()


@router.callback_query(ClientsBook.filter())
async def client_manual_booking_start(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    callback_data: ClientsBook,
) -> None:
    """Start manual booking for a client with FSM context."""
    telegram_id = callback_data.telegram_id
    source = callback_data.source
    page = callback_data.page
    client = await AdminService.get_client_by_telegram_id(telegram_id)
    if not client:
        await callback_query.answer("Клиент не найден", show_alert=True)
        return

    services = await CatalogService.list_services()
    buttons = [
        [InlineKeyboardButton(text=f"{service['name']} | {service['price']} ₽", callback_data=ManualBookService(service_id=service["id"]).pack())]
        for service in services
    ]
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data=ClientsCancel(telegram_id=telegram_id, source=source, page=page).pack())])

    await state.set_state(AdminManualBookingStates.select_service)
    await state.update_data(
        manual_telegram_id=telegram_id,
        manual_source=source,
        manual_page=page,
        # Store detail context for return after booking
        detail_telegram_id=telegram_id,
        detail_source=source,
        detail_page=page,
    )
    await callback_query.message.answer(
        f"📝 Ручная запись для {format_client_name(client)}\nВыберите услугу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback_query.answer()


@router.callback_query(ManualBookService.filter(), AdminManualBookingStates.select_service)
async def client_manual_booking_service(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    callback_data: ManualBookService,
) -> None:
    """Select service for manual booking."""
    service_id = callback_data.service_id
    service = await CatalogService.get_service(service_id)
    if not service:
        await callback_query.answer("Услуга не найдена", show_alert=True)
        return

    await state.update_data(
        manual_service_id=service_id,
        manual_service_name=service["name"],
    )
    await state.set_state(AdminManualBookingStates.select_date)
    today = datetime.now(get_tz_sync()).date()
    await callback_query.message.answer(
        "📅 Выберите дату записи:",
        reply_markup=await get_calendar_with_blocked_dates(today.year, today.month),
    )
    await callback_query.answer()


@router.callback_query(CalendarAction.filter(), AdminManualBookingStates.select_date)
async def manual_booking_calendar_month_change(
    callback_query: types.CallbackQuery,
    callback_data: CalendarAction,
) -> None:
    """Navigate calendar while selecting manual booking date."""
    await callback_query.message.edit_reply_markup(
        reply_markup=await get_calendar_with_blocked_dates(callback_data.year, callback_data.month),
    )
    await callback_query.answer()


@router.callback_query(CalendarDate.filter(), AdminManualBookingStates.select_date)
async def manual_booking_date_selected(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    callback_data: CalendarDate,
) -> None:
    """Select date for manual booking and offer time slots."""
    appointment_date = callback_data.date
    data = await state.get_data()
    service_id = data.get("manual_service_id")
    available_times = await BookingService.get_available_times(appointment_date, service_id)
    if not available_times:
        await callback_query.answer("На эту дату нет доступного времени", show_alert=True)
        return

    await state.update_data(manual_date=appointment_date)
    await state.set_state(AdminManualBookingStates.select_time)
    await callback_query.message.answer(
        f"⏰ Выберите время для {format_date_for_display(appointment_date)}:",
        reply_markup=time_selection_keyboard(available_times),
    )
    await callback_query.answer()


@router.callback_query(TimeSelect.filter(), AdminManualBookingStates.select_time)
async def manual_booking_time_selected(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    callback_data: TimeSelect,
) -> None:
    """Select time for manual booking."""
    appointment_time = callback_data.time.replace('.', ':')
    await state.update_data(manual_time=appointment_time)
    await state.set_state(AdminManualBookingStates.note)
    await callback_query.message.answer(
        "💬 Введите комментарий к записи или отправьте `нет`.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Без комментария", callback_data=ManualBookNote().pack())]]
        ),
    )
    await callback_query.answer()


@router.callback_query(ManualBookNote.filter(), AdminManualBookingStates.note)
async def manual_booking_no_note(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Create manual booking without note."""
    await callback_query.answer()  # Answer callback immediately
    await finalize_manual_booking(callback_query.message, state, callback_query.from_user, note="")


@router.message(AdminManualBookingStates.note)
async def manual_booking_note_received(message: types.Message, state: FSMContext) -> None:
    """Create manual booking with note."""
    note = "" if (message.text or "").strip().lower() == "нет" else (message.text or "").strip()
    await finalize_manual_booking(message, state, message.from_user, note=note)

@router.callback_query(ServiceList.filter())
async def show_services_list(callback_query: types.CallbackQuery) -> None:
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return

    await callback_query.answer()

    services = await AdminService.get_services()

    await callback_query.message.delete()

    if not services:
        await callback_query.message.answer(
            "📋 Услуг не найдено. Создайте первую услугу.",
            reply_markup=admin_services_keyboard(),
        )
    else:
        await callback_query.message.answer(
            "📋 Все услуги:",
            reply_markup=services_list_keyboard(services),
        )

@router.callback_query(ServiceCreate.filter())
async def start_create_service(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Start creating new service."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.set_state(ServiceManagementStates.create_name)
    await callback_query.message.edit_text(
        "📝 Введите название услуги:",
        reply_markup=service_edit_cancel_keyboard(0)  # 0 indicates new service
    )
    await callback_query.answer()

@router.message(ServiceManagementStates.create_name)
async def process_service_name(message: types.Message, state: FSMContext) -> None:
    """Process service name (for both create and edit)."""
    # Handle cancel button
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("🚫 Отменено", reply_markup=admin_services_keyboard())
        return
    
    data = await state.get_data()
    is_edit = data.get("is_edit", False)
    
    if is_edit:
        # Editing existing service
        service_id = data.get("service_id")
        await AdminService.update_service(service_id, name=message.text)
        await state.clear()
        await message.answer(f"✅ Название обновлено на '{message.text}'")
        service = await AdminService.get_service(service_id)
        if service:
            await message.answer(
                f"📋 Услуга: {service['name']}\n💰 Цена: {service['price']}₽\n⏱️ Длительность: {service['duration']} мин",
                reply_markup=service_edit_keyboard(service_id)
            )
    else:
        # Creating new service
        await state.update_data(name=message.text)
        await state.set_state(ServiceManagementStates.create_description)
        await message.answer(
            "📄 Введите описание услуги:"
        )

@router.message(ServiceManagementStates.create_description)
async def process_service_description(message: types.Message, state: FSMContext) -> None:
    """Process service description (for both create and edit)."""
    # Handle cancel button
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("🚫 Отменено", reply_markup=admin_services_keyboard())
        return
    
    data = await state.get_data()
    is_edit = data.get("is_edit", False)
    
    if is_edit:
        # Editing existing service
        service_id = data.get("service_id")
        await AdminService.update_service(service_id, description=message.text)
        await state.clear()
        await message.answer(f"✅ Описание обновлено")
        service = await AdminService.get_service(service_id)
        if service:
            await message.answer(
                f"📋 Услуга: {service['name']}\n💰 Цена: {service['price']}₽\n⏱️ Длительность: {service['duration']} мин",
                reply_markup=service_edit_keyboard(service_id)
            )
    else:
        # Creating new service
        await state.update_data(description=message.text)
        await state.set_state(ServiceManagementStates.create_price)
        await message.answer(
            "💰 Введите цену (в рублях):"
        )

@router.message(ServiceManagementStates.create_price)
async def process_service_price(message: types.Message, state: FSMContext) -> None:
    """Process service price (for both create and edit)."""
    # Handle cancel button
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("🚫 Отменено", reply_markup=admin_services_keyboard())
        return
    
    data = await state.get_data()
    is_edit = data.get("is_edit", False)
    
    try:
        price = int(message.text)
        
        if is_edit:
            # Editing existing service
            service_id = data.get("service_id")
            await AdminService.update_service(service_id, price=price)
            await state.clear()
            await message.answer(f"✅ Цена обновлена на {price}₽")
            service = await AdminService.get_service(service_id)
            if service:
                await message.answer(
                    f"📋 Услуга: {service['name']}\n💰 Цена: {service['price']}₽\n⏱️ Длительность: {service['duration']} мин",
                    reply_markup=service_edit_keyboard(service_id)
                )
        else:
            # Creating new service
            await state.update_data(price=price)
            await state.set_state(ServiceManagementStates.create_duration)
            await message.answer(
                "⏱️ Введите длительность (в минутах):"
            )
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число для цены:"
        )

@router.message(ServiceManagementStates.create_duration)
async def process_service_duration(message: types.Message, state: FSMContext) -> None:
    """Process and save service (for both create and edit)."""
    # Handle cancel button
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("🚫 Отменено", reply_markup=admin_services_keyboard())
        return
    
    data = await state.get_data()
    is_edit = data.get("is_edit", False)
    
    try:
        duration = int(message.text)
        if duration <= 0:
            raise ValueError
        
        if is_edit:
            # Editing existing service
            service_id = data.get("service_id")
            await AdminService.update_service(service_id, duration=duration)
            await state.clear()
            await message.answer(f"✅ Длительность обновлена на {duration} мин")
            service = await AdminService.get_service(service_id)
            if service:
                await message.answer(
                    f"📋 Услуга: {service['name']}\n💰 Цена: {service['price']}₽\n⏱️ Длительность: {service['duration']} мин",
                    reply_markup=service_edit_keyboard(service_id)
                )
        else:
            # Creating new service
            service_id = await AdminService.create_service(
                name=data['name'],
                description=data['description'],
                price=data['price'],
                duration=duration
            )
            
            await state.clear()
            await message.answer(
                f"✅ Услуга создана:\n{data['name']}\nЦена: {data['price']}₽\nДлительность: {duration} мин",
                reply_markup=admin_services_keyboard()
            )
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите положительное число для длительности:"
        )

@router.callback_query(ServiceEdit.filter())
async def edit_service(callback_query: types.CallbackQuery, callback_data: ServiceEdit) -> None:
    """Show service edit options."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    service_id = callback_data.service_id
    service = await AdminService.get_service(service_id)
    
    if not service:
        await callback_query.answer("Услуга не найдена", show_alert=True)
        return
    
    text = (
        f"📋 Услуга: {service['name']}\n"
        f"💰 Цена: {service['price']}₽\n"
        f"⏱️ Длительность: {service['duration']} мин\n"
        f"📄 Описание: {service['description']}"
    )
    
    await callback_query.message.edit_text(
        text,
        reply_markup=service_edit_keyboard(service_id),
    )
    await callback_query.answer()

@router.callback_query(ServiceEditField.filter())
async def edit_service_field(callback_query: types.CallbackQuery, callback_data: ServiceEditField, state: FSMContext) -> None:
    """Start editing a specific service field."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    service_id = callback_data.service_id
    field = callback_data.field
    
    service = await AdminService.get_service(service_id)
    if not service:
        await callback_query.answer("Услуга не найдена", show_alert=True)
        return
    
    await state.update_data(service_id=service_id, edit_field=field, is_edit=True)
    
    if field == "name":
        await state.set_state(ServiceManagementStates.create_name)
        text = f"📄 Текущее название: {service['name']}\n\n📝 Введите новое название услуги:"
        await callback_query.message.edit_text(
            text,
            reply_markup=service_edit_cancel_keyboard(service_id)
        )
    elif field == "description":
        await state.set_state(ServiceManagementStates.create_description)
        text = f"📄 Текущее описание: {service['description']}\n\n📄 Введите новое описание услуги:"
        await callback_query.message.edit_text(
            text,
            reply_markup=service_edit_cancel_keyboard(service_id)
        )
    elif field == "price":
        await state.set_state(ServiceManagementStates.create_price)
        text = f"💰 Текущая цена: {service['price']}₽\n\n💰 Введите новую цену (в рублях):"
        await callback_query.message.edit_text(
            text,
            reply_markup=service_edit_cancel_keyboard(service_id)
        )
    elif field == "duration":
        await state.set_state(ServiceManagementStates.create_duration)
        text = f"⏱️ Текущая длительность: {service['duration']} мин\n\n⏱️ Введите новую длительность (в минутах):"
        await callback_query.message.edit_text(
            text,
            reply_markup=service_edit_cancel_keyboard(service_id)
        )
    elif field == "photo":
        await state.set_state(ServiceManagementStates.edit_photo)
        current_photo_info = "❌ Нет фото" if not service.get('photo_file_id') else "✅ Фото установлено"
        text = f"📸 Текущее фото: {current_photo_info}\n\n📸 Отправьте новое фото для услуги:"
        await callback_query.message.edit_text(
            text,
            reply_markup=service_edit_cancel_keyboard(service_id)
        )
    
    await callback_query.answer()

@router.message(ServiceManagementStates.edit_photo)
async def process_service_photo(message: types.Message, state: FSMContext) -> None:
    """Process and save service photo."""
    from app.config import SERVICE_IMAGES_DIR
    
    # Handle cancel button
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("🚫 Отменено", reply_markup=admin_services_keyboard())
        return
    
    data = await state.get_data()
    service_id = data.get("service_id")
    
    # Check if message has photo
    if message.photo:
        try:
            # Get the largest photo (last one in list)
            photo = message.photo[-1]
            file_info = await message.bot.get_file(photo.file_id)
            
            # Create services images directory if it doesn't exist
            SERVICE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            
            # Save photo with service_id as filename
            photo_filename = f"service_{service_id}.jpg"
            photo_path = SERVICE_IMAGES_DIR / photo_filename
            
            # Download and save photo
            await message.bot.download_file(file_info.file_path, str(photo_path))
            
            # Save filename to database (not file_id)
            await AdminService.set_service_photo(service_id, photo_filename)
            
            await state.clear()
            await message.answer("✅ Фото обновлено")
            service = await AdminService.get_service(service_id)
            if service:
                await message.answer(
                    f"📋 Услуга: {service['name']}\n💰 Цена: {service['price']}₽\n⏱️ Длительность: {service['duration']} мин",
                    reply_markup=service_edit_keyboard(service_id)
                )
        except Exception as e:
            logger.error(f"Error saving service photo: {e}")
            await message.answer(f"❌ Ошибка при сохранении фото: {str(e)}")
    else:
        await message.answer(
            "❌ Пожалуйста, отправьте фотографию:"
        )

@router.callback_query(ServiceDelete.filter())
async def confirm_delete_service(callback_query: types.CallbackQuery, callback_data: ServiceDelete) -> None:
    """Confirm service deletion."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    service_id = callback_data.service_id
    await callback_query.message.edit_text(
        "⚠️ Вы уверены? Услуга будет удалена.",
        reply_markup=confirm_delete_service_keyboard(service_id),
    )
    await callback_query.answer()

@router.callback_query(ServiceConfirmDelete.filter())
async def delete_service(callback_query: types.CallbackQuery, callback_data: ServiceConfirmDelete) -> None:
    """Delete service."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    service_id = callback_data.service_id
    success = await AdminService.delete_service(service_id)
    
    if success:
        await callback_query.answer("✅ Услуга удалена")
        services = await AdminService.get_services()
        if services:
            await callback_query.message.edit_text(
                "📋 Все услуги:",
                reply_markup=services_list_keyboard(services),
            )
        else:
            await callback_query.message.edit_text(
                "📋 Услуг не найдено.",
                reply_markup=admin_services_keyboard(),
            )
    else:
        await callback_query.answer("❌ Не удалось удалить услугу. Она используется в записях.", show_alert=True)

@router.callback_query(MenuMain.filter())
async def admin_main_menu(callback_query: types.CallbackQuery) -> None:
    """Show main admin menu."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа к админ-меню", show_alert=True)
        return
    await callback_query.message.edit_text(
        "👨‍💼 Админ-меню:",
        reply_markup=admin_menu_keyboard(),
    )
    await callback_query.answer()

@router.callback_query(UnblockDay.filter())
async def unblock_entire_day(callback_query: types.CallbackQuery) -> None:
    """Unblock an entire day."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    day_date = callback_query.data.split(":", 1)[1]
    
    await AdminService.unblock_entire_day(day_date)
    await callback_query.answer(f"✅ День {day_date} разблокирован")
    
    # Refresh blocked slots list
    today = datetime.now(get_tz_sync()).date().isoformat()
    blocked = await AdminService.get_blocked_slots_for_week(today)
    
    # Filter out past dates
    now = datetime.now(get_tz_sync())
    blocked = [
        s for s in blocked 
        if s['date'] > today or (s['date'] == today and s['time'] > now.strftime("%H:%M"))
    ]
    
    if not blocked:
        await callback_query.message.edit_text(
            "✓ Нет активных блокировок",
            reply_markup=blocking_type_keyboard(),
        )
    else:
        # Group by date and check if any are full day blocks
        by_date = {}
        for slot in blocked:
            if slot['date'] not in by_date:
                by_date[slot['date']] = []
            by_date[slot['date']].append(slot)
        
        text = "🔒 Заблокированные слоты:\n\n"
        
        # First pass: identify full day blocks
        full_days = set()
        for date_str, slots in by_date.items():
            for slot in slots:
                if slot['reason'] == "День заблокирован":
                    full_days.add(date_str)
                    break
        
        # Display blocked items - full days first, then individual times
        for date_str in sorted(by_date.keys()):
            if date_str in full_days:
                text += f"📅 {date_str} - День полностью заблокирован\n"
            else:
                # Show only individual time slots for this date
                for slot in by_date[date_str]:
                    text += f"📅 {slot['date']} ⏰ {slot['time']}\n"
        
        # Build blocked list without full-day entries for the keyboard
        blocked_for_keyboard = [s for s in blocked if s['reason'] != "День заблокирован"]
        
        await callback_query.message.edit_text(
            text,
            reply_markup=blocked_slots_keyboard(blocked_for_keyboard, list(full_days)),
        )

@router.callback_query(Unblock.filter())
async def unblock_time_slot(callback_query: types.CallbackQuery) -> None:
    """Unblock a time slot or entire day."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    parts = callback_query.data.split(":", 2)
    slot_date = parts[1]
    slot_time = parts[2]
    
    # Check if entire day is blocked
    blocks_for_date = await AdminService.get_blocked_slots_for_date(slot_date)
    all_reason_day = all(b['reason'] == "День заблокирован" for b in blocks_for_date)
    
    if all_reason_day and len(blocks_for_date) > 1:
        # Entire day is blocked - unblock it all
        await AdminService.unblock_entire_day(slot_date)
        msg = f"✅ День {slot_date} разблокирован"
    else:
        # Just unblock this specific time
        await AdminService.unblock_time_slot(slot_date, slot_time)
        msg = f"✅ Время {slot_time} на {slot_date} разблокировано"
    
    # Refresh blocked slots list
    today = datetime.now(get_tz_sync()).date().isoformat()
    blocked = await AdminService.get_blocked_slots_for_week(today)
    
    # Filter out past dates
    now = datetime.now(get_tz_sync())
    blocked = [
        s for s in blocked 
        if s['date'] > today or (s['date'] == today and s['time'] > now.strftime("%H:%M"))
    ]
    
    if not blocked:
        await callback_query.message.edit_text(
            "✓ Нет активных блокировок",
            reply_markup=blocking_type_keyboard(),
        )
    else:
        # Group by date and check if any are full day blocks
        by_date = {}
        for slot in blocked:
            if slot['date'] not in by_date:
                by_date[slot['date']] = []
            by_date[slot['date']].append(slot)
        
        text = "🔒 Заблокированные слоты:\n\n"
        
        # First pass: identify full day blocks
        full_days = set()
        for date_str, slots in by_date.items():
            for slot in slots:
                if slot['reason'] == "День заблокирован":
                    full_days.add(date_str)
                    break
        
        # Display blocked items - full days first, then individual times
        for date_str in sorted(by_date.keys()):
            if date_str in full_days:
                text += f"📅 {date_str} - День полностью заблокирован\n"
            else:
                # Show only individual time slots for this date
                for slot in by_date[date_str]:
                    text += f"📅 {slot['date']} ⏰ {slot['time']}\n"
        
        # Build blocked list without full-day entries for the keyboard
        blocked_for_keyboard = [s for s in blocked if s['reason'] != "День заблокирован"]
        
        await callback_query.message.edit_text(
            text,
            reply_markup=blocked_slots_keyboard(blocked_for_keyboard, list(full_days)),
        )
    
    await callback_query.answer(msg)

@router.callback_query(AdminMenu.filter())
async def back_to_admin_menu(callback_query: types.CallbackQuery) -> None:
    """Return to admin main menu from appointments."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    try:
        await callback_query.message.edit_text(
            "👨‍💼 Меню администратора",
            reply_markup=admin_menu_keyboard(),
        )
    except Exception:
        await callback_query.message.delete()
        await callback_query.message.answer(
            "👨‍💼 Меню администратора",
            reply_markup=admin_menu_keyboard(),
        )
    await callback_query.answer()

@router.callback_query(AdminScheduleMenu.filter())
async def admin_schedule_menu(callback_query: types.CallbackQuery) -> None:
    """Show schedule management submenu."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    from app.admin_bot.menu_keyboard import admin_schedule_menu_keyboard
    
    await callback_query.message.edit_text(
        "📋 <b>Управление графиком</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=admin_schedule_menu_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(AdminServices.filter())
async def back_to_admin_services(callback_query: types.CallbackQuery) -> None:
    """Return to services menu."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback_query.message.delete()
    
    try:
        from pathlib import Path
        from app.config import DATA_DIR
        
        pricelist_path = Path(DATA_DIR) / "images" / "pricelist.jpg"
        
        if pricelist_path.exists():
            await callback_query.message.answer_photo(
                photo=FSInputFile(str(pricelist_path)),
                caption="✨ Наш прайс-лист",
                reply_markup=pricelist_keyboard(),
            )
        else:
            await callback_query.message.answer(
                "✨ Наш прайс-лист",
                reply_markup=pricelist_keyboard(),
            )
    except Exception as e:
        logger.error(f"Error in back_to_admin_services: {e}")
        await callback_query.message.answer(
            "✨ Наш прайс-лист",
            reply_markup=pricelist_keyboard(),
        )
    
    await callback_query.answer()


# ==================== ADMIN COMMANDS ====================

@router.message(Command("info"))
async def admin_info(message: types.Message) -> None:
    """Show list of admin commands - main info."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    commands_text = """
    📌 КОМАНДЫ АДМИНИСТРАТОРА

    ⏱️ Время и расписание
    /timezone — установить таймзону
    По кнопкам "📆 График" -> "⚙️ Настроить график", дополнительно:
    /schedule — настроить часы работы
    /notification — уведомления о записях

    📊 Данные и статистика
    /stats           — статистика салона
    /export_clients  — выгрузить клиентов CSV
    /loadall <d1> <d2> — отчёт за период

    👤 Клиенты
    По кнопке "👥 Клиенты", дополнительно:
    /user <ID> — история клиента

    🔒 Блокировки
    /block_status — просмотр блокировок
    /clear_block  — удалить все блокировки

    ⚙️ Настройки
    /contacts — контакты салона
    /reload   — перезагрузить бота

    /info — общий обзор
    
    /time — подробнее о времени
    /data — подробнее об аналитике
    """
    
    await message.answer(commands_text)


@router.message(Command("data"))
async def admin_data(message: types.Message) -> None:
    """Show data, analytics and database commands."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    data_text = """
    📊 ДАННЫЕ И АНАЛИТИКА — /data

    Клиенты
    /user <ID>       — история клиента по Telegram ID
    /export_clients  — все клиенты в CSV (имя, телефон, визиты)

    Отчёты
    /loadall <d1> <d2> — выгрузка за период в формате DD-MM-YYYY
    Пример: /loadall 01-01-2026 31-12-2026
    Результат: последние 10 записей в чате + полный CSV

    /stats — статистика с начала работы:
    записи, клиенты, выручка, топ услуга, средний чек

    Очистка БД
    При запуске бота автоматически удаляются записи
    старше 90 дней (cancelled/completed).
    Перед удалением CSV с архивом отправляется в этот чат.
    Копия сохраняется в data/exports/.

    /info — общий обзор
    """
    
    await message.answer(data_text)


@router.message(Command("time"))
async def admin_time(message: types.Message) -> None:
    """Show time, timezone and schedule commands."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    time_text = """
    🌍 ВРЕМЯ И РАСПИСАНИЕ — /time

    Таймзона
    /timezone <±X> — установить смещение от UTC (от -12 до +14)
    Примеры: /timezone 3 (Москва), /timezone 5 (Екб), /timezone 10 (Влад)
    После изменения таймзоны рекомендуется /reload

    Уведомления
    /notification — установить время для ежедневных автоуведомлений
    
    Расписание
    /schedule — настройка режима работы:
    цикличный график (X/Y), дни недели,
    интервал слотов, время перерыва

    Также управление расписанием, выходными
    и блокировками доступно через кнопку
    «📅 График» в главном меню.

    Блокировки
    /block_status — активные блокировки слотов
    /clear_block  — удалить все блокировки

    Перезагрузка
    /reload — применить изменения (5-10 сек, требует подтверждения)

    /info — общий обзор
    """
    
    await message.answer(time_text)


@router.message(Command("contacts"))
async def admin_contacts(message: types.Message, state: FSMContext) -> None:
    """Show and edit salon_sandbox contacts."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    contacts_text = await AdminService.get_salon_sandbox_contacts()
    
    if contacts_text:
        text = f"📞 КОНТАКТЫ САЛОНА\n\n{contacts_text}"
    else:
        text = "📞 КОНТАКТЫ САЛОНА\n\n❌ Контакты еще не добавлены"
    
    buttons = [
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="contact_edit_all")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_menu")],
    ]
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(ContactEditAll.filter())
async def edit_contacts_start(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Start editing contacts as a single text block."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    contacts_text = await AdminService.get_salon_sandbox_contacts()
    current_value = contacts_text or "(пусто)"
    
    await state.set_state(ContactsEditStates.editing)
    
    text = (
        "✏️ РЕДАКТИРОВАНИЕ КОНТАКТОВ\n\n"
        f"Текущие контакты:\n{current_value}\n\n"
        "Введите контакты в любом формате (можно на нескольких строках):\n"
        "Пример:\n"
        "Телефон: +7 (999) 123-45-67\n"
        "Адрес: Никольская, 14\n"
        "📲 Instagram: @salon_sandbox_MSK\n"
    )
    
    buttons = [[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_contacts")]]
    
    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback_query.answer()


@router.message(ContactsEditStates.editing)
async def process_contacts_edit(message: types.Message, state: FSMContext) -> None:
    """Process and save all contacts at once."""
    contacts_text = message.text.strip()
    
    if not contacts_text:
        await message.answer("❌ Контакты не могут быть пустыми")
        return
    
    await AdminService.update_salon_sandbox_contacts(contacts_text)
    await state.clear()
    
    await message.answer("✅ Контакты успешно обновлены")
    
    # Show updated contacts
    text = (
        "📞 КОНТАКТЫ САЛОНА\n\n"
        f"{contacts_text}"
    )
    
    buttons = [
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="contact_edit_all")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_menu")],
    ]
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(AdminContactsMenu.filter())
async def admin_contacts_callback(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Callback handler for contacts menu."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.clear()
    
    contacts_text = await AdminService.get_salon_sandbox_contacts()
    
    if contacts_text:
        text = f"📞 КОНТАКТЫ САЛОНА\n\n{contacts_text}"
    else:
        text = "📞 КОНТАКТЫ САЛОНА\n\n❌ Контакты еще не добавлены"
    
    buttons = [
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="contact_edit_all")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_menu")],
    ]
    
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback_query.answer()


# ==================== NOTIFICATIONS ====================

@router.message(Command("notification"))
async def notification_command(message: types.Message, state: FSMContext) -> None:
    """Set auto-notification time for admin."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    await state.set_state(AdminNotificationStates.set_time)
    await message.answer(
        "⏰ Введите время для автоуведомлений (HH:MM)\n"
        "Пример: 09:00\n\n"
        "Уведомления будут отправляться только в рабочие дни со списком записей на этот день.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="notification_cancel")]
        ]),
    )


@router.callback_query(NotificationCancel.filter())
async def notification_cancel(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel notification time setting."""
    await state.clear()
    await callback_query.message.edit_text(
        "❌ Отменено",
    )
    await callback_query.answer()


@router.message(AdminNotificationStates.set_time)
async def process_notification_time(message: types.Message, state: FSMContext) -> None:
    """Process notification time input."""
    time_text = message.text.strip()
    
    # Validate time format
    if not time_text or len(time_text) != 5 or time_text[2] != ':':
        await message.answer(
            "❌ Неправильный формат времени\n"
            "Пожалуйста, используйте формат HH:MM\n"
            "Пример: 09:00"
        )
        return
    
    try:
        hours, minutes = time_text.split(':')
        hour = int(hours)
        minute = int(minutes)
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Неверный диапазон времени")
        
        # Save notification time to admin settings
        await AdminService.set_admin_notification_time(message.from_user.id, time_text)
        
        await state.clear()
        await message.answer(
            f"✅ Время уведомлений установлено: {time_text}\n\n"
            f"Вы будете получать уведомления в {time_text} каждый рабочий день "
            f"со списком всех записей на этот день."
        )
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неправильный формат времени\n"
            "Пожалуйста, используйте формат HH:MM\n"
            "Пример: 09:00"
        )


@router.message(Command("user"))
async def export_user_history(message: types.Message) -> None:
    """Export client history by telegram ID."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Неверный формат\n\n"
            "📝 Правильно: /user <telegram_id>\n\n"
            "🔹 Пример: /user 123456789\n\n"
            "💡 Найти ID можно в списке клиентов (/export_clients)"
        )
        return
    
    try:
        telegram_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Telegram ID должен быть числом\n\n"
            "🔹 Пример: /user_telegramid 123456789"
        )
        return
    
    history = await AdminService.get_client_history(telegram_id)
    
    if not history:
        await message.answer(
            f"❌ История для пользователя {telegram_id} не найдена\n\n"
            "💡 Возможно, этот пользователь ещё не записывался"
        )
        return
    
    export_text = f"📊 История пользователя: {telegram_id}\n\n"
    total_price = 0
    
    for apt in history:
        # Translate status
        status_text = {
            "planned":   "Запланирована",
            "cancelled": "Отменена",
            "no-show":   "Неявка",
        }.get(apt["status"], apt["status"])

        export_text += f"🔹 {format_date_for_display(apt['date'])} {apt['time']}\n"
        export_text += f"   Услуга: {apt['service']}\n"
        export_text += f"   Цена: {apt['price']} ₽\n"
        export_text += f"   Статус: {status_text}\n"
        if apt["note"]:
            export_text += f"   Заметка: {apt['note']}\n"
        export_text += "\n"

        if apt["status"] not in ("cancelled", "no-show"):
            total_price += apt["price"] or 0

    export_text += f"\n💰 Всего потрачено: {total_price} ₽"

@router.message(Command("loadall"))
async def export_period_appointments(message: types.Message) -> None:
    """Export appointments for a period."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    error = is_sandbox_restricted("📊 Выгрузка статистики за период")
    if error:
        await message.answer(error)
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "❌ Неверный формат\n\n"
            "📝 Правильно: /loadall <начало> <конец>\n\n"
            "🔹 Пример: /loadall 01-01-2026 31-12-2026\n\n"
            "Формат дат: DD-MM-YYYY\n"
            "Выведет последние 10 записей + полный CSV"
        )
        return

    try:
        from datetime import datetime
        start_date = datetime.strptime(args[1], "%d-%m-%Y").strftime("%Y-%m-%d")
        end_date = datetime.strptime(args[2], "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        await message.answer(
            "❌ Неверный формат дат\n\n"
            "💡 Используйте формат: DD-MM-YYYY\n\n"
            "🔹 Пример: /loadall 01-01-2026 31-12-2026"
        )
        return

    appointments = await AdminService.get_appointments_period(start_date, end_date)

    if not appointments:
        await message.answer(
            f"❌ Записей в периоде {args[1]} - {args[2]} не найдено\n\n"
            "💡 Попробуйте расширить период дат"
        )
        return

    total_revenue = sum(apt['price'] for apt in appointments if apt['price'] and apt['status'] == 'completed')

    # ── Сообщение: только последние 10 ───────────────────────────────────────
    preview = appointments[-10:]
    status_map = {
        'planned': 'Запланирована',
        'completed': 'Завершена',
        'cancelled': 'Отменена',
        'no-show': 'Неявка',
    }

    export_text = (
        f"📅 Выгрузка: {args[1]} — {args[2]}\n"
        f"📊 Всего записей: {len(appointments)}\n"
        f"💰 Выручка: {total_revenue} ₽\n\n"
        f"🕐 Последние {len(preview)} записей:\n"
        f"{'─' * 25}\n"
    )

    for apt in preview:
        export_text += (
            f"🔹 {format_date_for_display(apt['date'])} {apt['time']}\n"
            f"   {apt['client_name']} · {apt['phone']}\n"
            f"   {apt['service']} · {apt['price']} ₽\n"
            f"   {status_map.get(apt['status'], apt['status'])}\n\n"
        )

    await message.answer(export_text)

    # ── CSV: все записи ───────────────────────────────────────────────────────
    try:
        import tempfile, os
        csv_content = AdminService.generate_appointments_csv(appointments)

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.csv', delete=False, encoding='utf-8-sig', newline=''
        ) as f:
            f.write(csv_content)
            csv_path = f.name

        await message.answer_document(
            document=FSInputFile(csv_path),
            caption=(
                f"📊 Полная выгрузка: {args[1]} — {args[2]}\n"
                f"Записей: {len(appointments)} · Выручка: {total_revenue} ₽"
            )
        )
        os.remove(csv_path)
    except Exception as e:
        logger.error(f"Ошибка генерации CSV: {e}")
        await message.answer("⚠️ Не удалось сгенерировать CSV файл")

@router.message(Command("export_clients"))
async def export_clients_list(message: types.Message) -> None:
    """Export all clients."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    error = is_sandbox_restricted("📊 Выгрузка списка клиентов")
    if error:
        await message.answer(error)
        return

    clients = await AdminService.get_all_clients()

    if not clients:
        await message.answer(
            "❌ Клиентов не найдено\n\n"
            "💡 Запись клиентов начнётся с первой записи в боте"
        )
        return

    # ── Сообщение: только последние 10 ───────────────────────────────────────
    preview = clients[-10:]

    export_text = (
        f"👥 Всего клиентов: {len(clients)}\n"
        f"{'─' * 30}\n"
        f"🕐 Последние {len(preview)}:\n\n"
    )

    for client in preview:
        export_text += (
            f"🔹 {client['first_name']} {client['last_name'] or ''}\n"
            f"   Telegram: {client['telegram_id']}\n"
            f"   Телефон: {client['phone'] or '—'}\n"
            f"   Записей: {client['total_appointments']}\n\n"
        )

    await message.answer(export_text)

    # ── CSV: все клиенты ──────────────────────────────────────────────────────
    try:
        import tempfile, os
        csv_content = AdminService.generate_clients_csv(clients)

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.csv', delete=False, encoding='utf-8-sig', newline=''
        ) as f:
            f.write(csv_content)
            csv_path = f.name

        await message.answer_document(
            document=FSInputFile(csv_path),
            caption=f"👥 Полный список клиентов · {len(clients)} чел."
        )
        os.remove(csv_path)
    except Exception as e:
        logger.error(f"Ошибка генерации CSV: {e}")
        await message.answer("⚠️ Не удалось сгенерировать CSV файл")

@router.message(Command("stats"))
async def show_statistics(message: types.Message) -> None:
    """Show appointment statistics."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    error = is_sandbox_restricted("📊 Выгрузка статистики")
    if error:
        await message.answer(error)
        return
    
    stats = await AdminService.get_statistics()
    
    stats_text = f"""
📊 ОБЩАЯ СТАТИСТИКА САЛОНА

 Всего записей: {stats['total_appointments']}
 Уникальных клиентов: {stats['total_unique_clients']}
 Общая выручка: {stats['total_revenue']} ₽
 Самая популярная услуга: {stats['top_service']}

 Статистика по всем временам
"/stats" - обновить данные
    """
    
    await message.answer(stats_text)


@router.message(Command("block_status"))
async def show_block_status(message: types.Message) -> None:
    """Show all blocked time slots."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    blocks = await AdminService.get_all_blocks()
    
    if not blocks:
        await message.answer(
            "✅ Нет активных блокировок\n\n"
            "💡 Все временные слоты доступны"
        )
        return
    
    export_text = f"🔒 Заблокированные слоты: {len(blocks)}\n\n"
    
    for block in blocks:
        export_text += f"📅 {block['date']} {block['time']}\n"
        export_text += f"   Причина: {block['reason']}\n\n"
    
    # Split into chunks if too long
    if len(export_text) > 4096:
        chunks = [export_text[i:i+4096] for i in range(0, len(export_text), 4096)]
        for chunk in chunks:
            await message.answer(chunk)
    else:
        await message.answer(export_text)


@router.message(Command("clear_block"))
async def clear_all_blocks(message: types.Message) -> None:
    """Clear all blocked time slots."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    count = await AdminService.clear_all_blocks()
    if count > 0:
        await message.answer(
            f"✅ **Все блокировки удалены!**\n\n"
            f"🗑️ Удалено слотов: {count}\n\n"
            f"💡 Все временные интервалы теперь доступны"
        )
    else:
        await message.answer(
            "✅ Нечего удалять\n\n"
            "💡 Активных блокировок нет"
        )


# ==================== TIMEZONE MANAGEMENT ====================

@router.message(Command("setup"))
async def setup_wizard_start(message: types.Message, state: FSMContext) -> None:
    """Start the setup wizard for initial admin configuration."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    await state.set_state(SetupWizardStates.step_timezone)
    await state.update_data(setup_step="timezone")
    
    current_offset = await AdminService.get_timezone_offset()
    
    await message.answer(
        "👋 <b>Добро пожаловать! Давайте настроим бота.</b>\n\n"
        "Это займёт пару минут. Каждый шаг можно пропустить.\n\n"
        "<b>Шаг 1 из 7 — Ваш часовой пояс</b>\n\n"
        "Введите ваш часовой пояс\n\n"
        "• <code>3</code> — Москва\n"
        "• <code>5</code> — Екатеринбург\n"
        "• <code>7</code> — Новосибирск\n"
        "• <code>10</code> — Владивосток\n\n"
        f"Сейчас: <b>UTC{current_offset:+d}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_timezone")]
        ]),
    )


@router.callback_query(SetupSkipTimezone.filter())
async def setup_skip_timezone(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Skip timezone step and go to schedule."""
    await state.set_state(SetupWizardStates.step_schedule_type)
    await state.update_data(setup_step="schedule_type")
    
    await callback_query.message.delete()
    await callback_query.message.answer(
        "<b>Шаг 2 из 7 — Тип графика</b>\n\n"
        "Как вы работаете?\n"
        "📅 Цикличный — два через два и другие\n"
        "📆 По дням недели — по определенным дням\n"
        "🆓 Свободный — все дни будут открыты",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Цикличный", callback_data="setup_schedule_type:cycle")],
            [InlineKeyboardButton(text="📆 По дням недели", callback_data="setup_schedule_type:weekdays")],
            [InlineKeyboardButton(text="🆓 Свободный", callback_data="setup_schedule_type:free")],
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_schedule_type")],
        ]),
    )
    
    await callback_query.answer()


@router.message(SetupWizardStates.step_timezone)
async def setup_process_timezone(message: types.Message, state: FSMContext) -> None:
    """Process timezone input in setup wizard."""
    offset_text = message.text.strip()
    
    try:
        offset = int(offset_text)
        
        # Validate range
        if not (-12 <= offset <= 14):
            await message.answer(
                "❌ Неверное значение (от -12 до +14)\n\n"
                "🔹 Примеры: <code>3</code>, <code>-5</code>, <code>10</code>",
                parse_mode="HTML"
            )
            return
        
        # Save timezone offset
        success = await AdminService.set_timezone_offset(offset)
        
        if success:
            await state.set_state(SetupWizardStates.step_schedule_type)
            await state.update_data(setup_step="schedule_type", timezone_offset=offset)
            
            await message.answer(
                f"✅ Часовой пояс установлен: <b>UTC{offset:+d}</b>\n\n"
                "<b>Шаг 2 из 7 — Тип графика</b>\n\n"
                "Как вы работаете?"
                "📅 Цикличный — два через два и другие\n"
                "📆 По дням недели — по определенным дням\n"
                "🆓 Свободный — все дни будут открыты\n",
                        parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📅 Цикличный", callback_data="setup_schedule_type:cycle")],
                    [InlineKeyboardButton(text="📆 По дням недели", callback_data="setup_schedule_type:weekdays")],
                    [InlineKeyboardButton(text="🆓 Свободный", callback_data="setup_schedule_type:free")],
                    [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_schedule_type")],
                ]),
            )
        else:
            await message.answer("❌ Ошибка при сохранении таймзоны. Попробуйте снова.")
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число\n\n"
            "Диапазон: от -12 до +14\n\n"
            "🔹 Примеры: <code>3</code>, <code>-5</code>, <code>10</code>",
            parse_mode="HTML"
        )


@router.callback_query(SetupScheduleType.filter())
async def setup_choose_schedule_type(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Process schedule type selection."""
    callback_data = callback_query.data or ""
    parts = callback_data.split(":", 1)
    schedule_type = parts[1] if len(parts) > 1 else ""

    if not schedule_type:
        await callback_query.answer("❌ Некорректный выбор. Повторите попытку.", show_alert=True)
        return

    await state.update_data(schedule_type=schedule_type)
    
    type_name = {
        "cycle": "Цикличный",
        "weekdays": "По дням недели",
        "free": "Свободный"
    }.get(schedule_type, schedule_type)
    
    await callback_query.message.delete()
    
    if schedule_type == "cycle":
        # For cycle mode, ask for pattern
        await state.set_state(SetupWizardStates.step_schedule_cycle_pattern)
        await callback_query.message.answer(
            "<b>Шаг 2 из 7 — Цикличный график</b>\n\n"
            "Сколько дней работаете и сколько отдыхаете?\n\n"
            "• <code>5/2</code> — 5 рабочих, 2 выходных\n"
            "• <code>6/1</code> — 6 рабочих, 1 выходной\n"
            "• <code>4/3</code> — 4 рабочих, 3 выходных\n\n"
            "Введите в формате <code>рабочих/выходных</code>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_schedule_type")]
            ]),
        )
    elif schedule_type == "weekdays":
        # For weekdays mode, ask for day selection
        await state.set_state(SetupWizardStates.step_schedule_weekdays)
        await state.update_data(selected_days={0, 1, 2, 3, 4})  # Default: Mon-Fri
        
        # Create custom weekday keyboard for setup
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        selected = {0, 1, 2, 3, 4}
        buttons = []
        
        # Days in rows
        for i in range(0, 7, 3):
            row = []
            for j in range(3):
                if i + j < 7:
                    day_idx = i + j
                    is_selected = day_idx in selected
                    row.append(InlineKeyboardButton(
                        text=f"{'✅' if is_selected else '❌'} {days[day_idx]}",
                        callback_data=f"setup_weekday:{day_idx}"
                    ))
            buttons.append(row)
        
        buttons.append([
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="setup_weekdays_confirm"),
            InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_schedule_type"),
        ])
        
        await callback_query.message.answer(
            f"✅ Выбран тип: <b>{type_name}</b>\n\n"
            "<b>Шаг 2 из 7 — Рабочие дни</b>\n\n"
            "Отметьте дни когда принимаете клиентов:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:  # free mode
        # For free mode, skip directly to hours
        await state.set_state(SetupWizardStates.step_schedule_hours)
        await callback_query.message.answer(
            "<b>Шаг 3 из 7 — Время работы</b>\n\n"
            "Введите время приёма клиентов:\n\n"
            "• <code>10:00-20:00</code>\n"
            "• <code>09:00-18:00</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_hours")]
            ]),
        )
    
    await callback_query.answer()


@router.message(SetupWizardStates.step_schedule_cycle_pattern)
async def setup_process_cycle_pattern(message: types.Message, state: FSMContext) -> None:
    """Process cycle pattern input (N/M)."""
    pattern_str = message.text.strip()
    
    # Validate format N/M
    if "/" not in pattern_str:
        await message.answer(
            "❌ Неверный формат\n\n"
            "Используйте: <b>N/M</b>\n\n"
            "<b>Примеры:</b>\n"
            "• <code>5/2</code> — 5 дней работы, 2 дня выходных\n"
            "• <code>6/1</code> — 6 дней работы, 1 день выходной",
            parse_mode="HTML"
        )
        return
    
    try:
        parts = pattern_str.split("/")
        work_days = int(parts[0])
        rest_days = int(parts[1])
        
        if work_days <= 0 or rest_days <= 0:
            raise ValueError("Оба числа должны быть больше нуля")
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат\n\n"
            "Введите две положительные цифры через слеш (например 5/2)",
        )
        return
    
    # Store pattern and ask for start date
    await state.update_data(cycle_pattern=pattern_str)
    await state.set_state(SetupWizardStates.step_schedule_cycle_date)
    
    today = datetime.now(get_tz_sync()).strftime("%d-%m-%Y")
    
    await message.answer(
        f"<b>Шаг 2 из 7 — Дата начала цикла</b>\n\n"
        f"С какого числа начинается первый рабочий день?\n\n"
        f"Введите дату в формате <code>ДД-MM-ГГГГ</code>\n"
        f"<i>Сегодня: {today}</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_schedule_type")]
        ]),
    )


@router.message(SetupWizardStates.step_schedule_cycle_date)
async def setup_process_cycle_date(message: types.Message, state: FSMContext) -> None:
    """Process cycle start date input."""
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
        await state.update_data(cycle_start_date=date_str)
        await state.set_state(SetupWizardStates.step_schedule_hours)
        await message.answer(
            f"<b>Шаг 3 из 7 — Рабочие часы</b>\n\n"
            f"Во сколько начинается и заканчивается рабочий день?\n\n"
            f"Введите время в формате <code>HH:MM-HH:MM</code>\n",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_hours")]
            ]),
        )
    else:
        await message.answer(
            f"⚠️ Ошибка: {msg}\n\n"
            f"Возможно, есть записи на выходные дни. "
            f"Введите другую дату или пропустите этот шаг.",
        )


@router.callback_query(SetupWeekday.filter(), SetupWizardStates.step_schedule_weekdays)
async def setup_toggle_weekday(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Toggle a weekday in setup."""
    day_idx = int(callback_query.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("selected_days", {0, 1, 2, 3, 4}))
    
    if day_idx in selected:
        selected.remove(day_idx)
    else:
        selected.add(day_idx)
    
    await state.update_data(selected_days=selected)
    
    from app.admin_bot.schedule_keyboards import weekday_keyboard

    await callback_query.message.edit_reply_markup(
        reply_markup=weekday_keyboard(
            selected,
            toggle_cb_name="setup_weekday",
            confirm_cb_name="setup_weekdays_confirm",
            cancel_cb_name="setup_skip_schedule_type",
        )
    )
    await callback_query.answer()


@router.callback_query(SetupWeekdaysConfirm.filter(), SetupWizardStates.step_schedule_weekdays)
async def setup_confirm_weekdays(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm weekdays selection and save."""
    data = await state.get_data()
    selected_days = sorted(data.get("selected_days", {0, 1, 2, 3, 4}))
    
    if not selected_days:
        await callback_query.answer("❌ Выберите хотя бы один день", show_alert=True)
        return
    
    # Store working days as numeric indices (CSV) for internal logic
    # and keep a human-readable representation for UI/state.
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    working_days_str = ",".join(str(i) for i in selected_days)
    working_days_display = ",".join(day_names[i] for i in selected_days)

    success = await AdminService.set_schedule_weekdays(working_days_str)

    if success:
        # save numeric CSV for logic and display string for UI
        await state.update_data(working_days=working_days_str, working_days_display=working_days_display)
        await state.set_state(SetupWizardStates.step_schedule_hours)
        
        await callback_query.message.delete()
        today = datetime.now(get_tz_sync()).strftime("%d-%m-%Y")
        await callback_query.message.answer(
            f"<b>Шаг 3 из 7 — Рабочие часы</b>\n\n"
            f"Во сколько начинается и заканчивается рабочий день?\n\n"
            f"Введите время в формате <code>HH:MM-HH:MM</code>\n",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_hours")]
            ]),
        )
        await callback_query.answer()
    else:
        await callback_query.answer("❌ Ошибка при сохранении", show_alert=True)



@router.callback_query(SetupSkipScheduleType.filter())
async def setup_skip_schedule_type(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Skip entire schedule setup and go to notification."""
    await state.set_state(SetupWizardStates.step_notification_time)
    await state.update_data(setup_step="notification")
    
    await callback_query.message.delete()
    await callback_query.message.answer(
        "<b>Шаг 6 из 7 — Уведомления о записях</b>\n\n"
        "В какое время присылать список записей на день?\n\n"
        "• <code>09:00</code>\n"
        "• <code>10:30</code>\n\n"
        "Приходит только в рабочие дни.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_notification")]
        ]),
    )
    
    await callback_query.answer()



@router.message(SetupWizardStates.step_schedule_hours)
async def setup_process_hours(message: types.Message, state: FSMContext) -> None:
    """Process work hours input."""
    hours_text = message.text.strip()
    
    # Validate format HH:MM-HH:MM
    if "-" not in hours_text or hours_text.count(":") != 2:
        await message.answer(
            "❌ Неверный формат\n\n"
            "Используйте: <b>HH:MM-HH:MM</b>\n\n"
            "<b>Примеры:</b>\n"
            "• <code>10:00-20:00</code>\n"
            "• <code>09:30-18:00</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        start_end = hours_text.split("-")
        start_time = start_end[0].strip()
        end_time = start_end[1].strip()
        
        # Validate time format
        start_h, start_m = map(int, start_time.split(":"))
        end_h, end_m = map(int, end_time.split(":"))
        
        if not (0 <= start_h <= 23 and 0 <= start_m <= 59 and 0 <= end_h <= 23 and 0 <= end_m <= 59):
            raise ValueError("Invalid time range")
        
        if start_h * 60 + start_m >= end_h * 60 + end_m:
            await message.answer(
                "❌ Время начала должно быть раньше времени окончания\n\n"
                "<b>Пример правильного ввода:</b>\n"
                "<code>10:00-20:00</code>",
                parse_mode="HTML"
            )
            return
        
        # Save hours
        await AdminService.set_schedule_setting("start_time", start_time)
        await AdminService.set_schedule_setting("end_time", end_time)
        
        await state.set_state(SetupWizardStates.step_schedule_breaks)
        await state.update_data(setup_step="breaks", start_time=start_time, end_time=end_time)
        
        await message.answer(
            "<b>Шаг 4 из 7 — Перерыв</b>\n\n"
            "Есть ли перерыв в течение дня?\n\n"
            "• <code>13:00-14:00</code>\n"
            "• <code>12:30-13:00</code>\n"
            "Нажмите пропустить, если перерыва нет.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_breaks")]
            ]),
        )
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат времени\n\n"
            "Используйте: <b>HH:MM-HH:MM</b>\n\n"
            "<b>Примеры:</b>\n"
            "• <code>10:00-20:00</code>\n"
            "• <code>09:30-18:00</code>",
            parse_mode="HTML"
        )


@router.callback_query(SetupSkipHours.filter())
async def setup_skip_hours(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Skip hours step and go to breaks."""
    await state.set_state(SetupWizardStates.step_schedule_breaks)
    await state.update_data(setup_step="breaks")
    
    await callback_query.message.delete()
    await callback_query.message.answer(
            "<b>Шаг 4 из 7 — Перерыв</b>\n\n"
            "Есть ли перерыв в течение дня?\n\n"
            "• <code>13:00-14:00</code>\n"
            "• <code>12:30-13:00</code>\n"
            "Нажмите пропустить, если перерыва нет.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_breaks")]
        ]),
    )
    
    await callback_query.answer()



@router.message(SetupWizardStates.step_schedule_breaks)
async def setup_process_breaks(message: types.Message, state: FSMContext) -> None:
    """Process break times input."""
    breaks_text = message.text.strip()
    
    # Validate format HH:MM-HH:MM
    if "-" not in breaks_text or breaks_text.count(":") != 2:
        await message.answer(
            "❌ Неверный формат\n\n"
            "Используйте: <b>HH:MM-HH:MM</b>\n\n"
            "<b>Примеры:</b>\n"
            "• <code>13:00-14:00</code>\n"
            "• <code>12:00-12:30</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        start_end = breaks_text.split("-")
        break_start = start_end[0].strip()
        break_end = start_end[1].strip()
        
        # Validate time format
        break_h, break_m = map(int, break_start.split(":"))
        break_e_h, break_e_m = map(int, break_end.split(":"))
        
        if not (0 <= break_h <= 23 and 0 <= break_m <= 59 and 0 <= break_e_h <= 23 and 0 <= break_e_m <= 59):
            raise ValueError("Invalid time range")
        
        if break_h * 60 + break_m >= break_e_h * 60 + break_e_m:
            await message.answer(
                "❌ Время начала перерыва должно быть раньше времени окончания\n\n"
                "<b>Пример правильного ввода:</b>\n"
                "<code>13:00-14:00</code>",
                parse_mode="HTML"
            )
            return
        
        # Save breaks
        await AdminService.set_schedule_setting("break_start", break_start)
        await AdminService.set_schedule_setting("break_end", break_end)
        
        await state.set_state(SetupWizardStates.step_schedule_interval)
        await state.update_data(setup_step="interval", break_start=break_start, break_end=break_end)
        
        await message.answer(
            "<b>Шаг 5 из 7 — Интервал записи</b>\n\n"
            "Через какой промежуток времени можно записаться?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏱️ 15 минут", callback_data="setup_interval:15")],
                [InlineKeyboardButton(text="⏱️ 30 минут", callback_data="setup_interval:30")],
                [InlineKeyboardButton(text="⏱️ 45 минут", callback_data="setup_interval:45")],
                [InlineKeyboardButton(text="⏱️ 60 минут", callback_data="setup_interval:60")],
                [InlineKeyboardButton(text="Другое", callback_data="setup_interval:custom")],
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_interval")],
            ]),
        )
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат времени\n\n"
            "Используйте: <b>HH:MM-HH:MM</b>\n\n"
            "<b>Примеры:</b>\n"
            "• <code>13:00-14:00</code>\n"
            "• <code>12:00-12:30</code>",
            parse_mode="HTML"
        )


@router.callback_query(SetupSkipBreaks.filter())
async def setup_skip_breaks(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Skip breaks step and go to interval."""
    await state.set_state(SetupWizardStates.step_schedule_interval)
    await state.update_data(setup_step="interval")
    
    await callback_query.message.delete()
    await callback_query.message.answer(
            "<b>Шаг 5 из 7 — Интервал записи</b>\n\n"
            "Через какой промежуток времени можно записаться?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏱️ 15 минут", callback_data="setup_interval:15")],
            [InlineKeyboardButton(text="⏱️ 30 минут", callback_data="setup_interval:30")],
            [InlineKeyboardButton(text="⏱️ 45 минут", callback_data="setup_interval:45")],
            [InlineKeyboardButton(text="⏱️ 60 минут", callback_data="setup_interval:60")],
            [InlineKeyboardButton(text="Другое", callback_data="setup_interval:custom")],
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_interval")],
        ]),
    )
    
    await callback_query.answer()


@router.callback_query(SetupInterval.filter())
async def setup_choose_interval(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Process interval selection."""
    callback_data = callback_query.data or ""
    data_part = callback_data.split(":", 1)[1] if ":" in callback_data else ""
    
    if data_part in ("custom", "0"):
        await callback_query.message.edit_text(
            "⏱️ <b>Введите интервал в минутах</b>\n\n"
            "Укажите целое число больше 0 (например, 10, 20, 25):\n\n"
            "<i>Минимальный интервал: 5 минут</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀ Назад", callback_data="setup_back_to_interval")
            ]])
        )
        await state.set_state(SetupWizardStates.step_custom_interval)
        await callback_query.answer()
        return
    
    interval = int(data_part)
    
    await AdminService.set_schedule_setting("interval_minutes", str(interval))
    
    await state.set_state(SetupWizardStates.step_notification_time)
    await state.update_data(setup_step="notification", interval_minutes=interval)
    
    await callback_query.message.delete()
    await callback_query.message.answer(
        "<b>Шаг 6 из 7 — Уведомления о записях</b>\n\n"
        "В какое время присылать список записей на день?\n\n"
        "• <code>09:00</code>\n"
        "• <code>10:30</code>\n\n"
        "Приходит только в рабочие дни.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_notification")]
        ]),
    )
    
    await callback_query.answer()


@router.callback_query(SetupBackToInterval.filter())
async def setup_back_to_interval(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Back to interval selection in setup wizard."""
    await state.set_state(SetupWizardStates.step_schedule_interval)
    await callback_query.message.edit_text(
        "<b>Шаг 5 из 7 — Интервал записи</b>\n\n"
        "Через какой промежуток времени можно записаться?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏱️ 15 минут", callback_data="setup_interval:15")],
            [InlineKeyboardButton(text="⏱️ 30 минут", callback_data="setup_interval:30")],
            [InlineKeyboardButton(text="⏱️ 45 минут", callback_data="setup_interval:45")],
            [InlineKeyboardButton(text="⏱️ 60 минут", callback_data="setup_interval:60")],
            [InlineKeyboardButton(text="Другое", callback_data="setup_interval:custom")],
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_interval")],
        ]),
    )
    await callback_query.answer()


@router.message(SetupWizardStates.step_custom_interval)
async def setup_process_custom_interval(message: types.Message, state: FSMContext) -> None:
    """Process custom interval input in setup wizard."""
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
    
    await AdminService.set_schedule_setting("interval_minutes", str(interval))
    
    await state.set_state(SetupWizardStates.step_notification_time)
    await state.update_data(setup_step="notification", interval_minutes=str(interval))
    
    await message.answer(
        "<b>Шаг 6 из 7 — Уведомления о записях</b>\n\n"
        "В какое время присылать список записей на день?\n\n"
        "• <code>09:00</code>\n"
        "• <code>10:30</code>\n\n"
        "Приходит только в рабочие дни.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_notification")]
        ]),
    )


@router.callback_query(SetupSkipInterval.filter())
async def setup_skip_interval(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Skip interval step and go to notification."""
    await state.set_state(SetupWizardStates.step_notification_time)
    await state.update_data(setup_step="notification")
    
    await callback_query.message.delete()
    await callback_query.message.answer(
        "⏭️ <b>Размер окна пропущен, стандартный - 30 минут</b>\n\n"
        "<b>Шаг 6 из 7 — Уведомления о записях</b>\n\n"
        "В какое время присылать список записей на день?\n\n"
        "• <code>09:00</code>\n"
        "• <code>10:30</code>\n\n"
        "Приходит только в рабочие дни.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_notification")]
        ]),
    )
    
    await callback_query.answer()


@router.message(SetupWizardStates.step_notification_time)
async def setup_process_notification_time(message: types.Message, state: FSMContext) -> None:
    """Process notification time input."""
    time_text = message.text.strip()
    
    # Validate time format
    if not time_text or len(time_text) != 5 or time_text[2] != ':':
        await message.answer(
            "❌ Неверный формат времени\n\n"
            "Используйте: <b>HH:MM</b>\n\n"
            "<b>Примеры:</b>\n"
            "• <code>09:00</code>\n"
            "• <code>10:30</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        hours, minutes = time_text.split(':')
        hour = int(hours)
        minute = int(minutes)
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Неверный диапазон времени")
        
        # Save notification time
        await AdminService.set_admin_notification_time(message.from_user.id, time_text)
        
        await state.set_state(SetupWizardStates.step_contacts)
        await state.update_data(notification_time=time_text)
        
        await message.answer(
            "<b>Шаг 7 из 7 — Контакты</b>\n\n"
            "Введите контактную информацию — клиенты будут её видеть.\n\n"
            "Пример:\n"
            "Мария, мастер маникюра\n"
            "📱 +7 900 000-00-00\n"
            "📍 Москва, ул. Примерная 1\n"
            "📸 @maria_nails",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_contacts")]
            ]),
        )
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат времени\n\n"
            "Используйте: <b>HH:MM</b>\n\n"
            "<b>Примеры:</b>\n"
            "• <code>09:00</code>\n"
            "• <code>10:30</code>",
            parse_mode="HTML"
        )


@router.callback_query(SetupSkipNotification.filter())
async def setup_skip_notification(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Skip notification time and go to contacts."""
    await state.set_state(SetupWizardStates.step_contacts)
    await state.update_data(setup_step="contacts")
    
    await callback_query.message.delete()
    await callback_query.message.answer(
        "<b>Шаг 7 из 7 — Контакты</b>\n\n"
        "Введите контактную информацию — клиенты будут её видеть.\n\n"
        "Пример:\n"
        "Мария, мастер маникюра\n"
        "📱 +7 900 000-00-00\n"
        "📍 Москва, ул. Примерная 1\n"
        "📸 @maria_nails",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="setup_skip_contacts")]
        ]),
    )
    
    await callback_query.answer()


@router.message(SetupWizardStates.step_contacts)
async def setup_process_contacts(message: types.Message, state: FSMContext) -> None:
    """Process contacts input."""
    contacts_text = message.text.strip()
    
    if not contacts_text:
        await message.answer("❌ Контакты не могут быть пустыми")
        return
    
    # Save contacts
    await AdminService.update_salon_sandbox_contacts(contacts_text)
    
    # Finish setup
    await state.clear()
    
    await message.answer(
        "✅ <b>Первичная настройка завершена!</b>\n"
        "⚠️ После изменения важных параметров используйте /reload\n"
        "Вы можете в любой момент изменить эти настройки через соответствующие команды:\n"
        "• /timezone — изменить таймзону\n"
        "• /schedule — изменить график\n"
        "• /contacts — изменить контакты\n\n"
        "Нажмите кнопку <b>⚙️ Прайс</b> для настройки услуг",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_menu")]
        ]),
    )


@router.callback_query(SetupSkipContacts.filter())
async def setup_skip_contacts(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Skip contacts step and finish setup."""
    await state.clear()
    
    await callback_query.message.delete()
    await callback_query.message.answer(
        "✅ <b>Первичная настройка завершена!</b>\n\n"
        "⚠️ После изменения важных параметров используйте /reload\n"

        "Вы можете в любой момент изменить эти настройки через соответствующие команды:\n"
        "• /timezone — изменить часовой пояс\n"
        "• /schedule — изменить график\n"
        "• /contacts — изменить контакты\n\n"
        "Нажмите кнопку <b>⚙️ Прайс</b> для настройки услуг",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_menu")]
        ]),
    )
    
    await callback_query.answer()


@router.message(Command("timezone"))
async def timezone_command(message: types.Message, state: FSMContext) -> None:
    """Set timezone offset for the entire system."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    # Get current timezone
    current_offset = await AdminService.get_timezone_offset()
    
    await state.set_state(TimezoneStates.set_offset)
    await message.answer(
        "Введите часовой пояс:\n\n"
        "• <code>3</code> — Москва\n"
        "• <code>5</code> — Екатеринбург\n"
        "• <code>7</code> — Новосибирск\n"
        "• <code>10</code> — Владивосток\n\n"
        f"Сейчас: <b>UTC{current_offset:+d}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="timezone_cancel")]
        ]),
    )


@router.callback_query(TimezoneCancel.filter())
async def timezone_cancel(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel timezone setting."""
    await state.clear()
    await callback_query.message.edit_text("❌ Отменено")
    await callback_query.answer()


@router.message(TimezoneStates.set_offset)
async def process_timezone_offset(message: types.Message, state: FSMContext) -> None:
    """Process timezone offset input."""
    offset_text = message.text.strip()
    
    try:
        offset = int(offset_text)
        
        # Validate range
        if not (-12 <= offset <= 14):
            await message.answer(
                "❌ Неверное значение\n\n"
                "Диапазон смещения: от -12 до +14\n\n"
                "🔹 Примеры:\n"
                "• <code>3</code> — UTC+3\n"
                "• <code>-5</code> — UTC-5",
                parse_mode="HTML"
            )
            return
        
        # Save timezone offset
        success = await AdminService.set_timezone_offset(offset)
        
        if success:
            await state.clear()
            await message.answer(
                f"✅ <b>Таймзона установлена: UTC{offset:+d}</b>\n\n"
                "⏰ Все расчёты времени в системе теперь используют новое смещение.\n\n"
                "Для переподключения бота требуется перезагрузка. /reload",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "❌ Ошибка при сохранении таймзоны.\n"
                "Попробуйте снова."
            )
    except ValueError:
        await message.answer(
            "❌ Неверный формат\n\n"
            "Введите число от -12 до +14\n\n"
            "🔹 Примеры:\n"
            "• <code>3</code> — UTC+3\n"
            "• <code>-5</code> — UTC-5",
            parse_mode="HTML"
        )


# ==================== BOT MANAGEMENT ====================

@router.message(Command("reload"))
async def reload_command(message: types.Message, state: FSMContext) -> None:
    """Reload bot to apply new settings."""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    
    await state.set_state(ReloadStates.confirm_reload)
    await message.answer(
        "⚠️ <b>Перезагрузка бота</b>\n\n"
        "Это применит все новые настройки (таймзона, время работы и т.д.)\n\n"
        "Процесс займет несколько секунд.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Перезагрузить", callback_data="reload_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="reload_cancel")]
        ]),
    )


@router.callback_query(ReloadCancel.filter(), ReloadStates.confirm_reload)
async def reload_cancel(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel reload."""
    await state.clear()
    await callback_query.message.edit_text("❌ Перезагрузка отменена")
    await callback_query.answer()


@router.callback_query(ReloadConfirm.filter(), ReloadStates.confirm_reload)
async def reload_confirm(callback_query: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm and execute reload."""
    from app.config import RESTART_DELAY
    
    try:
        await callback_query.message.edit_text(
            "⏳ Перезагрузка...\n\n"
            "Бот перезагружается. Подождите 5-10 секунд.",
            parse_mode="HTML"
        )
        await callback_query.answer()
    except Exception:
        pass
    
    # Graceful shutdown and restart
    await state.clear()
    logger.info(f"Bot reload initiated by admin {callback_query.from_user.id}")
    
    # Give time for message to be sent
    await asyncio.sleep(RESTART_DELAY)
    
    # Exit with code 1 - Docker/systemd will restart automatically
    os._exit(1)

# Include schedule router
from app.admin_bot.schedule_handlers import schedule_router
router.include_router(schedule_router)

