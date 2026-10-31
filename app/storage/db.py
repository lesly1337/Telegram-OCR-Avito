import aiosqlite
import logging
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id),
    avito_id TEXT UNIQUE,
    url TEXT NOT NULL,
    title TEXT,
    category TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER REFERENCES listings(id),
    url TEXT NOT NULL,
    ocr_text TEXT,
    confidence REAL
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER REFERENCES listings(id),
    entity_type TEXT NOT NULL, -- IMEI, MAC, SN, PASSWORD
    value TEXT NOT NULL,
    source_image_id INTEGER REFERENCES images(id),
    confidence REAL,
    UNIQUE(listing_id, entity_type, value)
);
"""

async def init_db():
    async with aiosqlite.connect(settings.db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info(f"База данных инициализирована: {settings.db_path}")

async def create_job(user_id: int, query: str) -> int:
    """Создает задачу парсинга и возвращает её ID."""
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute(
            "INSERT INTO jobs (user_id, query) VALUES (?, ?)",
            (user_id, query)
        )
        await db.commit()
        return cursor.lastrowid

# Здесь позже добавим функции сохранения объявлений и сущностей