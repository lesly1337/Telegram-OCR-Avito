import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from curl_cffi import CurlOpt
from curl_cffi import requests as curl_requests
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from app.config import settings

logger = logging.getLogger(__name__)

SEARCH_SELECTOR = 'a[data-marker="item-title"]'
GALLERY_SELECTOR = '[data-marker*="gallery"], [data-marker*="image-frame"], [data-marker*="image-slider"]'


class AvitoAccessBlockedError(RuntimeError):

class AvitoCollector:
    def __init__(self):
        self.base_url = settings.avito_base_url
        self.headless = settings.avito_headless
        self.proxy_url = settings.proxy_url
        self.user_data_dir = "data/browser_profile"

    def _get_playwright_proxy(self) -> dict[str, str] | None:
        if not self.proxy_url:
            return None
        parsed = urlsplit(self.proxy_url)
        host = parsed.hostname
        if not parsed.scheme or not host or not parsed.port:
            raise ValueError("PROXY_URL должен содержать протокол, адрес и порт")
        if ":" in host:
            host = f"[{host}]"
        proxy = {"server": f"{parsed.scheme}://{host}:{parsed.port}"}
        if parsed.username is not None:
            proxy["username"] = unquote(parsed.username)
        if parsed.password is not None:
            proxy["password"] = unquote(parsed.password)
        return proxy

    def _curl_proxy_options(self) -> dict:
        if self.proxy_url:
            return {"proxies": {"http": self.proxy_url, "https": self.proxy_url},
                    "curl_options": {CurlOpt.NOPROXY: ""}}
        return {"curl_options": {CurlOpt.PROXY: ""}}

    async def check_proxy(self) -> bool:
        if not self.proxy_url:
            return True
        logger.info("Проверка доступности прокси Avito...")
        try:
            response = await asyncio.to_thread(
                curl_requests.get, "https://api.ipify.org?format=json",
                impersonate="chrome110", timeout=10, **self._curl_proxy_options(),
            )
            if response.status_code == 200:
                return True
            logger.error("Прокси Avito не отвечает: HTTP %s", response.status_code)
        except Exception as e:
            logger.error("Ошибка прокси Avito: %s", e)
        return False

    async def _init_browser(self, p):
        context = await p.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            proxy=self._get_playwright_proxy(),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox'],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await Stealth().apply_stealth_async(page)
        return context, page

    async def _diagnose_page(self, page, kind: str) -> None:
        title = await page.title()
        logger.warning("%s не найдены. Заголовок страницы: %s; URL: %s", kind, title, page.url)
        if any(word in title.lower() for word in ("проверка", "доступ ограничен", "captcha")):
            logger.warning("Avito запрашивает проверку. При AVITO_HEADLESS=false решите её в браузере.")
        try:
            path = Path(settings.tmp_dir) / "avito_debug.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(path))
            logger.info("Скриншот страницы: %s", path)
        except Exception as e:
            logger.warning("Не удалось сохранить скриншот: %s", e)

    async def _search_on_page(self, page, query: str, limit: int) -> list[dict[str, Any]]:
        search_url = f"{self.base_url}/rossiya?q={quote(query)}"
        results: list[dict[str, Any]] = []
        seen_items: set[str] = set()
        seen_pages: set[str] = set()
        next_url = search_url
        while next_url and next_url not in seen_pages and len(results) < limit:
            seen_pages.add(next_url)
            logger.info("Переход по ссылке: %s", next_url)
            await page.goto(next_url, wait_until="domcontentloaded", timeout=60000)
            if not self.headless:
                logger.info("Ожидание результатов до 30 секунд; при необходимости решите проверку в браузере.")
            try:
                
                await page.wait_for_selector(SEARCH_SELECTOR, timeout=30000)
            except PlaywrightTimeoutError:
                title = (await page.title()).lower()
                await self._diagnose_page(page, "Карточки")
                if any(word in title for word in ("проверка", "доступ ограничен", "captcha")):
                    raise AvitoAccessBlockedError("Avito запросил проверку доступа")
                break
            items = await page.query_selector_all(SEARCH_SELECTOR)
            logger.info("Найдено карточек на странице: %s", len(items))
            for item in items:
                url = await item.get_attribute("href")
                if not url:
                    continue
                parts = urlsplit(urljoin(self.base_url, url))
                clean_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
                if clean_url in seen_items:
                    continue
                seen_items.add(clean_url)
                match = re.search(r'_(\d+)(?:\.html)?$', parts.path)
                results.append({
                    "avito_id": match.group(1) if match else None,
                    "url": clean_url,
                    "title": (await item.inner_text()).strip(),
                    "category": "Avito Item",
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
            next_link = await page.query_selector('a[data-marker="pagination-button/next"]')
            href = await next_link.get_attribute("href") if next_link else None
            next_url = urljoin(page.url, href) if href else None
        if len(results) < limit:
            logger.warning("Удалось найти %s из %s объявлений", len(results), limit)
        return results

    async def search(self, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        if limit is None:
            limit = settings.avito_max_items_default
        if limit <= 0 or not await self.check_proxy():
            return []
        logger.info("Запуск поиска на Avito: '%s', лимит: %s", query, limit)
        async with async_playwright() as p:
            context, page = await self._init_browser(p)
            try:
                return await self._search_on_page(page, query, limit)
            except AvitoAccessBlockedError:
                raise
            except Exception:
                logger.exception("Ошибка при поиске Avito")
                return []
            finally:
                await context.close()

    async def _images_on_page(self, page, url: str) -> list[str]:
        logger.info("Извлечение картинок из: %s", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        title = (await page.title()).lower()
        challenge = any(word in title for word in ("проверка", "доступ ограничен", "captcha"))
        if challenge and not self.headless:
            logger.warning("Avito запрашивает проверку. Решите её в браузере; ожидание до 30 секунд.")
        try:
            await page.wait_for_selector(GALLERY_SELECTOR, timeout=30000 if challenge else 10000, state="attached")
        except PlaywrightTimeoutError:
            current_title = (await page.title()).lower()
            if challenge and any(word in current_title for word in ("проверка", "доступ ограничен", "captcha")):
                await self._diagnose_page(page, "Картинки")
                return []
                
        data = await page.evaluate('''selector => {
            const urls = [];
            for (const gallery of document.querySelectorAll(selector)) {
                for (const el of [gallery, ...gallery.querySelectorAll('img, source, [style]')]) {
                    const srcset = el.getAttribute('srcset') || el.getAttribute('data-srcset');
                    if (srcset) {
                        const variants = srcset.split(',').map(s => s.trim().split(/\\s+/)[0]);
                        urls.push(variants[variants.length - 1]);
                    } else {
                        urls.push(el.getAttribute('data-src') || el.getAttribute('src'));
                    }
                    const style = el.getAttribute('style') || '';
                    for (const match of style.matchAll(/url\\(["']?([^"')]+)["']?\\)/g)) urls.push(match[1]);
                }
            }
            const meta = document.querySelector('meta[property="og:image"]');
            return {urls, og: meta && meta.content,
                jsonld: [...document.querySelectorAll('script[type="application/ld+json"]')].map(el => el.textContent)};
        }''', GALLERY_SELECTOR)
        candidates = list(data["urls"])
        for raw in data["jsonld"]:
            try:
                candidates.extend(_jsonld_images(json.loads(raw)))
            except (ValueError, TypeError):
                continue
        if data["og"]:
            candidates.append(data["og"])
        images = []
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate:
                continue
            image_url = urljoin(page.url, candidate)
            scheme = urlsplit(image_url).scheme
            
            if scheme in ("http", "https") and "img.avito.st/image/" in image_url:
                if image_url not in images:
                    images.append(image_url)
        if not images:
            await self._diagnose_page(page, "Картинки")
        logger.info("Найдено %s картинок.", len(images))
        return images

    async def get_images_from_listing(self, url: str) -> list[str]:
        async with async_playwright() as p:
            context, page = await self._init_browser(p)
            try:
                return await self._images_on_page(page, url)
            except Exception:
                logger.exception("Ошибка при извлечении картинок: %s", url)
                return []
            finally:
                await context.close()

    async def collect(self, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        
        if limit is None:
            limit = settings.avito_max_items_default
        if limit <= 0 or not await self.check_proxy():
            return []
        async with async_playwright() as p:
            context, page = await self._init_browser(p)
            try:
                try:
                    results = await self._search_on_page(page, query, limit)
                except AvitoAccessBlockedError:
                    raise
                except Exception:
                    logger.exception("Ошибка при поиске Avito")
                    return []
                for item in results:
                    try:
                        item["images"] = await self._images_on_page(page, item["url"])
                    except Exception:
                        logger.exception("Ошибка при обработке объявления: %s", item["url"])
                        item["images"] = []
                return results
            finally:
                await context.close()

    async def download_image(self, image_url: str, save_path: str) -> bool:
        try:
            response = await asyncio.to_thread(
                curl_requests.get, image_url, impersonate="chrome110", timeout=15,
                **self._curl_proxy_options(),
            )
            if response.status_code == 200:
                Path(save_path).write_bytes(response.content)
                return True
            logger.warning("Не удалось скачать %s: HTTP %s", image_url, response.status_code)
        except Exception as e:
            logger.error("Ошибка скачивания %s: %s", image_url, e)
        return False


def _jsonld_images(value: Any) -> list[str]:
    
    if isinstance(value, list):
        return [image for item in value for image in _jsonld_images(item)]
    if not isinstance(value, dict):
        return []
    result = []
    types = value.get("@type", [])
    if isinstance(types, str):
        types = [types]
    if any(t in ("Product", "IndividualProduct") for t in types):
        images = value.get("image", [])
        if isinstance(images, (str, dict)):
            images = [images]
        if isinstance(images, list):
            for image in images:
                if isinstance(image, str):
                    result.append(image)
                elif isinstance(image, dict):
                    image_url = image.get("url") or image.get("contentUrl")
                    if isinstance(image_url, str):
                        result.append(image_url)
    if "@graph" in value:
        result.extend(_jsonld_images(value["@graph"]))
    return result
