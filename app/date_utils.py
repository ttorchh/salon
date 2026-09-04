from datetime import date, datetime

ISO_DATE_FORMAT = "%Y-%m-%d"
DISPLAY_DATE_FORMAT = "%d-%m-%Y"
SUPPORTED_DATE_FORMATS = (ISO_DATE_FORMAT, DISPLAY_DATE_FORMAT)


def parse_date_value(date_value: str | date | datetime) -> date:
    """Parse a date value from supported string formats or date objects."""
    if isinstance(date_value, datetime):
        return date_value.date()
    if isinstance(date_value, date):
        return date_value
    if not isinstance(date_value, str):
        raise TypeError(f"Unsupported date value type: {type(date_value).__name__}")

    cleaned = date_value.strip()
    if not cleaned:
        raise ValueError("Date value is empty")

    for fmt in SUPPORTED_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Unsupported date format: {date_value}")


def normalize_date_to_iso(date_value: str | date | datetime) -> str:
    """Convert a supported date value to ISO format."""
    return parse_date_value(date_value).isoformat()


def format_date_for_display(date_value: str | date | datetime) -> str:
    """Convert a supported date value to DD-MM-YYYY for visual output."""
    if date_value in (None, ""):
        return ""

    try:
        return parse_date_value(date_value).strftime(DISPLAY_DATE_FORMAT)
    except (TypeError, ValueError):
        return str(date_value)
