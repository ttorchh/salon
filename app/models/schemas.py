from dataclasses import dataclass

@dataclass
class ServiceItem:
    id: int
    name: str
    description: str
    price: int
    duration: int

@dataclass
class Client:
    id: int
    telegram_id: int
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None

@dataclass
class Appointment:
    id: int
    client_id: int
    service_id: int
    appointment_date: str
    appointment_time: str
    note: str | None = None
    status: str = "planned"
    created_at: str = ""

@dataclass
class Feedback:
    id: int
    appointment_id: int | None
    telegram_id: int
    rating: int | None = None
    comment: str | None = None
    created_at: str = ""

@dataclass
class ScheduleSettings:
    mode: str  # "cycle", "weekdays", or "free"
    cycle_pattern: str | None = None  # e.g. "5/2", "2/2"
    cycle_start_date: str | None = None  # e.g. "2026-04-20"
    working_days: str | None = None  # e.g. "0,1,2,3,4" (0=Mon, 6=Sun)
    interval_minutes: int = 30
    break_start: str | None = None  # e.g. "13:00"
    break_end: str | None = None  # e.g. "14:00"
    start_time: str = "10:00"  # Время открытия (начало разлиновки)
    end_time: str = "20:00"  # Время закрытия (конец разлиновки)
