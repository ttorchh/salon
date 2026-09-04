from datetime import datetime, timedelta
from calendar import monthcalendar, monthrange

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData
from app.config import get_tz_sync


class CalendarAction(CallbackData, prefix="calendar"):
    year: int
    month: int


class CalendarDate(CallbackData, prefix="calendar_date"):
    date: str


class TimeSelect(CallbackData, prefix="time"):
    time: str


def calendar_keyboard(year: int, month: int, blocked_dates: set = None) -> InlineKeyboardMarkup:
    """Generate calendar keyboard for given month.
    
    Args:
        year: Year of calendar
        month: Month of calendar
        blocked_dates: Set of blocked date strings (YYYY-MM-DD format).
                      If not provided, will use default hardcoded weekends logic.
    """
    if blocked_dates is None:
        blocked_dates = set()
    
    # Days of week header
    days_of_week = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    buttons = [[InlineKeyboardButton(text=day, callback_data="noop") for day in days_of_week]]
    
    cal = monthcalendar(year, month)
    month_name = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ][month - 1]
    
    # Calendar days
    for week in cal:
        week_buttons = []
        for day in week:
            if day == 0:
                # Empty day
                week_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            else:
                # Check if it's today or in the past
                today = datetime.now(get_tz_sync()).date()
                current_date = datetime(year, month, day, tzinfo=get_tz_sync()).date()
                date_str = f"{year}-{month:02d}-{day:02d}"
                
                if current_date < today:
                    # Past days are disabled (show with —)
                    week_buttons.append(InlineKeyboardButton(text="—", callback_data="noop"))
                elif date_str in blocked_dates:
                    # Blocked/unavailable days (check provided set first)
                    week_buttons.append(InlineKeyboardButton(text="—", callback_data="noop"))
                else:
                    # Available days
                    week_buttons.append(InlineKeyboardButton(
                        text=str(day),
                        callback_data=CalendarDate(date=date_str).pack()
                    ))
        buttons.append(week_buttons)
    
    # Navigation buttons
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    nav_buttons = [
        InlineKeyboardButton(text="◀", callback_data=CalendarAction(year=prev_year, month=prev_month).pack()),
        InlineKeyboardButton(text=f"{month_name} {year}", callback_data="noop"),
        InlineKeyboardButton(text="▶", callback_data=CalendarAction(year=next_year, month=next_month).pack()),
    ]
    buttons.append(nav_buttons)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_calendar_with_blocked_dates(year: int, month: int) -> InlineKeyboardMarkup:
    """Get calendar keyboard with blocked dates marked."""
    from app.services.admin_service import AdminService
    from app.services.booking_service import BookingService
    from app.database import get_connection
    from datetime import datetime
    
    # Get all blocked slots for entire month by fetching directly from DB
    blocked_dates = set()
    
    async with get_connection() as connection:
        async with connection.cursor() as cursor:
            # Get all blocked slots for the month where reason is "День заблокирован"
            await cursor.execute(
                """
                SELECT DISTINCT slot_date 
                FROM unavailable_slots 
                WHERE slot_date LIKE ? AND reason = ?
                """,
                (f"{year}-{month:02d}-%", "День заблокирован")
            )
            rows = await cursor.fetchall()
    
    for row in rows:
        blocked_dates.add(row[0])
    
    # Also mark non-work days as blocked
    import calendar as cal
    for day in range(1, cal.monthrange(year, month)[1] + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        is_work = await BookingService.is_work_day(date_str)
        if not is_work:
            blocked_dates.add(date_str)
    
    return calendar_keyboard(year, month, blocked_dates)


def time_selection_keyboard(available_times: list[str]) -> InlineKeyboardMarkup:
    """Generate time selection keyboard based on schedule settings."""
    buttons = []
    
    if not available_times:
        available_times = []
    
    # The available_times list already contains the correct times based on schedule settings
    # (generated by BookingService.get_available_times which uses start_time, end_time, interval_minutes)
    # So we just need to display them
    
    # Create button grid (3 columns)
    for i in range(0, len(available_times), 3):
        row = []
        for j in range(3):
            if i + j < len(available_times):
                time_str = available_times[i + j]
                row.append(InlineKeyboardButton(
                    text=time_str,
                    callback_data=TimeSelect(time=time_str.replace(':', '.')).pack()
                ))
        if row:
            buttons.append(row)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
