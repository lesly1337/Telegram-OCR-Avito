from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from scripts import check_proxy_routes


@pytest.mark.asyncio
async def test_telegram_check_uses_its_own_proxy_and_hides_errors(monkeypatch, capsys):
    monkeypatch.setattr(settings, "telegram_proxy_url", "socks5://user:secret@localhost:1080")
    session = SimpleNamespace(_connector_init={}, close=AsyncMock())
    session_factory = MagicMock(return_value=session)
    monkeypatch.setattr(check_proxy_routes, "AiohttpSession", session_factory)
    monkeypatch.setattr(check_proxy_routes, "Bot", lambda **kwargs: SimpleNamespace(get_me=AsyncMock(side_effect=RuntimeError("secret"))))

    assert not await check_proxy_routes.check_telegram()
    session_factory.assert_called_once_with(proxy=settings.telegram_proxy_url, timeout=15)
    session.close.assert_awaited_once()
    assert "secret" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_avito_country_check_uses_avito_proxy(monkeypatch, capsys):
    monkeypatch.setattr(settings, "proxy_url", "http://user:secret@avito-proxy:3128")
    response = MagicMock()
    response.json.return_value = {"success": True, "country_code": "RU"}
    get = MagicMock(return_value=response)
    monkeypatch.setattr(check_proxy_routes.requests, "get", get)

    assert await check_proxy_routes.check_avito_country()
    assert get.call_args.kwargs["proxies"]["https"] == settings.proxy_url
    assert "secret" not in capsys.readouterr().out
