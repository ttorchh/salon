from aiogram import Bot
from app.database import get_connection
from ..bot import create_bot
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def format_date_for_display(date_str: str) -> str:
    """Convert date from YYYY-MM-DD to DD-MM-YYYY format for display."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%m-%Y")
    except:
        return date_str


class NotificationService:
    """Service for sending notifications to users."""
    
    @staticmethod
    async def notify_appointment_cancelled(bot: Bot, appointment_id: int, reason: str = "") -> None:
        """Notify user that their appointment was cancelled."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT c.telegram_id, c.first_name, a.appointment_date, a.appointment_time, s.name "
                    "FROM appointments a "
                    "JOIN clients c ON c.id = a.client_id "
                    "JOIN services s ON s.id = a.service_id "
                    "WHERE a.id = ?",
                    (appointment_id,),
                )
                row = await cursor.fetchone()
        
        if not row:
            return
        
        telegram_id, first_name, date, time, service_name = row
        client_name = (first_name or "Клиент").strip() or "Клиент"
        
        message = (
            f"❌ {client_name}, ваша запись отменена\n\n"
            f"Услуга: {service_name}\n"
            f"Дата: {format_date_for_display(date)}\n"
            f"Время: {time}\n"
        )
        
        if reason:
            message += f"По причине: {reason}\n"
        
        message += f"\nПожалуйста, свяжитесь с салоном или запишитесь на другое время."
        
        # Send via user bot, not admin bot
        from ..config import BOT_TOKEN
        from ..bot import create_bot
        user_bot = create_bot(BOT_TOKEN)
        try:
            await user_bot.send_message(
                chat_id=telegram_id,
                text=message,
            )
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
        finally:
            await user_bot.session.close()
    
    @staticmethod
    async def notify_appointment_rescheduled(
        bot: Bot,
        appointment_id: int,
        new_date: str,
        new_time: str,
        old_date: str = None,
        old_time: str = None,
    ) -> None:
        """Notify user that their appointment was rescheduled via user bot."""
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT c.telegram_id, c.first_name, s.name "
                    "FROM appointments a "
                    "JOIN clients c ON c.id = a.client_id "
                    "JOIN services s ON s.id = a.service_id "
                    "WHERE a.id = ?",
                    (appointment_id,),
                )
                row = await cursor.fetchone()
        
        if not row:
            return
        
        telegram_id, first_name, service_name = row
        
        # If old_date/old_time not provided, get from DB (for backward compatibility)
        if old_date is None or old_time is None:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT appointment_date, appointment_time FROM appointments WHERE id = ?",
                        (appointment_id,),
                    )
                    apt_row = await cursor.fetchone()
                    if apt_row:
                        old_date = old_date or apt_row[0]
                        old_time = old_time or apt_row[1]
        
        client_name = (first_name or "Клиент").strip() or "Клиент"
        
        message = (
            f"📅 {client_name}, ваша запись перенесена\n\n"
            f"Услуга: {service_name}\n"
            f"Старая дата: {format_date_for_display(old_date)} {old_time}\n"
            f"Новая дата: {format_date_for_display(new_date)} {new_time}\n\n"
            f"Ждём вас с нетерпением!"
        )
        
        # Send via user bot, not admin bot
        from ..config import BOT_TOKEN
        from ..bot import create_bot
        user_bot = create_bot(BOT_TOKEN)
        try:
            await user_bot.send_message(
                chat_id=telegram_id,
                text=message,
            )
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
        finally:
            await user_bot.session.close()
    
    @staticmethod
    async def send_reminder(
        bot,
        appointment_id: int,
        reminder_type: str = "before",
    ) -> None:
        """Send reminder notification before appointment.
        
        reminder_type can be:
        - "before": Напоминание в 10:00 утра за день до записи
        - "hour_before": Напоминание за час до записи (только для записей сегодня)
        - "completion": Напоминание через 3 недели для повторного визита и отзыва
        """
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT c.telegram_id, a.appointment_date, a.appointment_time, s.name, s.price, s.id "
                    "FROM appointments a "
                    "JOIN clients c ON c.id = a.client_id "
                    "JOIN services s ON s.id = a.service_id "
                    "WHERE a.id = ? AND a.status = 'planned'",
                    (appointment_id,),
                )
                row = await cursor.fetchone()
        
        if not row:
            return
        
        telegram_id, date, time, service_name, price, service_id = row
        
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT first_name FROM clients WHERE telegram_id = ?",
                    (telegram_id,),
                )
                row_client = await cursor.fetchone()
        
        client_name = (row_client[0] if row_client else "Клиент").strip() or "Клиент"
        
        if reminder_type == "hour_before":
            message = (
                f"⏰ {client_name}, напоминание: ваша запись через час!\n\n"
                f"Услуга: {service_name}\n"
                f"Дата: {date}\n"
                f"Время: {time}\n"
                f"Цена: {price} ₽\n\n"
                f"Спасибо за ваш выбор!"
            )
            markup = None
        elif reminder_type == "completion_immediate":
            message = (
                f"{client_name}, спасибо за доверие! Вам понравилась процедура?\n\n"
                f"Пожалуйста, оставьте свой отзыв о работе мастера\n"
                f"(фото с комментарием приветствуются!)\n\n"
                f"📅 Пора повторить процедуру?\n"
                f"Рекомендуем снова записаться на:\n"
                f"🛍️ {service_name}\n"
                f"💰 Цена: {price} ₽"
            )
            # Add inline buttons for better UX
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"feedback:{appointment_id}"),
                    InlineKeyboardButton(text="📅 Записаться", callback_data="booking:start"),
                ],
            ])
        elif reminder_type == "completion":
            message = (
                f"{client_name}, спасибо за доверие! Вам понравилась процедура?\n\n"
                f"📅 Пора повторить процедуру!\n"
                f"Рекомендуем записаться на:\n"
                f"🛍️ {service_name}\n"
                f"💰 Цена: {price} ₽"
            )
            # Add inline buttons for better UX
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"feedback:{appointment_id}"),
                    InlineKeyboardButton(text="📅 Записаться", callback_data="booking:start"),
                ],
            ])
        else:  # "before" or default
            message = (
                f"🔔 {client_name}, напоминание о записи завтра!\n\n"
                f"Услуга: {service_name}\n"
                f"Дата: {format_date_for_display(date)}\n"
                f"Время: {time}\n"
                f"Цена: {price} ₽\n\n"
                f"Ждем с нетерпением!"
            )
            markup = None
        
        try:
            logger.info(f"Sending {reminder_type} reminder for appointment {appointment_id} to user {telegram_id}")
            await bot.send_message(
                chat_id=telegram_id,
                text=message,
                reply_markup=markup,
            )
            logger.info(f"✅ Successfully sent {reminder_type} reminder for appointment {appointment_id}")
        except Exception as e:
            logger.error(f"❌ Error sending {reminder_type} reminder for appointment {appointment_id}: {e}")
            logger.error(f"Error sending reminder: {e}")

    @staticmethod
    async def notify_appointment_created(
        bot: Bot,
        telegram_id: int,
        service_name: str,
        date: str,
        time: str,
        client_name: str = "",
        phone: str = "",
        note: str = "",
    ) -> None:
        """Notify user about successful appointment creation with full details."""
        logger.info(f"notify_appointment_created called for user {telegram_id}, appointment: {service_name} on {date} at {time}")
        
        # Get client name from DB if not provided
        if not client_name:
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT first_name FROM clients WHERE telegram_id = ?",
                        (telegram_id,),
                    )
                    row = await cursor.fetchone()
            client_name = (row[0] if row else "").strip() or "Клиент"
        else:
            client_name = (client_name or "").strip() or "Клиент"
        
        message = (
            f"НОВАЯ ЗАПИСЬ\n\n"
            f"✨ Услуга: {service_name}\n"
            f"📅 Дата: {date}\n"
            f"🕐 Время: {time}\n"
        )
        
        if note:
            message += f"\n💬 Пожелания: {note}\n"
        else:
            message += f"\n💬 Пожелания: Нет\n"
        
        message += "\nСпасибо за выбор нашего салона!"
        
        logger.info(f"Sending notification message to {telegram_id}: {message[:100]}...")
        try:
            result = await bot.send_message(
                chat_id=telegram_id,
                text=message,
            )
            logger.info(f"Successfully sent notification to {telegram_id}, message_id={result.message_id}")
        except Exception as e:
            logger.error(f"Error sending appointment creation notification to {telegram_id}: {e}", exc_info=True)
    
    @staticmethod
    async def notify_admin_appointment_created(
        appointment_id: int,
        first_name: str,
        last_name: str,
        service_name: str,
        date: str,
        time: str,
        phone: str,
        note: str = "",
    ) -> None:
        """Notify admin about new appointment. Prevents duplicate notifications."""
        from ..config import ADMIN_BOT_TOKEN, ADMIN_IDS
        from ..bot import create_bot
        
        # Check if notification already sent
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT admin_notification_sent FROM appointments WHERE id = ?",
                    (appointment_id,),
                )
                row = await cursor.fetchone()
                if row and row[0]:  # Notification already sent
                    return
        
        # Normalize data
        first_name = (first_name or "").strip()
        last_name = (last_name or "").strip()
        phone = (phone or "").strip()
        note = (note or "").strip()
        
        # Build client name
        client_name = first_name
        if last_name:
            client_name += f" {last_name}"
        if not client_name:
            client_name = "Неизвестный клиент"
        
        message = (
            f"📋 НОВАЯ ЗАПИСЬ\n\n"
            f"👤 Клиент: {client_name}\n"
        )
        
        if phone:
            message += f"📱 Телефон: {phone}\n"
        
        message += (
            f"✨ Услуга: {service_name}\n"
            f"📅 Дата: {date}\n"
            f"🕐 Время: {time}"
        )
        
        if note:
            message += f"\n💬 Пожелания: {note}"
        
        admin_bot = create_bot(ADMIN_BOT_TOKEN)
        try:
            for admin_id in ADMIN_IDS:
                await admin_bot.send_message(
                    chat_id=admin_id,
                    text=message,
                )
            
            # Mark notification as sent
            async with get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "UPDATE appointments SET admin_notification_sent = 1 WHERE id = ?",
                        (appointment_id,),
                    )
                    await connection.commit()
        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")
        finally:
            await admin_bot.session.close()
    
    @staticmethod
    async def notify_admin_appointment_cancelled(
        first_name: str,
        last_name: str,
        service_name: str,
        date: str,
        time: str,
        phone: str = None,
        reason: str = "",
    ) -> None:
        """Notify admin about cancelled appointment."""
        from ..config import ADMIN_BOT_TOKEN, ADMIN_IDS
        from ..bot import create_bot
        
        # Normalize data
        first_name = (first_name or "").strip()
        last_name = (last_name or "").strip()
        phone = (phone or "").strip()
        
        # Build client name
        client_name = first_name
        if last_name:
            client_name += f" {last_name}"
        if not client_name:
            client_name = "Неизвестный клиент"
        
        message = (
            f"❌ ОТМЕНА ЗАПИСИ\n\n"
            f"👤 Клиент: {client_name}\n"
        )
        
        if phone:
            message += f"📱 Телефон: {phone}\n"
        
        message += (
            f"✨ Услуга: {service_name}\n"
            f"📅 Дата: {date}\n"
            f"🕐 Время: {time}"
        )
        
        if reason:
            message += f"\nПричина: {reason}"
        
        admin_bot = create_bot(ADMIN_BOT_TOKEN)
        try:
            for admin_id in ADMIN_IDS:
                await admin_bot.send_message(
                    chat_id=admin_id,
                    text=message,
                )
        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")
        finally:
            await admin_bot.session.close()
    
    @staticmethod
    async def notify_admin_appointment_rescheduled(
        first_name: str,
        last_name: str,
        service_name: str,
        old_date: str,
        old_time: str,
        new_date: str,
        new_time: str,
        phone: str = None,
    ) -> None:
        """Notify admin about rescheduled appointment."""
        from ..config import ADMIN_BOT_TOKEN, ADMIN_IDS
        from ..bot import create_bot
        
        # Normalize data
        first_name = (first_name or "").strip()
        last_name = (last_name or "").strip()
        phone = (phone or "").strip()
        
        # Build client name
        client_name = first_name
        if last_name:
            client_name += f" {last_name}"
        if not client_name:
            client_name = "Неизвестный клиент"
        
        message = (
            f"📆 ПЕРЕНОС ЗАПИСИ\n\n"
            f"👤 Клиент: {client_name}\n"
        )
        
        if phone:
            message += f"📱 Телефон: {phone}\n"
        
        message += (
            f"✨ Услуга: {service_name}\n"
            f"❌ Было: {old_date} {old_time}\n"
            f"✅ Теперь: {new_date} {new_time}"
        )
        
        admin_bot = create_bot(ADMIN_BOT_TOKEN)
        try:
            for admin_id in ADMIN_IDS:
                await admin_bot.send_message(
                    chat_id=admin_id,
                    text=message,
                )
        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")
        finally:
            await admin_bot.session.close()
    
    @staticmethod
    async def notify_admin_new_feedback(
        client_name: str,
        text: str,
        has_photo: bool = False,
    ) -> None:
        """Notify admin about new feedback."""
        from ..config import ADMIN_BOT_TOKEN, ADMIN_IDS
        from ..bot import create_bot
        
        # Normalize client name
        client_name = (client_name or "Анонимный клиент").strip() or "Анонимный клиент"
        
        message = (
            f"💬 НОВЫЙ ОТЗЫВ\n\n"
            f"👤 От: {client_name}\n"
            f"📝 Отзыв: {text}"
        )
        
        if has_photo:
            message += "\n📸 Фото приложено"
        
        admin_bot = create_bot(ADMIN_BOT_TOKEN)
        try:
            for admin_id in ADMIN_IDS:
                await admin_bot.send_message(
                    chat_id=admin_id,
                    text=message,
                )
        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")
        finally:
            await admin_bot.session.close()
