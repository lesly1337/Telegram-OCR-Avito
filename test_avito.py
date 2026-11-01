import asyncio
import logging
from app.avito.collector import AvitoCollector

logging.basicConfig(level=logging.INFO)

async def main():
    collector = AvitoCollector()
    # Ищем 3 объявления
    results = await collector.search("iphone 13", limit=3)
    
    if not results:
        print("\n❌ Ничего не найдено. Avito нас заблокировал или изменил верстку.")
    else:
        print("\n✅ Результаты:")
        for i, item in enumerate(results, 1):
            print(f"{i}. {item['title']}")
            print(f"   URL: {item['url']}")
            print(f"   ID: {item['avito_id']}")

if __name__ == "__main__":
    asyncio.run(main())