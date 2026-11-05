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


async def get_cached_listing(avito_id: str):
    """Проверяет, есть ли объявление в БД, и возвращает его сущности."""
    if not avito_id:
        return None
        
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        # 1. Ищем объявление
        async with db.execute("SELECT id, url, title FROM listings WHERE avito_id = ?", (avito_id,)) as cursor:
            listing = await cursor.fetchone()
            if not listing:
                return None
                
            listing_id = listing['id']
            
        # 2. Достаем сохраненные сущности
        entities = {"IMEI": [], "SN": [], "MAC": [], "PASSWORD": []}
        async with db.execute("SELECT entity_type, value FROM entities WHERE listing_id = ?", (listing_id,)) as cursor:
            async for row in cursor:
                e_type = row['entity_type']
                if e_type in entities:
                    entities[e_type].append(row['value'])
                    
        return {
            "url": listing['url'],
            "title": listing['title'],
            "entities": entities
        }

async def save_listing_to_cache(job_id: int, avito_id: str, url: str, title: str, entities: dict):
    if not avito_id:
        return
        
    async with aiosqlite.connect(settings.db_path) as db:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO listings (job_id, avito_id, url, title) VALUES (?, ?, ?, ?)",
                (job_id, avito_id, url, title)
            )
            # ID объявления (нового или существующего)
            async with db.execute("SELECT id FROM listings WHERE avito_id = ?", (avito_id,)) as cursor:
                row = await cursor.fetchone()
                listing_id = row[0]
                
            for e_type, values in entities.items():
                for val in values:
                    await db.execute(
                        "INSERT OR IGNORE INTO entities (listing_id, entity_type, value) VALUES (?, ?, ?)",
                        (listing_id, e_type, val)
                    )
            await db.commit()
            logger.info(f"Объявление {avito_id} сохранено в БД.")
        except Exception as e:
            logger.error(f"Ошибка сохранения в БД: {e}")