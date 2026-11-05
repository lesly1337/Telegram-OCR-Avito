from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.avito.collector import AvitoAccessBlockedError, AvitoCollector


@pytest.mark.asyncio
async def test_search_page_reports_access_check():
    collector = AvitoCollector()
    collector.headless = True
    collector._diagnose_page = AsyncMock()
    page = AsyncMock()
    page.title.return_value = "Доступ ограничен: проблема с IP"
    page.wait_for_selector.side_effect = PlaywrightTimeoutError("no cards")

    with pytest.raises(AvitoAccessBlockedError):
        await collector._search_on_page(page, "iphone", 1)

    collector._diagnose_page.assert_awaited_once_with(page, "Карточки")


@pytest.mark.asyncio
async def test_search_propagates_access_check_and_closes_browser(monkeypatch):
    from app.avito import collector as module

    playwright = AsyncMock()
    monkeypatch.setattr(module, "async_playwright", lambda: playwright)
    collector = AvitoCollector()
    collector.check_proxy = AsyncMock(return_value=True)
    context = AsyncMock()
    collector._init_browser = AsyncMock(return_value=(context, AsyncMock()))
    collector._search_on_page = AsyncMock(side_effect=AvitoAccessBlockedError())

    with pytest.raises(AvitoAccessBlockedError):
        await collector.search("iphone", 1)

    context.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_bot_reports_access_check_instead_of_empty_results(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "parse_user_request", AsyncMock(return_value={"query": "iphone", "limit": 1}))
    monkeypatch.setattr(main, "create_job", AsyncMock(return_value=1))
    collector = SimpleNamespace(search=AsyncMock(side_effect=AvitoAccessBlockedError()))
    monkeypatch.setattr(main, "AvitoCollector", lambda: collector)
    status = SimpleNamespace(edit_text=AsyncMock())
    message = SimpleNamespace(text="iphone", from_user=SimpleNamespace(id=1), answer=AsyncMock(return_value=status))

    await main.handle_query(message)

    assert "Avito ограничил доступ" in status.edit_text.await_args.args[0]
