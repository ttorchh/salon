"""Centralized data paths for the Nails bot."""

from pathlib import Path

from .config import DATA_DIR, IMAGES_DIR, SERVICE_IMAGES_DIR, FEEDBACK_IMAGES_DIR, EXPORTS_DIR, DB_PATH, LOGS_DIR, BACKUPS_DIR


def get_data_dir() -> Path:
    """Get the main data directory."""
    return DATA_DIR


def get_images_dir() -> Path:
    """Get the images root directory."""
    return IMAGES_DIR


def get_service_images_dir() -> Path:
    """Get the service images directory."""
    return SERVICE_IMAGES_DIR


def get_feedback_images_dir() -> Path:
    """Get the feedback images directory."""
    return FEEDBACK_IMAGES_DIR


def get_exports_dir() -> Path:
    """Get the exports directory."""
    return EXPORTS_DIR


def get_db_path() -> Path:
    """Get the database file path."""
    return Path(DB_PATH)

def get_logs_dir() -> Path:
    return LOGS_DIR

def get_backups_dir() -> Path:
    return BACKUPS_DIR

__all__ = [
    "get_data_dir",
    "get_images_dir",
    "get_service_images_dir",
    "get_feedback_images_dir",
    "get_exports_dir",
     "get_db_path",
    "get_logs_dir",
    "get_backups_dir",
    ]
