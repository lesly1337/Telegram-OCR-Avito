import asyncio
import logging
import random
import urllib.parse
from typing import List, Dict, Any
from urllib.parse import quote

from playwright.async_api import async_playwright
from curl_cffi import requests as curl_requests

from app.config import settings

logger = logging.getLogger(__name__)

class AvitoCollector:
    def __init__(self):
        self.base_url = settings.avito_base_url
        self.headless = settings.avito_headless
        self.proxy_url = settings.proxy_url

    def _get_playwright_proxy(self) -> Dict[str, str] | None:
        if not self.proxy_url:
            return None
        parsed = urllib.parse.urlparse(self.proxy_url)
        proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
        if parsed.username:
            proxy["username"] = parsed.username
        if parsed.password:
            proxy["password"] = parsed.password
        return proxy

    async def check_proxy(self) -> bool:
        """Проверяет, работает ли прокси и какой IP он выдает."""
        if not self.proxy_url:
            return True # Прокси нет, пропускаем проверку
        
        logger.info("Проверка доступности прокси...")
        try:
            proxies = {"https": self.proxy_url}
            # Используем сервис для проверки IP
            response = curl_requests.get(
                "https://api.ipify.org?format=json", 
                proxies=proxies, 
                impersonate="chrome110", 
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"Прокси работает. Внешний IP: {response.json().get('ip')}")
                return True
            else:
                logger.error(f"Прокси не отвечает. Статус: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Ошибка подключения к прокси: {e}")
            return False

    async def search(self, query: str, limit: int = None) -> List[Dict[str, Any]]:
        if limit is None:
            limit = settings.avito_max_items_default
            
        # Проверяем прокси перед запуском
        if not await self.check_proxy():
            logger.error("Прерывание поиска: прокси недоступен.")
            return []

        logger.info(f"Запуск поиска на Avito: '{query}', лимит: {limit}")
        search_url = f"{self.base_url}/rossiya?q={quote(query)}"
        results = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            
            context_options = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080},
                "extra_http_headers": {
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                }
            }
            
            pw_proxy = self._get_playwright_proxy()
            if pw_proxy:
                context_options["proxy"] = pw_proxy
                logger.info(f"Playwright использует прокси: {pw_proxy['server']}")
            
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            
            try:
                logger.info(f"Переход по ссылке: {search_url}")
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(random.uniform(4.0, 7.0))
                
                items = await page.query_selector_all('a[data-marker="item-title"]')
                if not items:
                    await page.screenshot(path="data/tmp/avito_debug.png")
                    logger.warning("Карточки не найдены. Скриншот сохранен.")
                    return []

                logger.info(f"Найдено карточек: {len(items)}. Обрабатываем...")
                for item in items:
                    if len(results) >= limit:
                        break
                    url = await item.get_attribute("href")
                    title = await item.inner_text()
                    if not url or "/item/" not in url:
                        continue
                    full_url = f"{self.base_url}{url}" if url.startswith("/") else url
                    results.append({
                        "avito_id": url.split("_")[-1].replace(".html", "") if "_" in url else None,
                        "url": full_url,
                        "title": title.strip(),
                        "category": "Avito Item"
                    })
                
                return results
                
            except Exception as e:
                logger.error(f"Ошибка при парсинге Avito: {e}")
                return []
            finally:
                await browser.close()

    async def download_image(self, image_url: str, save_path: str) -> bool:
        """Скачивает картинку, используя прокси (если задан)."""
        try:
            proxies = {"https": self.proxy_url} if self.proxy_url else None
            response = curl_requests.get(
                image_url, 
                impersonate="chrome110", 
                timeout=15,
                proxies=proxies
            )
            if response.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                return True
            else:
                logger.warning(f"Не удалось скачать {image_url}: статус {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Ошибка скачивания {image_url}: {e}")
            return False