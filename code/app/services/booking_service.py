from datetime import datetime, timedelta
import logging
import re

from ..database import get_connection
from ..config import get_tz_sync
from ..date_utils import normalize_date_to_iso
from ..models.schemas import ScheduleSettings

logger = logging.getLogger(__name__)

class BookingService:
    @staticmethod
    async def get_or_create_client(telegram_id: int, first_name: str | None, last_name: str | None) -> int:
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT id FROM clients WHERE telegram_id = ?",
                    (telegram_id,),
                )
                row = await cursor.fetchone()
                if row:
                    return row[0]
                await cursor.execute(
                    "INSERT INTO clients (telegram_id, first_name, last_name) VALUES (?, ?, ?)",
                    (telegram_id, first_name, last_name),
                )
                await connection.commit()
                return cursor.lastrowid

    @staticmethod
    async def get_client(telegram_id: int) -> dict | None:
        """Get client info by telegram_id."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT id, telegram_id, first_name, last_name, phone FROM clients WHERE telegram_id = ?",
                    (telegram_id,),
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "telegram_id": row[1],
                        "first_name": row[2],
                        "last_name": row[3],
                        "phone": row[4],
                    }
        return None

    @staticmethod
    async def create_appointment(
        client_id: int,
        service_id: int,
        appointment_date: str,
        appointment_time: str,
        note: str | None = None,
    ) -> int:
        appointment_date = normalize_date_to_iso(appointment_date)
        created_at = datetime.now(get_tz_sync()).isoformat()
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Get service duration at time of booking
                await cursor.execute("SELECT duration FROM services WHERE id = ?", (service_id,))
                service_row = await cursor.fetchone()
                service_duration = service_row[0] if service_row else 30
                
                await cursor.execute(
                    "INSERT INTO appointments (client_id, service_id, appointment_date, appointment_time, note, created_at, service_duration_minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (client_id, service_id, appointment_date, appointment_time, note, created_at, service_duration),
                )
                await connection.commit()
                return cursor.lastrowid

    @staticmethod
    async def list_client_appointments(telegram_id: int) -> list[dict]:
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT a.id, s.name, a.appointment_date, a.appointment_time, a.status, a.note "
                    "FROM appointments a "
                    "JOIN clients c ON c.id = a.client_id "
                    "JOIN services s ON s.id = a.service_id "
                    "WHERE c.telegram_id = ? AND a.status = 'planned' "
                    "ORDER BY a.appointment_date, a.appointment_time",
                    (telegram_id,),
                )
                rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "service_name": row[1],
                "date": row[2],
                "time": row[3],
                "status": row[4],
                "note": row[5],
            }
            for row in rows
        ]

    @staticmethod
    async def get_schedule_settings() -> ScheduleSettings:
        """Get schedule settings from database."""
        settings_dict = {
            "mode": "cycle",
            "cycle_pattern": "5/2",
            "cycle_start_date": "2026-04-20",
            "interval_minutes": 30,
            "break_start": None,
            "break_end": None,
            "start_time": "10:00",
            "end_time": "20:00",
        }
        
        # Only these keys are valid for ScheduleSettings dataclass
        valid_keys = {"mode", "cycle_pattern", "cycle_start_date", "working_days", "interval_minutes", "break_start", "break_end", "start_time", "end_time"}
        
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT key, value FROM schedule_settings")
                    rows = await cursor.fetchall()
                    for key, value in rows:
                        # Only process valid keys (ignore admin_notification_time_* and other dynamic keys)
                        if key not in valid_keys:
                            continue
                        if key == "interval_minutes":
                            settings_dict[key] = int(value)
                        elif key == "cycle_start_date" and value:
                            try:
                                settings_dict[key] = normalize_date_to_iso(value)
                            except ValueError:
                                logger.warning("Invalid cycle_start_date in schedule_settings: %s", value)
                        elif key == "working_days":
                            # Normalize working_days: accept numeric CSV or weekday names like "Пн,Вт"
                            if not value:
                                settings_dict[key] = None
                                continue
                            tokens = [t.strip() for t in re.split(r"[,;\\s]+", value) if t.strip()]
                            name_map = {"пн": "0", "вт": "1", "ср": "2", "чт": "3", "пт": "4", "сб": "5", "вс": "6"}
                            normalized = []
                            for t in tokens:
                                try:
                                    normalized.append(str(int(t)))
                                except Exception:
                                    mapped = name_map.get(t.lower())
                                    if mapped is not None:
                                        normalized.append(mapped)
                                    else:
                                        logger.warning("Unknown weekday token in schedule_settings: %s", t)
                            settings_dict[key] = ",".join(normalized) if normalized else None
                        else:
                            settings_dict[key] = value
        except Exception as e:
            logger.error(f"Error loading schedule settings: {e}")
        
        return ScheduleSettings(**settings_dict)

    @staticmethod
    async def is_work_day(appointment_date: str) -> bool:
        """Check if a given date is a work day based on schedule settings and exceptions."""
        try:
            appointment_date = normalize_date_to_iso(appointment_date)
        except ValueError as e:
            logger.error(f"Error checking if work day: {e}")
            return True

        settings = await BookingService.get_schedule_settings()
        
        # First check work_days table for exceptions
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT is_working FROM work_days WHERE work_date = ?",
                    (appointment_date,),
                )
                exception = await cursor.fetchone()
        
        if exception:
            return bool(exception[0])  # Use the exception override
        
        if settings.mode == "free":
            return True
        
        try:
            current = datetime.strptime(appointment_date, "%Y-%m-%d")
            weekday = current.weekday()  # 0=Mon, 6=Sun
            
            if settings.mode == "weekdays":
                # Check if this weekday is in working days
                working_list = [int(x) for x in settings.working_days.split(',')] if settings.working_days else []
                return weekday in working_list
            
            # Mode: "cycle"
            if not settings.cycle_pattern or not settings.cycle_start_date:
                return False
            
            pattern_parts = settings.cycle_pattern.split('/')
            work_days = int(pattern_parts[0])
            cycle_length = int(pattern_parts[0]) + int(pattern_parts[1])
            
            cycle_start_date = normalize_date_to_iso(settings.cycle_start_date)
            start = datetime.strptime(cycle_start_date, "%Y-%m-%d")
            days_since_start = (current - start).days
            
            if days_since_start < 0:
                return False
            
            position = days_since_start % cycle_length
            return position < work_days
        except Exception as e:
            logger.error(f"Error checking if work day: {e}")
            return True  # Default to work day on error

    @staticmethod
    async def get_available_times(appointment_date: str, service_id: int, exclude_appointment_id: int = None) -> list[str]:
        """Get available time slots for given date and service."""
        # Validate inputs
        if service_id is None or service_id <= 0:
            logger.error(f"Invalid service_id: {service_id} (type: {type(service_id).__name__})")
            raise ValueError(f"service_id must be a positive integer, got: {service_id}")
        
        if not appointment_date:
            logger.error(f"Invalid appointment_date: {appointment_date}")
            raise ValueError(f"appointment_date must not be empty, got: {appointment_date}")

        appointment_date = normalize_date_to_iso(appointment_date)
        
        logger.debug(f"get_available_times: date={appointment_date}, service_id={service_id}, exclude_apt_id={exclude_appointment_id}")
        
        # Get schedule settings for start and end times
        settings = await BookingService.get_schedule_settings()
        start_hour, start_min = map(int, settings.start_time.split(":"))
        end_hour, end_min = map(int, settings.end_time.split(":"))
        interval = settings.interval_minutes
        
        # Generate all possible time slots based on settings
        all_times = []
        current = datetime.strptime(f"{start_hour:02d}:{start_min:02d}", "%H:%M")
        end = datetime.strptime(f"{end_hour:02d}:{end_min:02d}", "%H:%M")
        
        while current <= end:
            all_times.append(current.strftime("%H:%M"))
            current += timedelta(minutes=interval)
        
        # Get service duration
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Check if it's a work day
                if not await BookingService.is_work_day(appointment_date):
                    return []
                
                # For today, filter out passed times
                from datetime import datetime as dt
                date_obj = dt.strptime(appointment_date, "%Y-%m-%d").date()
                today = datetime.now(get_tz_sync()).date()
                current_time = datetime.now(get_tz_sync()).time()
                if date_obj == today:
                    # Remove times that have already passed today
                    all_times = [t for t in all_times if t > current_time.strftime("%H:%M")]
                
                # Get service duration
                await cursor.execute("SELECT duration FROM services WHERE id = ?", (service_id,))
                row = await cursor.fetchone()
                if not row:
                    logger.error(f"Service not found: service_id={service_id}")
                    return []
                service_duration = row[0]  # in minutes
                logger.debug(f"Service {service_id} duration: {service_duration} min")
                
                # Get all booked appointments for this date (excluding the appointment being rescheduled)
                if exclude_appointment_id:
                    await cursor.execute(
                        "SELECT a.appointment_time, s.duration FROM appointments a "
                        "JOIN services s ON s.id = a.service_id "
                        "WHERE a.appointment_date = ? AND a.status = 'planned' AND a.id != ?",
                        (appointment_date, exclude_appointment_id),
                    )
                else:
                    await cursor.execute(
                        "SELECT a.appointment_time, s.duration FROM appointments a "
                        "JOIN services s ON s.id = a.service_id "
                        "WHERE a.appointment_date = ? AND a.status = 'planned'",
                        (appointment_date,),
                    )
                booked = await cursor.fetchall()
                
                # Get blocked time slots
                await cursor.execute(
                    "SELECT slot_time FROM unavailable_slots WHERE slot_date = ?",
                    (appointment_date,),
                )
                blocked = await cursor.fetchall()
        
        blocked_times = {row[0] for row in blocked}
        
        # Parse break times as datetime objects for range checking
        break_start_dt = None
        break_end_dt = None
        if settings.break_start and settings.break_end:
            break_start_dt = datetime.strptime(settings.break_start, "%H:%M")
            break_end_dt = datetime.strptime(settings.break_end, "%H:%M")
        
        # Calculate occupied time ranges
        occupied_ranges = set()
        for booked_time, duration in booked:
            start_dt = datetime.strptime(f"{appointment_date} {booked_time}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(minutes=duration)
            
            # Mark all overlapping slots as occupied
            current = start_dt
            while current < end_dt:
                occupied_ranges.add(current.strftime("%H:%M"))
                current += timedelta(minutes=interval)
        
        # Filter available times
        available = []
        end_time_dt = datetime.strptime(settings.end_time, "%H:%M")
        for time_slot in all_times:
            if time_slot not in blocked_times and time_slot not in occupied_ranges:
                # Check if the entire duration fits
                slot_dt = datetime.strptime(f"{appointment_date} {time_slot}", "%Y-%m-%d %H:%M")
                end_dt = slot_dt + timedelta(minutes=service_duration)
                
                # Make sure it doesn't go past end_time
                if end_dt.time() > end_time_dt.time():
                    continue
                
                # Check if any time during service duration overlaps with break
                conflict = False
                if break_start_dt and break_end_dt:
                    # Convert break times to datetime for comparison
                    break_start_full = datetime.strptime(f"{appointment_date} {break_start_dt.strftime('%H:%M')}", "%Y-%m-%d %H:%M")
                    break_end_full = datetime.strptime(f"{appointment_date} {break_end_dt.strftime('%H:%M')}", "%Y-%m-%d %H:%M")
                    
                    # Check if appointment overlaps with break
                    if slot_dt < break_end_full and end_dt > break_start_full:
                        conflict = True
                
                # Check if any slot in the duration is blocked or occupied
                if not conflict:
                    current = slot_dt
                    while current < end_dt:
                        current_time_str = current.strftime("%H:%M")
                        if current_time_str in blocked_times or current_time_str in occupied_ranges:
                            conflict = True
                            break
                        current += timedelta(minutes=interval)
                
                if not conflict:
                    available.append(time_slot)
        
        logger.debug(f"Available times for {appointment_date}: {available}")
        return available
    
    @staticmethod
    async def block_time_slot(appointment_date: str, appointment_time: str, reason: str = "Заблокировано администратором") -> None:
        """Block a time slot for the entire service duration."""
        appointment_date = normalize_date_to_iso(appointment_date)
        created_at = datetime.now(get_tz_sync()).isoformat()
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "INSERT OR REPLACE INTO unavailable_slots (slot_date, slot_time, reason, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (appointment_date, appointment_time, reason, created_at),
                )
                await connection.commit()
    
    @staticmethod
    async def unblock_time_slot(appointment_date: str, appointment_time: str) -> None:
        """Unblock a time slot."""
        appointment_date = normalize_date_to_iso(appointment_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM unavailable_slots WHERE slot_date = ? AND slot_time = ?",
                    (appointment_date, appointment_time),
                )
                await connection.commit()
    
    @staticmethod
    async def cancel_appointment(appointment_id: int) -> bool:
        """Cancel an appointment."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE appointments SET status = ? WHERE id = ?",
                    ("cancelled", appointment_id),
                )
                await connection.commit()
        return True
    
    @staticmethod
    async def move_appointment(appointment_id: int, new_date: str, new_time: str) -> bool:
        """Move an appointment to a new date/time."""
        new_date = normalize_date_to_iso(new_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE appointments SET appointment_date = ?, appointment_time = ? WHERE id = ?",
                    (new_date, new_time, appointment_id),
                )
                await connection.commit()
        return True

    @staticmethod
    async def has_feedback(appointment_id: int) -> bool:
        """Check if feedback exists for an appointment."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT id FROM feedback WHERE appointment_id = ?",
                    (appointment_id,),
                )
                return bool(await cursor.fetchone())
