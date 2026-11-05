"""Открыть Avito в видимом браузере с профилем и прокси бота."""

import asyncio

from playwright.async_api import async_playwright

from app.avito.collector import AvitoCollector


async def main() -> int:
    collector = AvitoCollector()
    collector.headless = False
    try:
        async with async_playwright() as playwright:
            context, page = await collector._init_browser(playwright)
            closed = asyncio.Event()
            context.on("close", lambda _: closed.set())
            try:
                await page.goto(
                    f"{collector.base_url}/rossiya?q=iphone",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                print("Пройдите проверку Avito в открывшемся окне, затем закройте браузер.", flush=True)
                await closed.wait()
            finally:
                if not closed.is_set():
                    await context.close()
        print("Браузер закрыт. Профиль сохранён; можно снова запустить бота.")
        return 0
    except Exception as exc:
        # Исключения Playwright могут содержать адреса с учётными данными.
        print(f"Не удалось открыть браузер: {type(exc).__name__}.")
        print("Проверьте доступность графического интерфейса и убедитесь, что бот остановлен.")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
