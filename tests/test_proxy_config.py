from unittest.mock import AsyncMock, MagicMock

import pytest
from curl_cffi import CurlOpt

from app.avito.collector import AvitoCollector
from app.config import settings


def test_avito_proxy_is_independent_of_telegram_and_decodes_credentials(monkeypatch):
    monkeypatch.setattr(settings, "proxy_url", "http://user:pass%40word@avito-proxy:3128")
    monkeypatch.setattr(settings, "telegram_proxy_url", "http://telegram-proxy:3128")
    collector = AvitoCollector()

    assert collector._get_playwright_proxy() == {
        "server": "http://avito-proxy:3128", "username": "user", "password": "pass@word"
    }
    assert collector._curl_proxy_options() == {
        "proxies": {"http": settings.proxy_url, "https": settings.proxy_url},
        "curl_options": {CurlOpt.NOPROXY: ""},
    }


def test_no_avito_proxy_ignores_global_proxy_environment(monkeypatch):
    monkeypatch.setattr(settings, "proxy_url", "")
    monkeypatch.setenv("HTTPS_PROXY", "http://unrelated-proxy:3128")
    collector = AvitoCollector()
    assert collector._get_playwright_proxy() is None
    assert collector._curl_proxy_options() == {"curl_options": {CurlOpt.PROXY: ""}}


@pytest.mark.asyncio
async def test_search_fails_gracefully_when_proxy_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "proxy_url", "http://avito-proxy:3128")
    collector = AvitoCollector()
    monkeypatch.setattr("app.avito.collector.curl_requests.get", MagicMock(side_effect=OSError("unavailable")))
    collector._init_browser = AsyncMock()
    assert await collector.search("iphone", 1) == []
    collector._init_browser.assert_not_awaited()
