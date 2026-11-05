import runpy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_module_start_initializes_database_and_starts_polling(monkeypatch, tmp_path):
    import aiogram
    import aiogram.client.session.aiohttp
    import app.storage.db as db
    from app.config import settings

    monkeypatch.setattr(settings, "db_path", tmp_path / "db" / "app.db")
    monkeypatch.setattr(settings, "tmp_dir", tmp_path / "tmp")
    monkeypatch.setattr(settings, "telegram_proxy_url", "http://telegram-proxy:3128")
    monkeypatch.setattr(settings, "proxy_url", "http://avito-proxy:3128")
    init_db = AsyncMock()
    monkeypatch.setattr(db, "init_db", init_db)
    bot = MagicMock(delete_webhook=AsyncMock())
    dispatcher = MagicMock(start_polling=AsyncMock())
    session = MagicMock(_connector_init={}, close=AsyncMock())
    monkeypatch.setattr(aiogram, "Bot", MagicMock(return_value=bot))
    monkeypatch.setattr(aiogram, "Dispatcher", MagicMock(return_value=dispatcher))
    session_factory = MagicMock(return_value=session)
    monkeypatch.setattr(aiogram.client.session.aiohttp, "AiohttpSession", session_factory)

    runpy.run_module("app.main", run_name="__main__")

    init_db.assert_awaited_once()
    session_factory.assert_called_once_with(proxy="http://telegram-proxy:3128", timeout=120.0)
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
    dispatcher.start_polling.assert_awaited_once_with(bot)
    session.close.assert_awaited_once()
    assert settings.db_path.parent.is_dir()
    assert settings.tmp_dir.is_dir()


@pytest.mark.asyncio
async def test_query_reuses_cached_ocr_results(monkeypatch, tmp_path):
    import app.main as main
    from app.config import settings

    monkeypatch.setattr(settings, "db_path", tmp_path / "app.db")
    monkeypatch.setattr(settings, "tmp_dir", tmp_path)
    await main.init_db()
    monkeypatch.setattr(main, "parse_user_request", AsyncMock(return_value={"query": "iphone", "limit": 1}))
    collector = MagicMock()
    collector.search = AsyncMock(return_value=[{"avito_id": "123", "url": "https://example.com/item_123", "title": "iPhone"}])
    collector.get_images_from_listing = AsyncMock(return_value=["https://example.com/photo.jpg"])
    collector.download_image = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "AvitoCollector", lambda: collector)
    ocr = MagicMock(return_value={"combined": "serial"})
    monkeypatch.setattr(main, "extract_text_from_image", ocr)
    monkeypatch.setattr(main, "extract_all", lambda text: {"IMEI": [], "SN": ["serial"], "MAC": [], "PASSWORD": []})
    status = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
    message = SimpleNamespace(text="iphone", from_user=SimpleNamespace(id=1), answer=AsyncMock(return_value=status), answer_document=AsyncMock())

    await main.handle_query(message)
    await main.handle_query(message)

    ocr.assert_called_once()
    assert message.answer_document.await_count == 2
    cached = await main.get_cached_listing("123")
    assert cached["entities"]["SN"] == ["serial"]


@pytest.mark.asyncio
@pytest.mark.parametrize("images,downloads", [([], []), (["one", "two"], [True, False])])
async def test_failed_or_missing_photos_are_not_cached(monkeypatch, tmp_path, images, downloads):
    import app.main as main
    from app.config import settings

    monkeypatch.setattr(settings, "tmp_dir", tmp_path)
    monkeypatch.setattr(main, "parse_user_request", AsyncMock(return_value={"query": "iphone", "limit": 1}))
    monkeypatch.setattr(main, "create_job", AsyncMock(return_value=1))
    monkeypatch.setattr(main, "get_cached_listing", AsyncMock(return_value=None))
    save_cache = AsyncMock()
    monkeypatch.setattr(main, "save_listing_to_cache", save_cache)
    monkeypatch.setattr(main, "extract_text_from_image", lambda path: {"combined": ""})
    monkeypatch.setattr(main, "extract_all", lambda text: {"IMEI": [], "SN": [], "MAC": [], "PASSWORD": []})
    collector = MagicMock(
        search=AsyncMock(return_value=[{"avito_id": "123", "url": "https://example.com/item_123", "title": "iPhone"}]),
        get_images_from_listing=AsyncMock(return_value=images),
        download_image=AsyncMock(side_effect=downloads),
    )
    monkeypatch.setattr(main, "AvitoCollector", lambda: collector)
    status = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
    message = SimpleNamespace(text="iphone", from_user=SimpleNamespace(id=1), answer=AsyncMock(return_value=status), answer_document=AsyncMock())

    await main.handle_query(message)

    save_cache.assert_not_awaited()
    message.answer_document.assert_awaited_once()
