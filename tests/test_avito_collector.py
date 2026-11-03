from unittest.mock import AsyncMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.avito.collector import AvitoCollector, _jsonld_images


class Element:
    def __init__(self, href, title=""):
        self.href = href
        self.title = title

    async def get_attribute(self, name):
        return self.href if name == "href" else None

    async def inner_text(self):
        return self.title


class SearchPage:
    def __init__(self):
        self.url = ""
        self.visited = []

    async def goto(self, url, **kwargs):
        self.url = url
        self.visited.append(url)

    async def wait_for_selector(self, *args, **kwargs):
        pass

    async def query_selector_all(self, selector):
        if len(self.visited) == 1:
            return [Element("/item_1?tracking=1", "First"), Element("/item_2", "Second")]
        return [Element("/item_2", "Duplicate"), Element("/item_3", "Third")]

    async def query_selector(self, selector):
        return Element("?q=iphone&p=2") if len(self.visited) == 1 else None


@pytest.mark.asyncio
async def test_search_paginates_deduplicates_and_respects_limit():
    collector = AvitoCollector()
    collector.headless = True
    page = SearchPage()
    results = await collector._search_on_page(page, "iphone", 3)
    assert [item["avito_id"] for item in results] == ["1", "2", "3"]
    assert results[0]["url"] == f"{collector.base_url}/item_1"
    assert len(page.visited) == 2


@pytest.mark.asyncio
async def test_search_zero_limit_does_not_launch_browser():
    collector = AvitoCollector()
    collector.check_proxy = AsyncMock()
    assert await collector.search("iphone", 0) == []
    collector.check_proxy.assert_not_awaited()


@pytest.mark.asyncio
async def test_images_normalize_deduplicate_and_use_product_metadata():
    collector = AvitoCollector()
    page = AsyncMock()
    page.url = "https://www.avito.ru/item_1"
    page.title.return_value = "Объявление"
    page.evaluate.return_value = {
        "urls": ["https://images.example/1.jpg", "https://images.example/1.jpg", "data:image/png;base64,aaa"],
        "og": "/2.jpg",
        "jsonld": ['{"@type":"Product","image":["https://images.example/3.jpg"]}', 'invalid'],
    }
    images = await collector._images_on_page(page, page.url)
    assert images == ["https://images.example/1.jpg", "https://images.example/3.jpg", "https://www.avito.ru/2.jpg"]


@pytest.mark.asyncio
async def test_challenge_reports_missing_images():
    collector = AvitoCollector()
    collector.headless = False
    collector._diagnose_page = AsyncMock()
    page = AsyncMock()
    page.url = "https://www.avito.ru/item_1"
    page.title.return_value = "Доступ ограничен: проверка безопасности"
    page.wait_for_selector.side_effect = PlaywrightTimeoutError("timeout")
    page.evaluate.return_value = {"urls": [], "og": None, "jsonld": []}
    assert await collector._images_on_page(page, page.url) == []
    assert page.wait_for_selector.await_args.kwargs["timeout"] == 30000
    collector._diagnose_page.assert_awaited_once()
    page.evaluate.assert_not_awaited()


def test_jsonld_ignores_non_product_images():
    data = {"@graph": [
        {"@type": "Organization", "image": "logo.jpg"},
        {"@type": "Product", "image": [{"contentUrl": "product.jpg"}]},
    ]}
    assert _jsonld_images(data) == ["product.jpg"]


@pytest.mark.asyncio
async def test_collect_reuses_context_and_continues_after_listing_error(monkeypatch):
    from app.avito import collector as module

    context = AsyncMock()
    page = AsyncMock()
    playwright_context = AsyncMock()
    monkeypatch.setattr(module, "async_playwright", lambda: playwright_context)
    collector = AvitoCollector()
    collector.check_proxy = AsyncMock(return_value=True)
    collector._init_browser = AsyncMock(return_value=(context, page))
    collector._search_on_page = AsyncMock(return_value=[{"url": "first"}, {"url": "second"}])
    collector._images_on_page = AsyncMock(side_effect=[RuntimeError("failed"), ["photo.jpg"]])

    result = await collector.collect("iphone", 2)

    assert result == [{"url": "first", "images": []}, {"url": "second", "images": ["photo.jpg"]}]
    collector._init_browser.assert_awaited_once()
    context.close.assert_awaited_once()
