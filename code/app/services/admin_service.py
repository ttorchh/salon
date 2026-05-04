from datetime import datetime, timedelta
import re

from ..database import get_connection
from ..config import get_tz_sync
from ..date_utils import format_date_for_display, normalize_date_to_iso

class AdminService:
    @staticmethod
    async def list_appointments_for_day(target_date: str) -> list[dict]:
        target_date = normalize_date_to_iso(target_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT a.id, c.telegram_id, c.first_name, c.phone, s.name, a.appointment_date, a.appointment_time, a.status, a.note "
                    "FROM appointments a "
                    "LEFT JOIN clients c ON c.id = a.client_id "
                    "LEFT JOIN services s ON s.id = a.service_id "
                    "WHERE a.appointment_date = ? "
                    "ORDER BY a.appointment_time",
                    (target_date,),
                )
                rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "telegram_id": row[1],
                "client_name": row[2],
                "phone": row[3],
                "service_name": row[4],
                "date": row[5],
                "time": row[6],
                "status": row[7],
                "note": row[8],
            }
            for row in rows
        ]

    @staticmethod
    async def list_appointments_for_week(start_date: str) -> list[dict]:
        start_date = normalize_date_to_iso(start_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                end_date = (datetime.fromisoformat(start_date) + timedelta(days=6)).date().isoformat()
                await cursor.execute(
                    "SELECT a.id, c.telegram_id, c.first_name, c.phone, s.name, a.appointment_date, a.appointment_time, a.status, a.note "
                    "FROM appointments a "
                    "LEFT JOIN clients c ON c.id = a.client_id "
                    "LEFT JOIN services s ON s.id = a.service_id "
                    "WHERE a.appointment_date BETWEEN ? AND ? "
                    "ORDER BY a.appointment_date, a.appointment_time",
                    (start_date, end_date),
                )
                rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "telegram_id": row[1],
                "client_name": row[2],
                "phone": row[3],
                "service_name": row[4],
                "date": row[5],
                "time": row[6],
                "status": row[7],
                "note": row[8],
            }
            for row in rows
        ]

    @staticmethod
    async def list_upcoming_appointments(from_date: str) -> list[dict]:
        """Get all upcoming non-cancelled appointments from date."""
        from_date = normalize_date_to_iso(from_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT a.id, c.telegram_id, c.first_name, c.phone, s.name, a.appointment_date, a.appointment_time, a.status, a.note "
                    "FROM appointments a "
                    "LEFT JOIN clients c ON c.id = a.client_id "
                    "LEFT JOIN services s ON s.id = a.service_id "
                    "WHERE a.appointment_date >= ? AND a.status = 'planned' "
                    "ORDER BY a.appointment_date, a.appointment_time",
                    (from_date,),
                )
                rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "telegram_id": row[1],
                "client_name": row[2],
                "phone": row[3],
                "service_name": row[4],
                "date": row[5],
                "time": row[6],
                "status": row[7],
                "note": row[8],
            }
            for row in rows
        ]

    @staticmethod
    async def list_upcoming_appointments(today: str) -> list[dict]:
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT a.id, c.telegram_id, c.first_name, c.phone, s.name, a.appointment_date, a.appointment_time, a.status, a.note "
                    "FROM appointments a "
                    "LEFT JOIN clients c ON c.id = a.client_id "
                    "LEFT JOIN services s ON s.id = a.service_id "
                    "WHERE a.appointment_date >= ? AND a.status != 'cancelled' "
                    "ORDER BY a.appointment_date, a.appointment_time",
                    (today,),
                )
                rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "telegram_id": row[1],
                "client_name": row[2],
                "phone": row[3],
                "service_name": row[4],
                "date": row[5],
                "time": row[6],
                "status": row[7],
                "note": row[8],
            }
            for row in rows
        ]

    @staticmethod
    async def add_work_day(date_value: str, is_working: bool, note: str | None = None) -> None:
        date_value = normalize_date_to_iso(date_value)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "INSERT OR REPLACE INTO work_days (work_date, is_working, note) VALUES (?, ?, ?)",
                    (date_value, 1 if is_working else 0, note),
                )
                await connection.commit()

    @staticmethod
    async def block_time_slot(appointment_date: str, appointment_time: str, reason: str = "Заблокировано администратором") -> bool:
        """Block a time slot if no appointments exist at that time. Returns True on success, False if conflict."""
        appointment_date = normalize_date_to_iso(appointment_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Check if there are any active appointments at this time
                await cursor.execute(
                    "SELECT COUNT(*) FROM appointments WHERE appointment_date = ? AND appointment_time = ? AND status != 'cancelled'",
                    (appointment_date, appointment_time),
                )
                count = await cursor.fetchone()
                
                # If there's an appointment at this time, don't block
                if count and count[0] > 0:
                    return False
                
                created_at = datetime.now(get_tz_sync()).isoformat()
                await cursor.execute(
                    "INSERT OR REPLACE INTO unavailable_slots (slot_date, slot_time, reason, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (appointment_date, appointment_time, reason, created_at),
                )
                await connection.commit()
        return True

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
    async def move_appointment(appointment_id: int, new_date: str, new_time: str) -> bool:
        """Move an appointment to a new date/time."""
        new_date = normalize_date_to_iso(new_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Get appointment details
                await cursor.execute(
                    "SELECT service_id FROM appointments WHERE id = ?",
                    (appointment_id,),
                )
                row = await cursor.fetchone()
                if not row:
                    return False
                
                # Update appointment
                await cursor.execute(
                    "UPDATE appointments SET appointment_date = ?, appointment_time = ? WHERE id = ?",
                    (new_date, new_time, appointment_id),
                )
                await connection.commit()
        return True
    
    @staticmethod
    async def reschedule_appointment_by_admin(appointment_id: int, new_date: str, new_time: str) -> bool:
        """Reschedule an appointment by admin."""
        return await AdminService.move_appointment(appointment_id, new_date, new_time)

    @staticmethod
    async def cancel_appointment(appointment_id: int, reason: str = "Отменено администратором") -> bool:
        """Cancel an appointment (mark as cancelled, don't delete)."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE appointments SET status = ? WHERE id = ?",
                    ("cancelled", appointment_id),
                )
                await connection.commit()
        return True
    
    @staticmethod
    async def restore_appointment(appointment_id: int) -> bool:
        """Restore a cancelled appointment."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE appointments SET status = ? WHERE id = ?",
                    ("planned", appointment_id),
                )
                await connection.commit()
        return True
    
    @staticmethod
    async def mark_appointment_no_show(appointment_id: int) -> bool:
        """Mark appointment as no-show (client didn't come)."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE appointments SET status = ? WHERE id = ?",
                    ("no-show", appointment_id),
                )
                await connection.commit()
        return True

    @staticmethod
    async def get_appointment_details(appointment_id: int) -> dict | None:
        """Get full appointment details for any status."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT a.id, c.telegram_id, c.first_name, c.last_name, s.id, s.name, a.appointment_date, "
                    "a.appointment_time, a.status, a.note, s.duration, s.price "
                    "FROM appointments a "
                    "JOIN clients c ON c.id = a.client_id "
                    "JOIN services s ON s.id = a.service_id "
                    "WHERE a.id = ?",
                    (appointment_id,),
                )
                row = await cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "telegram_id": row[1],
            "first_name": row[2],
            "last_name": row[3],
            "service_id": row[4],
            "service_name": row[5],
            "date": row[6],
            "time": row[7],
            "status": row[8],
            "note": row[9],
            "duration": row[10],
            "price": row[11],
        }

    # ==================== SERVICE MANAGEMENT ====================

    @staticmethod
    async def get_services() -> list[dict]:
        """Get all services."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT id, name, description, price, duration FROM services ORDER BY name"
                )
                rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": row[3],
                "duration": row[4],
            }
            for row in rows
        ]

    @staticmethod
    async def get_service(service_id: int) -> dict | None:
        """Get service details."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT id, name, description, price, duration FROM services WHERE id = ?",
                    (service_id,),
                )
                row = await cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "price": row[3],
            "duration": row[4],
        }

    @staticmethod
    async def create_service(name: str, description: str, price: int, duration: int) -> int:
        """Create new service."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO services (name, description, price, duration) VALUES (?, ?, ?, ?)",
                    (name, description, price, duration),
                )
                await connection.commit()
                return cursor.lastrowid

    @staticmethod
    async def update_service(service_id: int, name: str = None, description: str = None, price: int = None, duration: int = None) -> bool:
        """Update service details."""
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if price is not None:
            updates.append("price = ?")
            params.append(price)
        if duration is not None:
            updates.append("duration = ?")
            params.append(duration)
        
        if not updates:
            return True
        
        params.append(service_id)
        
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                query = f"UPDATE services SET {', '.join(updates)} WHERE id = ?"
                await cursor.execute(query, params)
                await connection.commit()
        
        return True

    @staticmethod
    async def delete_service(service_id: int) -> bool:
        """Delete a service if it's not used in any appointments."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Check if service is used in any appointments
                await cursor.execute(
                    "SELECT COUNT(*) FROM appointments WHERE service_id = ? AND status != 'cancelled'",
                    (service_id,),
                )
                count = await cursor.fetchone()
                
                # If service is used in active appointments, don't delete
                if count and count[0] > 0:
                    return False
                
                # Delete the service
                await cursor.execute(
                    "DELETE FROM services WHERE id = ?",
                    (service_id,),
                )
                await connection.commit()
        return True

    @staticmethod
    async def get_day_slots_for_blocking(appointment_date: str) -> list[str]:
        """Get all available time slots for blocking respecting work day settings."""
        from app.services.booking_service import BookingService

        appointment_date = normalize_date_to_iso(appointment_date)
        
        # Check if it's a work day
        if not await BookingService.is_work_day(appointment_date):
            return []  # Non-working day - no slots available to block
        
        # Get schedule settings
        settings = await BookingService.get_schedule_settings()
        start_hour, start_min = map(int, settings.start_time.split(":"))
        end_hour, end_min = map(int, settings.end_time.split(":"))
        interval = settings.interval_minutes
        
        # Generate all time slots based on schedule settings
        all_times = []
        current = datetime.strptime(f"{start_hour:02d}:{start_min:02d}", "%H:%M")
        end = datetime.strptime(f"{end_hour:02d}:{end_min:02d}", "%H:%M")
        
        while current <= end:
            all_times.append(current.strftime("%H:%M"))
            current += timedelta(minutes=interval)
        
        return all_times

    @staticmethod
    async def get_blocked_slots_for_date(target_date: str) -> list[dict]:
        """Get all blocked time slots for a specific date."""
        target_date = normalize_date_to_iso(target_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT slot_date, slot_time, reason FROM unavailable_slots WHERE slot_date = ? ORDER BY slot_time",
                    (target_date,),
                )
                rows = await cursor.fetchall()
        
        return [
            {
                "date": row[0],
                "time": row[1],
                "reason": row[2],
            }
            for row in rows
        ]

    @staticmethod
    async def get_blocked_slots_for_week(start_date: str) -> list[dict]:
        """Get all blocked time slots for a week."""
        start_date = normalize_date_to_iso(start_date)
        start = datetime.fromisoformat(start_date)
        end = start + timedelta(days=7)
        
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT slot_date, slot_time, reason FROM unavailable_slots "
                    "WHERE slot_date >= ? AND slot_date < ? "
                    "ORDER BY slot_date, slot_time",
                    (start.isoformat()[:10], end.isoformat()[:10]),
                )
                rows = await cursor.fetchall()
        
        return [
            {
                "date": row[0],
                "time": row[1],
                "reason": row[2],
            }
            for row in rows
        ]

    @staticmethod
    async def block_entire_day(appointment_date: str) -> None:
        """Block all time slots for an entire day using schedule settings."""
        appointment_date = normalize_date_to_iso(appointment_date)
        all_times = await AdminService.get_day_slots_for_blocking(appointment_date)
        
        for time_slot in all_times:
            await AdminService.block_time_slot(appointment_date, time_slot, "День заблокирован")

    @staticmethod
    async def unblock_entire_day(appointment_date: str) -> None:
        """Unblock all time slots for an entire day."""
        appointment_date = normalize_date_to_iso(appointment_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM unavailable_slots WHERE slot_date = ?",
                    (appointment_date,),
                )
                await connection.commit()
    
    @staticmethod
    async def open_nonworking_day(appointment_date: str) -> None:
        """Open a non-working day for appointments (add exception)."""
        appointment_date = normalize_date_to_iso(appointment_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Insert or update the work_days table to mark this day as working
                await cursor.execute(
                    "INSERT OR REPLACE INTO work_days (work_date, is_working, note) VALUES (?, ?, ?)",
                    (appointment_date, 1, "Открыт день открытием исключения"),
                )
                # Remove any blocks that were on this day
                await cursor.execute(
                    "DELETE FROM unavailable_slots WHERE slot_date = ?",
                    (appointment_date,),
                )
                await connection.commit()
    
    @staticmethod
    async def close_working_day(appointment_date: str) -> None:
        """Close a working day (mark as non-working) using schedule settings."""
        appointment_date = normalize_date_to_iso(appointment_date)
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Insert or update the work_days table to mark this day as non-working
                await cursor.execute(
                    "INSERT OR REPLACE INTO work_days (work_date, is_working, note) VALUES (?, ?, ?)",
                    (appointment_date, 0, "Закрыт день закрытием исключения"),
                )
                
                # Get all time slots using schedule settings
                all_times = await AdminService.get_day_slots_for_blocking(appointment_date)
                
                # Block all slots for this day
                created_at = datetime.now(get_tz_sync()).isoformat()
                for time_slot in all_times:
                    await cursor.execute(
                        "INSERT OR IGNORE INTO unavailable_slots (slot_date, slot_time, reason, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (appointment_date, time_slot, "День закрыт", created_at),
                    )
                await connection.commit()
    
    # ==================== FEEDBACK MANAGEMENT ====================
    
    @staticmethod
    async def get_all_feedback() -> list[dict]:
        """Get all feedback with appointment and client details."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT f.id, c.telegram_id, c.first_name, a.appointment_date, s.name, "
                    "f.comment, f.photo_filename, f.created_at "
                    "FROM feedback f "
                    "LEFT JOIN appointments a ON f.appointment_id = a.id "
                    "LEFT JOIN clients c ON f.telegram_id = c.telegram_id "
                    "LEFT JOIN services s ON a.service_id = s.id "
                    "ORDER BY f.created_at DESC"
                )
                rows = await cursor.fetchall()
        
        return [
            {
                "id": row[0],
                "telegram_id": row[1],
                "client_name": row[2],
                "appointment_date": row[3],
                "service_name": row[4],
                "comment": row[5],
                "photo_filename": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]
    
    @staticmethod
    async def get_recent_feedback(limit: int = 10) -> list[dict]:
        """Get recent feedback."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT f.id, c.telegram_id, c.first_name, a.appointment_date, s.name, "
                    "f.comment, f.photo_filename, f.created_at "
                    "FROM feedback f "
                    "LEFT JOIN appointments a ON f.appointment_id = a.id "
                    "LEFT JOIN clients c ON f.telegram_id = c.telegram_id "
                    "LEFT JOIN services s ON a.service_id = s.id "
                    "ORDER BY f.created_at DESC "
                    "LIMIT ?",
                    (limit,)
                )
                rows = await cursor.fetchall()
        
        return [
            {
                "id": row[0],
                "telegram_id": row[1],
                "client_name": row[2],
                "appointment_date": row[3],
                "service_name": row[4],
                "comment": row[5],
                "photo_filename": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]
    
    # ==================== EXPORT & ADMIN TOOLS ====================
    
    @staticmethod
    async def get_all_clients() -> list[dict]:
        """Get all clients with their appointment count."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT c.id, c.telegram_id, c.first_name, c.last_name, c.phone, "
                    "COUNT(a.id) as total_appointments "
                    "FROM clients c "
                    "LEFT JOIN appointments a ON c.id = a.client_id "
                    "GROUP BY c.id "
                    "ORDER BY c.first_name"
                )
                rows = await cursor.fetchall()
        
        return [
            {
                "id": row[0],
                "telegram_id": row[1],
                "first_name": row[2],
                "last_name": row[3],
                "phone": row[4],
                "total_appointments": row[5],
            }
            for row in rows
        ]

    @staticmethod
    async def get_client_by_telegram_id(telegram_id: int) -> dict | None:
        """Get a single client by telegram id with aggregated info."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT c.id, c.telegram_id, c.first_name, c.last_name, c.phone, "
                    "COUNT(a.id) as total_appointments "
                    "FROM clients c "
                    "LEFT JOIN appointments a ON c.id = a.client_id "
                    "WHERE c.telegram_id = ? "
                    "GROUP BY c.id",
                    (telegram_id,),
                )
                row = await cursor.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "telegram_id": row[1],
            "first_name": row[2],
            "last_name": row[3],
            "phone": row[4],
            "total_appointments": row[5],
        }

    @staticmethod
    async def get_clients_page(page: int = 1, page_size: int = 8) -> tuple[list[dict], int]:
        """Return a paginated client list."""
        offset = max(page - 1, 0) * page_size
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT COUNT(*) FROM clients")
                total = (await cursor.fetchone())[0]
                await cursor.execute(
                    "SELECT c.id, c.telegram_id, c.first_name, c.last_name, c.phone, "
                    "COUNT(a.id) as total_appointments "
                    "FROM clients c "
                    "LEFT JOIN appointments a ON c.id = a.client_id "
                    "GROUP BY c.id "
                    "ORDER BY COALESCE(c.first_name, ''), COALESCE(c.last_name, ''), c.telegram_id "
                    "LIMIT ? OFFSET ?",
                    (page_size, offset),
                )
                rows = await cursor.fetchall()

        return ([
            {
                "id": row[0],
                "telegram_id": row[1],
                "first_name": row[2],
                "last_name": row[3],
                "phone": row[4],
                "total_appointments": row[5],
            }
            for row in rows
        ], total)

    @staticmethod
    async def ban_user(telegram_id: int, banned_by: int, reason: str | None = None) -> None:
        """Ban a user in the user bot."""
        banned_at = datetime.now(get_tz_sync()).isoformat()
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO banned_users (telegram_id, reason, banned_at, banned_by, is_active) "
                    "VALUES (?, ?, ?, ?, 1) "
                    "ON CONFLICT(telegram_id) DO UPDATE SET "
                    "reason = excluded.reason, banned_at = excluded.banned_at, "
                    "banned_by = excluded.banned_by, is_active = 1",
                    (telegram_id, reason, banned_at, banned_by),
                )
                await connection.commit()

    @staticmethod
    async def unban_user(telegram_id: int) -> None:
        """Unban a user in the user bot."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE banned_users SET is_active = 0 WHERE telegram_id = ?",
                    (telegram_id,),
                )
                await connection.commit()

    @staticmethod
    async def get_ban_info(telegram_id: int) -> dict | None:
        """Return active ban info for a user."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT telegram_id, reason, banned_at, banned_by, is_active "
                    "FROM banned_users WHERE telegram_id = ? AND is_active = 1",
                    (telegram_id,),
                )
                row = await cursor.fetchone()

        if not row:
            return None

        return {
            "telegram_id": row[0],
            "reason": row[1],
            "banned_at": row[2],
            "banned_by": row[3],
            "is_active": bool(row[4]),
        }

    @staticmethod
    async def is_user_banned(telegram_id: int) -> bool:
        """Check whether user is actively banned."""
        return await AdminService.get_ban_info(telegram_id) is not None

    @staticmethod
    async def get_banned_users_page(page: int = 1, page_size: int = 8) -> tuple[list[dict], int]:
        """Return a paginated active ban list joined with client info."""
        offset = max(page - 1, 0) * page_size
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT COUNT(*) FROM banned_users WHERE is_active = 1")
                total = (await cursor.fetchone())[0]
                await cursor.execute(
                    "SELECT b.telegram_id, b.reason, b.banned_at, b.banned_by, "
                    "c.first_name, c.last_name, c.phone "
                    "FROM banned_users b "
                    "LEFT JOIN clients c ON c.telegram_id = b.telegram_id "
                    "WHERE b.is_active = 1 "
                    "ORDER BY b.banned_at DESC "
                    "LIMIT ? OFFSET ?",
                    (page_size, offset),
                )
                rows = await cursor.fetchall()

        return ([
            {
                "telegram_id": row[0],
                "reason": row[1],
                "banned_at": row[2],
                "banned_by": row[3],
                "first_name": row[4],
                "last_name": row[5],
                "phone": row[6],
            }
            for row in rows
        ], total)
    
    @staticmethod
    async def get_client_history(telegram_id: int) -> list[dict]:
        """Get all appointments for a specific client."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT a.id, a.appointment_date, a.appointment_time, s.name, s.price, a.status, a.note, a.created_at "
                    "FROM appointments a "
                    "JOIN clients c ON c.id = a.client_id "
                    "JOIN services s ON s.id = a.service_id "
                    "WHERE c.telegram_id = ? "
                    "ORDER BY a.appointment_date DESC",
                    (telegram_id,),
                )
                rows = await cursor.fetchall()
        
        return [
            {
                "id": row[0],
                "date": row[1],
                "time": row[2],
                "service": row[3],
                "price": row[4],
                "status": row[5],
                "note": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]
    
    @staticmethod
    async def get_appointments_period(start_date: str, end_date: str) -> list[dict]:
        """Get all appointments in a date range."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT a.id, c.telegram_id, c.first_name, c.phone, a.appointment_date, a.appointment_time, "
                    "s.name, s.price, a.status, a.note "
                    "FROM appointments a "
                    "JOIN clients c ON c.id = a.client_id "
                    "JOIN services s ON s.id = a.service_id "
                    "WHERE a.appointment_date BETWEEN ? AND ? "
                    "ORDER BY a.appointment_date, a.appointment_time",
                    (start_date, end_date),
                )
                rows = await cursor.fetchall()
        
        return [
            {
                "id": row[0],
                "telegram_id": row[1],
                "client_name": row[2],
                "phone": row[3],
                "date": row[4],
                "time": row[5],
                "service": row[6],
                "price": row[7],
                "status": row[8],
                "note": row[9],
            }
            for row in rows
        ]
    
    @staticmethod
    async def get_statistics(start_date: str = None, end_date: str = None) -> dict:
        """Get statistics for appointments."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Total appointments
                if start_date and end_date:
                    await cursor.execute(
                        "SELECT COUNT(*) FROM appointments WHERE appointment_date BETWEEN ? AND ?",
                        (start_date, end_date),
                    )
                else:
                    await cursor.execute("SELECT COUNT(*) FROM appointments")
                
                total_apts = (await cursor.fetchone())[0]
                
                # Total revenue
                if start_date and end_date:
                    await cursor.execute(
                        "SELECT SUM(s.price) FROM appointments a "
                        "JOIN services s ON s.id = a.service_id "
                        "WHERE a.appointment_date BETWEEN ? AND ? AND a.status = 'planned'",
                        (start_date, end_date),
                    )
                else:
                    await cursor.execute(
                        "SELECT SUM(s.price) FROM appointments a "
                        "JOIN services s ON s.id = a.service_id "
                        "WHERE a.status = 'planned'"
                    )
                
                total_revenue = (await cursor.fetchone())[0] or 0
                
                # Most popular service
                if start_date and end_date:
                    await cursor.execute(
                        "SELECT s.name, COUNT(a.id) as count FROM appointments a "
                        "JOIN services s ON s.id = a.service_id "
                        "WHERE a.appointment_date BETWEEN ? AND ? "
                        "GROUP BY s.id ORDER BY count DESC LIMIT 1",
                        (start_date, end_date),
                    )
                else:
                    await cursor.execute(
                        "SELECT s.name, COUNT(a.id) as count FROM appointments a "
                        "JOIN services s ON s.id = a.service_id "
                        "GROUP BY s.id ORDER BY count DESC LIMIT 1"
                    )
                
                top_service = await cursor.fetchone()
                
                # Total clients
                if start_date and end_date:
                    await cursor.execute(
                        "SELECT COUNT(DISTINCT a.client_id) FROM appointments a "
                        "WHERE a.appointment_date BETWEEN ? AND ?",
                        (start_date, end_date),
                    )
                else:
                    await cursor.execute("SELECT COUNT(DISTINCT client_id) FROM appointments")
                
                total_clients = (await cursor.fetchone())[0]
        
        return {
            "total_appointments": total_apts,
            "total_revenue": total_revenue,
            "top_service": top_service[0] if top_service else "N/A",
            "total_unique_clients": total_clients,
        }
    
    @staticmethod
    async def clear_all_blocks() -> int:
        """Clear all blocked time slots."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT COUNT(*) FROM unavailable_slots")
                count = (await cursor.fetchone())[0]
                
                await cursor.execute("DELETE FROM unavailable_slots")
                await connection.commit()
        
        return count
    
    # ==================== CSV EXPORT ====================
    
    @staticmethod
    def generate_appointments_csv(appointments: list[dict]) -> str:
        """Generate CSV content for appointments."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        # Header
        writer.writerow(['Дата', 'Время', 'Клиент', 'Telegram ID', 'Телефон', 'Услуга', 'Цена (₽)', 'Статус'])
        
        # Rows
        for apt in appointments:
            writer.writerow([
                apt['date'],
                apt['time'],
                apt['client_name'],
                apt['telegram_id'],
                apt['phone'],
                apt['service'],
                apt['price'],
                apt['status'],
            ])
        
        return output.getvalue()
    
    @staticmethod
    def generate_clients_csv(clients: list[dict]) -> str:
        """Generate CSV content for clients."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        # Header
        writer.writerow(['Имя', 'Фамилия', 'Telegram ID', 'Телефон', 'Количество визитов'])
        
        # Rows
        for client in clients:
            writer.writerow([
                client['first_name'],
                client['last_name'] or '',
                client['telegram_id'],
                client['phone'],
                client['total_appointments'],
            ])
        
        return output.getvalue()
    
    @staticmethod
    async def get_all_blocks() -> list[dict]:
        """Get all blocked time slots."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT slot_date, slot_time, reason FROM unavailable_slots "
                    "ORDER BY slot_date, slot_time"
                )
                rows = await cursor.fetchall()
        
        return [
            {
                "date": row[0],
                "time": row[1],
                "reason": row[2],
            }
            for row in rows
        ]
    
    # ==================== SERVICE PHOTOS ====================
    
    @staticmethod
    async def set_service_photo(service_id: int, photo_file_id: str) -> bool:
        """Save photo file_id for service."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE services SET photo_file_id = ? WHERE id = ?",
                    (photo_file_id, service_id),
                )
                await connection.commit()
        return True
    
    @staticmethod
    async def get_service_photo(service_id: int) -> str | None:
        """Get photo file_id for service."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT photo_file_id FROM services WHERE id = ?",
                    (service_id,),
                )
                row = await cursor.fetchone()
        return row[0] if row else None
    
    @staticmethod
    async def get_services_with_photos() -> list[dict]:
        """Get all services with their photo info."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT id, name, description, price, duration, photo_file_id FROM services ORDER BY name"
                )
                rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": row[3],
                "duration": row[4],
                "photo_file_id": row[5],
            }
            for row in rows
        ]
    
    # ==================== SALON CONTACTS ====================
    
    @staticmethod
    async def get_salon_contacts() -> str:
        """Get salon contact information as a single formatted text."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT value FROM salon_info WHERE key = 'contacts'"
                )
                row = await cursor.fetchone()
        
        if row:
            return row[0]
        return None
    
    @staticmethod
    async def update_salon_contacts(contacts_text: str) -> bool:
        """Update salon contacts with full text."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "INSERT OR REPLACE INTO salon_info (key, value) VALUES (?, ?)",
                    ("contacts", contacts_text)
                )
                await connection.commit()
        
        return True

    # ==================== SCHEDULE MANAGEMENT ====================
    
    @staticmethod
    async def get_schedule_settings() -> dict:
        """Get current schedule settings."""
        from ..models.schemas import ScheduleSettings
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
        
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT key, value FROM schedule_settings")
                    rows = await cursor.fetchall()
                    for key, value in rows:
                        if key == "interval_minutes":
                            settings_dict[key] = int(value)
                        elif key == "cycle_start_date" and value:
                            settings_dict[key] = normalize_date_to_iso(value)
                        elif key == "working_days":
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
                            settings_dict[key] = ",".join(normalized) if normalized else None
                        else:
                            settings_dict[key] = value
        except Exception:
            pass
        
        return settings_dict
    
    @staticmethod
    async def check_schedule_conflicts(mode: str, cycle_pattern: str = None, cycle_start_date: str = None, working_days: str = None) -> list[str]:
        """Check for conflicts when changing schedule mode."""
        from .booking_service import BookingService
        
        conflicts = []
        normalized_cycle_start_date = normalize_date_to_iso(cycle_start_date) if cycle_start_date else None
        
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Get all active appointments
                await cursor.execute(
                    "SELECT appointment_date FROM appointments WHERE status = 'planned' ORDER BY appointment_date"
                )
                apt_dates = [row[0] for row in await cursor.fetchall()]
        
        # Check each appointment date
        for apt_date in apt_dates:
            is_work = await BookingService.is_work_day(apt_date)
            
            # Simulate new settings
            if mode == "cycle" and cycle_pattern and normalized_cycle_start_date:
                try:
                    from datetime import datetime
                    current = datetime.strptime(apt_date, "%Y-%m-%d")
                    pattern_parts = cycle_pattern.split('/')
                    work_days = int(pattern_parts[0])
                    cycle_length = int(pattern_parts[0]) + int(pattern_parts[1])
                    start = datetime.strptime(normalized_cycle_start_date, "%Y-%m-%d")
                    days_since_start = (current - start).days
                    if days_since_start >= 0:
                        position = days_since_start % cycle_length
                        would_be_work = position < work_days
                    else:
                        would_be_work = False
                except Exception:
                    would_be_work = True
            elif mode == "weekdays" and working_days:
                try:
                    from datetime import datetime
                    current = datetime.strptime(apt_date, "%Y-%m-%d")
                    weekday = current.weekday()
                    working_list = [int(x) for x in working_days.split(',')]
                    would_be_work = weekday in working_list
                except Exception:
                    would_be_work = True
            else:
                would_be_work = True
            
            # If currently is work day but would NOT be, that's a conflict
            if is_work and not would_be_work:
                conflicts.append(apt_date)
        
        return conflicts
    
    @staticmethod
    async def set_schedule_cycle(cycle_pattern: str, cycle_start_date: str) -> tuple[bool, str]:
        """Set schedule to cycle mode."""
        cycle_start_date = normalize_date_to_iso(cycle_start_date)
        conflicts = await AdminService.check_schedule_conflicts("cycle", cycle_pattern, cycle_start_date)
        
        if conflicts:
            conflict_dates = ", ".join(format_date_for_display(item) for item in conflicts[:3])
            return (False, f"Конфликты на следующие дни: {conflict_dates}" + ("..." if len(conflicts) > 3 else ""))
        
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("mode", "cycle"))
                    await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("cycle_pattern", cycle_pattern))
                    await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("cycle_start_date", cycle_start_date))
                    await connection.commit()
            return (True, "Циклический график установлен")
        except Exception as e:
            return (False, f"Ошибка: {str(e)}")
    
    @staticmethod
    async def set_schedule_weekdays(working_days: str) -> tuple[bool, str]:
        """Set schedule to weekdays mode."""
        conflicts = await AdminService.check_schedule_conflicts("weekdays", None, None, working_days)
        
        if conflicts:
            conflict_dates = ", ".join(format_date_for_display(item) for item in conflicts[:3])
            return (False, f"Конфликты на следующие дни: {conflict_dates}" + ("..." if len(conflicts) > 3 else ""))
        
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("mode", "weekdays"))
                    await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("working_days", working_days))
                    await connection.commit()
            return (True, "Режим рабочих дней установлен")
        except Exception as e:
            return (False, f"Ошибка: {str(e)}")
    
    @staticmethod
    async def set_schedule_free() -> tuple[bool, str]:
        """Set schedule to free mode."""
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("mode", "free"))
                    await connection.commit()
            return (True, "Свободный график установлен")
        except Exception as e:
            return (False, f"Ошибка: {str(e)}")
    
    @staticmethod
    async def update_interval(interval_minutes: int) -> bool:
        """Update time slot interval."""
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("interval_minutes", str(interval_minutes)))
                    await connection.commit()
            return True
        except Exception:
            return False
    
    @staticmethod
    async def set_break_time(break_start: str | None, break_end: str | None) -> bool:
        """Set break time."""
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    if break_start:
                        await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("break_start", break_start))
                    else:
                        await cursor.execute("DELETE FROM schedule_settings WHERE key = 'break_start'")
                    
                    if break_end:
                        await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("break_end", break_end))
                    else:
                        await cursor.execute("DELETE FROM schedule_settings WHERE key = 'break_end'")
                    
                    await connection.commit()
            return True
        except Exception:
            return False

    @staticmethod
    async def set_working_hours(start_time: str, end_time: str) -> bool:
        """Set working hours (start and end time for appointments)."""
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("start_time", start_time))
                    await cursor.execute("INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)", ("end_time", end_time))
                    await connection.commit()
            return True
        except Exception:
            return False

    # ==================== ADMIN NOTIFICATIONS ====================

    @staticmethod
    async def set_admin_notification_time(admin_id: int, notification_time: str) -> bool:
        """Save admin notification time (HH:MM format)."""
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    # Using schedule_settings with admin_id prefix for storage
                    key = f"admin_notification_time_{admin_id}"
                    await cursor.execute(
                        "INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)",
                        (key, notification_time)
                    )
                    await connection.commit()
            return True
        except Exception:
            return False

    @staticmethod
    async def get_admin_notification_time(admin_id: int) -> str | None:
        """Get admin notification time (HH:MM format)."""
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    key = f"admin_notification_time_{admin_id}"
                    await cursor.execute(
                        "SELECT value FROM schedule_settings WHERE key = ?",
                        (key,)
                    )
                    result = await cursor.fetchone()
            return result[0] if result else None
        except Exception:
            return None

    # ==================== TIMEZONE MANAGEMENT ====================

    @staticmethod
    async def set_timezone_offset(offset_hours: int) -> bool:
        """Save timezone offset in hours (e.g., 3 for UTC+3, -5 for UTC-5)."""
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)",
                        ("timezone_offset", str(offset_hours))
                    )
                    await connection.commit()
            return True
        except Exception:
            return False

    @staticmethod
    async def get_timezone_offset() -> int:
        """Get timezone offset in hours. Returns 3 (UTC+3) as default."""
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT value FROM schedule_settings WHERE key = ?",
                        ("timezone_offset",)
                    )
                    result = await cursor.fetchone()
            if result:
                return int(result[0])
        except Exception:
            pass
        return 3  # Default to UTC+3

    @staticmethod
    async def set_schedule_setting(key: str, value: str | int) -> bool:
        """Set a generic schedule setting (key-value pair)."""
        try:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "INSERT OR REPLACE INTO schedule_settings (key, value) VALUES (?, ?)",
                        (key, str(value))
                    )
                    await connection.commit()
            return True
        except Exception:
            return False

