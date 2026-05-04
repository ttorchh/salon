from datetime import datetime, timedelta
from aiogram import Bot
from app.database import get_connection
from app.config import get_tz_sync, BOT_TOKEN
from app.services.notification_service import NotificationService
import asyncio
import logging
import csv
import io
import aiosqlite
from datetime import datetime, timedelta
from aiogram.types import BufferedInputFile

logger = logging.getLogger(__name__)

async def send_reminders_task():
    """Background task to send reminders for upcoming appointments."""
    from app.bot import create_bot
    
    logger.info("🚀 send_reminders_task started")
    
    # Create bot once outside the loop
    user_bot = create_bot(BOT_TOKEN)
    last_check = None  # Track last check time to prevent duplicate sends
    
    try:
        while True:
            try:
                now = datetime.now(get_tz_sync())
                current_hour = now.hour
                current_minute = now.minute
                today = now.date().isoformat()
                
                # Create a checkpoint key for this minute to prevent duplicates
                current_checkpoint = f"{today}_{current_hour}_{current_minute // 5}"  # Check every 5 minutes
                
                # Skip if we already processed this checkpoint
                if last_check == current_checkpoint:
                    await asyncio.sleep(30)
                    continue
                
                last_check = current_checkpoint
                
                async with get_connection() as connection:
                    async with connection.cursor() as cursor:
                        # 1. Send reminder at 10:00 AM for appointments not today (24 hours before)
                        if current_hour == 10 and current_minute < 5:
                            tomorrow = (now + timedelta(days=1)).date().isoformat()
                            await cursor.execute(
                                "SELECT a.id FROM appointments a "
                                "WHERE a.appointment_date >= ? AND a.status = 'planned' AND a.reminder_sent = 0 "
                                "AND a.appointment_date != ?",
                                (tomorrow, today),
                            )
                            far_appointments = await cursor.fetchall()
                            
                            for (apt_id,) in far_appointments:
                                try:
                                    await NotificationService.send_reminder(user_bot, apt_id, reminder_type="before")
                                    # Mark as sent
                                    await cursor.execute(
                                        "UPDATE appointments SET reminder_sent = 1 WHERE id = ?",
                                        (apt_id,),
                                    )
                                    await connection.commit()
                                except Exception as e:
                                    logger.error(f"Error sending 24-hour reminder for appointment {apt_id}: {e}")
                        
                        # 2. Send reminder 1 hour before appointment today
                        await cursor.execute(
                            "SELECT a.id, a.appointment_time FROM appointments a "
                            "WHERE a.appointment_date = ? AND a.status = 'planned' AND a.reminder_sent = 0",
                            (today,),
                        )
                        today_appointments = await cursor.fetchall()
                        
                        for apt_id, apt_time in today_appointments:
                            try:
                                # Parse appointment time (HH:MM format)
                                apt_hour, apt_minute = map(int, apt_time.split(':'))
                                apt_datetime = datetime.combine(now.date(), datetime.min.time().replace(hour=apt_hour, minute=apt_minute), tzinfo=get_tz_sync())
                                
                                # Check if appointment is in 1 hour (within 50-70 minute window)
                                time_until_apt = (apt_datetime - now).total_seconds() / 60  # minutes
                                if 50 < time_until_apt < 70:
                                    await NotificationService.send_reminder(user_bot, apt_id, reminder_type="hour_before")
                                    # Mark as sent
                                    await cursor.execute(
                                        "UPDATE appointments SET reminder_sent = 1 WHERE id = ?",
                                        (apt_id,),
                                    )
                                    await connection.commit()
                            except Exception as e:
                                logger.error(f"Error sending 1-hour reminder for appointment {apt_id}: {e}")
                        
                        # 2.5 Send immediate message when appointment ends (catch-up logic)
                        # Query for appointments that have ended but message not sent yet
                        # Only send within 24 hours of completion to avoid duplication with 3-week reminder
                        # Filter to recent appointments only to avoid double-sending with completion reminder
                        await cursor.execute(
                            "SELECT a.id, a.appointment_date, a.appointment_time, a.service_duration_minutes "
                            "FROM appointments a "
                            "WHERE a.status = 'planned' AND a.completion_message_sent = 0 AND a.completion_reminder_sent = 0 "
                            "AND a.appointment_date > date('now', '-1 day')",
                        )
                        all_appointments = await cursor.fetchall()
                        
                        for apt_id, apt_date, apt_time, service_duration in all_appointments:
                            try:
                                # Use stored service_duration_minutes, or fallback to 30 if 0/null
                                duration = service_duration if service_duration and service_duration > 0 else 30
                                
                                # Calculate appointment completion time using stored duration
                                apt_datetime = datetime.strptime(f"{apt_date} {apt_time}", "%Y-%m-%d %H:%M")
                                apt_datetime = apt_datetime.replace(tzinfo=get_tz_sync())
                                apt_end_time = apt_datetime + timedelta(minutes=duration)
                                
                                # Send message only if appointment ended recently (within 24 hours)
                                time_since_end = (now - apt_end_time).total_seconds() / 3600  # hours
                                if 0 <= time_since_end <= 24:
                                    await NotificationService.send_reminder(user_bot, apt_id, reminder_type="completion_immediate")
                                    # Mark as sent
                                    await cursor.execute(
                                        "UPDATE appointments SET completion_message_sent = 1 WHERE id = ?",
                                        (apt_id,),
                                    )
                                    await connection.commit()
                            except Exception as e:
                                logger.error(f"Error sending completion message for appointment {apt_id}: {e}")
                        
                        # 3. Send completion reminder 3 weeks after appointment completion
                        # Use stored service duration
                        # Only send if completion_message was NOT already sent recently
                        await cursor.execute(
                            "SELECT a.id, a.appointment_date, a.appointment_time, a.service_duration_minutes "
                            "FROM appointments a "
                            "WHERE a.status = 'planned' AND a.completion_reminder_sent = 0 AND a.completion_message_sent = 0",
                        )
                        all_appointments = await cursor.fetchall()
                        
                        if all_appointments:
                            logger.info(f"[COMPLETION REMINDER] Found {len(all_appointments)} appointments for check")
                        
                        for apt_id, apt_date, apt_time, service_duration in all_appointments:
                            try:
                                # Use stored service_duration_minutes, or fallback to 30 if 0/null
                                duration = service_duration if service_duration and service_duration > 0 else 30
                                
                                # Calculate appointment completion time
                                apt_datetime = datetime.strptime(f"{apt_date} {apt_time}", "%Y-%m-%d %H:%M")
                                apt_datetime = apt_datetime.replace(tzinfo=get_tz_sync())
                                apt_end_time = apt_datetime + timedelta(minutes=duration)
                                
                                # Calculate 3 weeks after completion
                                completion_plus_3_weeks = apt_end_time + timedelta(days=21)
                                
                                logger.info(f"[COMPLETION REMINDER] Apt {apt_id}: date={apt_date} time={apt_time} duration={duration}min")
                                logger.info(f"[COMPLETION REMINDER] Apt {apt_id}: apt_end={apt_end_time.isoformat()}")
                                logger.info(f"[COMPLETION REMINDER] Apt {apt_id}: deadline={completion_plus_3_weeks.isoformat()}")
                                logger.info(f"[COMPLETION REMINDER] Apt {apt_id}: now={now.isoformat()}")
                                logger.info(f"[COMPLETION REMINDER] Apt {apt_id}: ready={now >= completion_plus_3_weeks}")
                                
                                # If 3 weeks have passed since completion, send reminder
                                if now >= completion_plus_3_weeks:
                                    logger.info(f"[COMPLETION REMINDER] Sending reminder for apt {apt_id}")
                                    await NotificationService.send_reminder(user_bot, apt_id, reminder_type="completion")
                                    # Mark as sent
                                    await cursor.execute(
                                        "UPDATE appointments SET completion_reminder_sent = 1 WHERE id = ?",
                                        (apt_id,),
                                    )
                                    await connection.commit()
                                    logger.info(f"[COMPLETION REMINDER] Marked apt {apt_id} as sent")
                            except Exception as e:
                                logger.error(f"Error sending completion reminder for appointment {apt_id}: {e}")
                
                # Wait 30 seconds before checking again
                await asyncio.sleep(30)
            
            except Exception as e:
                logger.error(f"Error in send_reminders_task iteration: {e}")
                # Wait before retrying
                await asyncio.sleep(60)
    
    finally:
        await user_bot.session.close()


