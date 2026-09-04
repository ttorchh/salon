from datetime import datetime
from pathlib import Path

from ..database import get_connection
from ..config import SERVICE_IMAGES_DIR

DEFAULT_SERVICES = [
    {
        "name": "Тестовая услуга 10",
        "description": "Стартовая тестовая услуга длительностью 10 минут.",
        "price": 599,
        "duration": 10,
    },
    {
        "name": "Тестовая услуга 30",
        "description": "Стандартная тестовая услуга длительностью 30 минут.",
        "price": 999,
        "duration": 30,
    },
    {
        "name": "Тестовая услуга 75",
        "description": "Стандартная тестовая услуга длительностью 75 минут.",
        "price": 1499,
        "duration": 75,
    },
]

class CatalogService:
    @staticmethod
    async def seed_services() -> None:
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                for item in DEFAULT_SERVICES:
                    # Check if service with this name already exists
                    await cursor.execute("SELECT id FROM services WHERE name = ?", (item["name"],))
                    existing = await cursor.fetchone()
                    if not existing:
                        await cursor.execute(
                            "INSERT INTO services (name, description, price, duration) VALUES (?, ?, ?, ?)",
                            (item["name"], item["description"], item["price"], item["duration"]),
                        )
                await connection.commit()

    @staticmethod
    async def restore_service_photos() -> None:
        """Restore service photo references from file system after DB recreation."""
        if not SERVICE_IMAGES_DIR.exists():
            return
        
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                # Scan for existing service photos
                for photo_file in SERVICE_IMAGES_DIR.glob("service_*.jpg"):
                    try:
                        # Extract service_id from filename (e.g., "service_3.jpg" -> 3)
                        service_id = int(photo_file.stem.split("_")[1])
                        
                        # Check if service exists
                        await cursor.execute("SELECT id FROM services WHERE id = ?", (service_id,))
                        service = await cursor.fetchone()
                        
                        if service:
                            # Update service with photo reference if not already set
                            await cursor.execute(
                                "UPDATE services SET photo_file_id = ? WHERE id = ? AND photo_file_id IS NULL",
                                (photo_file.name, service_id),
                            )
                    except (ValueError, IndexError):
                        # Skip files that don't match the pattern
                        continue
                
                await connection.commit()

    @staticmethod
    async def list_services() -> list[dict]:
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT id, name, description, price, duration, photo_file_id FROM services ORDER BY id")
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

    @staticmethod
    async def get_service(service_id: int) -> dict | None:
        async with get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT id, name, description, price, duration, photo_file_id FROM services WHERE id = ?",
                    (service_id,),
                )
                row = await cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": row[3],
                "duration": row[4],
                "photo_file_id": row[5],
            }
        return None
