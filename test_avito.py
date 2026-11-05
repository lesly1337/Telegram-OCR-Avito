import argparse
import asyncio
import logging

from app.avito.collector import AvitoAccessBlockedError, AvitoCollector

logging.basicConfig(level=logging.INFO)


async def main(query: str = "iphone 13", limit: int = 1):
    collector = AvitoCollector()
    try:
        results = await collector.collect(query, limit=limit)
    except AvitoAccessBlockedError:
        print("\n❌ Avito запросил проверку. Проверьте прокси или пройдите её в браузере.")
        return

    if not results:
        print("\n❌ Ничего не найдено. Проверьте сообщения выше.")
        return

    for number, item in enumerate(results, 1):
        print(f"\n✅ Объявление {number}: {item['title']}")
        print(f"URL: {item['url']}")
        print(f"Найдено картинок: {len(item['images'])}")
        for i, image in enumerate(item["images"], 1):
            print(f"{i}. {image}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Поиск объявлений Avito и их изображений")
    parser.add_argument("query", nargs="?", default="iphone 13", help="Поисковый запрос")
    parser.add_argument("--limit", type=int, default=1, help="Количество объявлений")
    args = parser.parse_args()
    asyncio.run(main(args.query, args.limit))