async def send_admin_notifications_task():
    """Background task to send admin notifications at set time with today's appointments."""
    from app.bot import create_bot
    from app.services.admin_service import AdminService
    from app.services.booking_service import BookingService
    from app.config import ADMIN_IDS, ADMIN_BOT_TOKEN
    
    # Create bot once outside the loop
    admin_bot = create_bot(ADMIN_BOT_TOKEN, is_admin_bot=True)
    last_sent_today = None  # Track if we already sent today
    
    try:
        while True:
            try:
                now = datetime.now(get_tz_sync())
                current_hour = now.hour
                current_minute = now.minute
                today = now.date().isoformat()
                
                # Check if today's notifications were already sent
                current_date_key = today
                if last_sent_today == current_date_key:
                    await asyncio.sleep(60)  # Wait 1 minute before checking again
                    continue
                
                # Check each admin's notification settings
                for admin_id in ADMIN_IDS:
                    notification_time = await AdminService.get_admin_notification_time(admin_id)
                    
                    if not notification_time:
                        continue  # No notification time set for this admin
                    
                    # Parse notification time
                    try:
                        set_hour, set_minute = map(int, notification_time.split(':'))
                    except (ValueError, IndexError):
                        continue
                    
                    # Check if current time matches notification time (within 5-minute window)
                    if current_hour == set_hour and abs(current_minute - set_minute) < 5:
                        # Check if today is a working day
                        is_work = await BookingService.is_work_day(today)
                        
                        if is_work:
                            # Get appointments for today
                            appointments = await AdminService.list_appointments_for_day(today)
                            
                            if appointments:
                                # Build notification message
                                message_text = f"📅 <b>Записи на {today}</b>\n\n"
                                for apt in appointments:
                                    message_text += (
                                        f"⏰ {apt['time']} — {apt['service_name']}\n"
                                        f"👤 {apt['client_name']}"
                                    )
                                    if apt['phone']:
                                        message_text += f" ({apt['phone']})"
                                    message_text += "\n"
                                    if apt['note']:
                                        message_text += f"💬 Пожелания: {apt['note']}\n"
                                    message_text += "\n"
                                
                                # Send to admin
                                try:
                                    await admin_bot.send_message(
                                        chat_id=admin_id,
                                        text=message_text,
                                        parse_mode="HTML",
                                    )
                                    logger.info(f"Admin notification sent to {admin_id} at {notification_time}")
                                except Exception as e:
                                    logger.error(f"Error sending admin notification to {admin_id}: {e}")
                        
                        # Mark this date as processed
                        last_sent_today = current_date_key
                
                # Wait 60 seconds before checking again
                await asyncio.sleep(60)
            
            except Exception as e:
                logger.error(f"Error in send_admin_notifications_task iteration: {e}")
                # Wait before retrying
                await asyncio.sleep(60)
    
    finally:
        await admin_bot.session.close()


