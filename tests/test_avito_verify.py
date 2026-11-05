from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import avito_verify


@pytest.mark.asyncio
async def test_verification_uses_visible_browser_and_waits_for_close(monkeypatch, capsys):
    context = MagicMock()
    context.close = AsyncMock()
    page = MagicMock()

    async def close_window(*args, **kwargs):
        context.on.call_args.args[1](context)

    page.goto = AsyncMock(side_effect=close_window)
    collector = MagicMock(base_url="https://www.avito.ru", headless=True)
    collector._init_browser = AsyncMock(return_value=(context, page))
    monkeypatch.setattr(avito_verify, "AvitoCollector", lambda: collector)
    monkeypatch.setattr(avito_verify, "async_playwright", lambda: AsyncMock())

    assert await avito_verify.main() == 0
    assert collector.headless is False
    assert page.goto.await_args.args[0] == "https://www.avito.ru/rossiya?q=iphone"
    context.close.assert_not_awaited()
    assert "Профиль сохранён" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_verification_hides_browser_errors(monkeypatch, capsys):
    collector = MagicMock()
    collector._init_browser = AsyncMock(side_effect=RuntimeError("secret"))
    monkeypatch.setattr(avito_verify, "AvitoCollector", lambda: collector)
    monkeypatch.setattr(avito_verify, "async_playwright", lambda: AsyncMock())

    assert await avito_verify.main() == 1
    assert "secret" not in capsys.readouterr().out