async def cleanup_db_soft_task():
    """Ежедневная фоновая очистка БД в 3:00.
    Каждый день сохраняет CSV архив в EXPORTS_DIR.
    1го числа отправляет сводку за прошлый месяц админам.
    """
    logger.info("🧹 cleanup_db_soft_task started")
    last_cleanup_date = None

    try:
        while True:
            try:
                now = datetime.now(get_tz_sync())
                today = now.date().isoformat()

                if last_cleanup_date == today:
                    await asyncio.sleep(3600)
                    continue

                if now.hour == 3 and now.minute < 10:
                    logger.info("🧹 Запуск ежедневной очистки БД")

                    cutoff_90 = (now - timedelta(days=90)).strftime("%Y-%m-%d")
                    cutoff_60 = (now - timedelta(days=60)).strftime("%Y-%m-%d")
                    soft_cutoff = (now - timedelta(days=180)).strftime("%Y-%m-%d")
                    batch_size = 500
                    result = {}
                    is_monthly = now.day == 1

                    async with get_connection() as connection:
                        connection.row_factory = aiosqlite.Row

                        # Собираем записи диапазона 60-90 дней перед удалением
                        async with connection.cursor() as cur:
                            await cur.execute("""
                                SELECT
                                    a.id, a.appointment_date, a.appointment_time,
                                    a.status, a.note, a.created_at,
                                    c.first_name, c.last_name, c.phone, c.telegram_id,
                                    s.name as service_name, s.price
                                FROM appointments a
                                JOIN clients c ON c.id = a.client_id
                                JOIN services s ON s.id = a.service_id
                                WHERE a.status IN ('cancelled', 'completed')
                                AND a.appointment_date >= ? AND a.appointment_date < ?
                                ORDER BY a.appointment_date
                                LIMIT ?
                            """, (cutoff_90, cutoff_60, batch_size))
                            rows = await cur.fetchall()

                        # Удаляем appointments старше 90 дней
                        async with connection.cursor() as cur:
                            await cur.execute("""
                                DELETE FROM appointments
                                WHERE id IN (
                                    SELECT id FROM appointments
                                    WHERE status IN ('cancelled', 'completed')
                                    AND appointment_date < ?
                                    ORDER BY appointment_date
                                    LIMIT ?
                                )
                            """, (cutoff_90, batch_size))
                            result["appointments"] = cur.rowcount

                        # Удаляем unavailable_slots
                        async with connection.cursor() as cur:
                            await cur.execute("""
                                DELETE FROM unavailable_slots
                                WHERE id IN (
                                    SELECT id FROM unavailable_slots
                                    WHERE slot_date < ?
                                    ORDER BY slot_date
                                    LIMIT ?
                                )
                            """, (cutoff_90, batch_size))
                            result["unavailable_slots"] = cur.rowcount

                        # Удаляем feedback старше 180 дней
                        async with connection.cursor() as cur:
                            await cur.execute("""
                                DELETE FROM feedback
                                WHERE id IN (
                                    SELECT id FROM feedback
                                    WHERE created_at < ?
                                    ORDER BY created_at
                                    LIMIT ?
                                )
                            """, (soft_cutoff, batch_size))
                            result["feedback"] = cur.rowcount

                        await connection.commit()

                    logger.info(f"✅ Очистка завершена: {result}")

                    # Сохраняем CSV каждый день (даже если rows пустой — файл не создаём)
                    if rows:
                        try:
                            from .config import EXPORTS_DIR
                            import csv, io

                            output = io.StringIO()
                            # Точка с запятой как разделитель — корректно открывается
                            # в Excel с кириллицей без доп. настроек
                            writer = csv.writer(output, delimiter=';')
                            writer.writerow([
                                "Дата", "Время", "Статус", "Имя", "Фамилия",
                                "Телефон", "Telegram ID", "Услуга", "Цена",
                                "Заметка", "Создана"
                            ])
                            for r in rows:
                                writer.writerow([
                                    r["appointment_date"], r["appointment_time"],
                                    r["status"], r["first_name"], r["last_name"],
                                    r["phone"], r["telegram_id"], r["service_name"],
                                    r["price"], r["note"], r["created_at"]
                                ])

                            # utf-8-sig — BOM для корректного открытия в Excel
                            csv_bytes = output.getvalue().encode("utf-8-sig")
                            export_filename = EXPORTS_DIR / f"cleanup_{today}.csv"
                            export_filename.write_bytes(csv_bytes)
                            logger.info(f"📁 Архив сохранён: {export_filename.name}")

                            # Удаляем файлы старше 3 месяцев
                            cutoff_month = (now - timedelta(days=90)).strftime("%Y-%m")
                            for f in sorted(EXPORTS_DIR.glob("cleanup_*.csv")):
                                file_month = f.stem.replace("cleanup_", "")[:7]
                                if file_month < cutoff_month:
                                    f.unlink()
                                    logger.info(f"🗑 Удалён старый архив: {f.name}")

                        except Exception as e:
                            logger.error(f"Ошибка сохранения CSV архива: {e}")

                    # 1го числа — отправляем файлы за прошлый месяц
                    if is_monthly:
                        try:
                            from .config import ADMIN_IDS, ADMIN_BOT_TOKEN, EXPORTS_DIR
                            from .bot import create_bot
                            from aiogram.types import BufferedInputFile

                            prev_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
                            monthly_files = sorted(EXPORTS_DIR.glob(f"cleanup_{prev_month}-*.csv"))

                            if monthly_files:
                                admin_bot = create_bot(ADMIN_BOT_TOKEN)
                                try:
                                    for admin_id in ADMIN_IDS:
                                        await admin_bot.send_message(
                                            chat_id=admin_id,
                                            text=(
                                                f"🗂 Ежемесячный архив за {prev_month}\n"
                                                f"Файлов: {len(monthly_files)}\n"
                                                f"Удалено записей за месяц: {result['appointments']}"
                                            )
                                        )
                                        for f in monthly_files:
                                            await admin_bot.send_document(
                                                chat_id=admin_id,
                                                document=BufferedInputFile(
                                                    f.read_bytes(),
                                                    filename=f.name
                                                ),
                                            )
                                finally:
                                    await admin_bot.session.close()
                            else:
                                logger.info(f"Нет архивов за {prev_month} для отправки")

                        except Exception as e:
                            logger.error(f"Ошибка отправки месячного архива: {e}")

                    last_cleanup_date = today

                await asyncio.sleep(600)

            except Exception as e:
                logger.error(f"Ошибка в cleanup_db_soft_task: {e}")
                await asyncio.sleep(3600)

    except Exception as e:
        logger.error(f"Критическая ошибка в cleanup_db_soft_task: {e}")

def start_user_background_tasks():
    """Start user bot background tasks (reminders and completions)."""
    logger.info("📌 Initializing user background tasks (reminders)")
    asyncio.create_task(send_reminders_task())


def start_admin_background_tasks():
    """Start admin bot background tasks (daily notifications + soft DB cleanup)."""
    logger.info("📌 Initializing admin background tasks")
    asyncio.create_task(send_admin_notifications_task())
    asyncio.create_task(cleanup_db_soft_task())


def start_background_tasks():
    """Start all background tasks (non-async wrapper). 
    This is kept for backwards compatibility - prefer using start_user_background_tasks() or start_admin_background_tasks()."""
    logger.info("📌 Initializing ALL background tasks (user + admin)")
    asyncio.create_task(send_reminders_task())
