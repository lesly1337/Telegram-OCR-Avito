import json
import logging
import asyncio
from typing import Dict, Any
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings

logger = logging.getLogger(__name__)

llm = ChatOllama(
    base_url=settings.ollama_base_url,
    model=settings.ollama_model,
    format="json",
    temperature=0.0
)

system_prompt = """Ты — ассистент Telegram-бота, который ищет объявления на Avito и вытаскивает данные с фото.
Твоя задача — извлечь параметры из запроса пользователя и вернуть ТОЛЬКО валидный JSON.

Схема JSON:
{{
  "query": "поисковый запрос для Avito (например, 'iphone 13')",
  "limit": {default_limit},
  "fields": ["IMEI", "SN", "MAC", "PASSWORD"],
  "category_hint": "iphone" | "router" | "laptop" | "other"
}}

Если пользователь не указал количество, используй {default_limit}.
Если не указал поля, используй все: ["IMEI", "SN", "MAC", "PASSWORD"].
Если не указал категорию, выбери "other".

Примеры:
- "найди 15 iphone 13, нужны sn и imei" -> {{"query": "iphone 13", "limit": 15, "fields": ["SN", "IMEI"], "category_hint": "iphone"}}
- "ищу роутеры tp-link, нужен mac и пароль" -> {{"query": "tp-link роутер", "limit": {default_limit}, "fields": ["MAC", "PASSWORD"], "category_hint": "router"}}
- "привет" -> {{"query": null, "limit": null, "fields": [], "category_hint": null}}
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("user", "{user_input}")
])

async def parse_user_request(text: str) -> Dict[str, Any]:
    chain = prompt | llm
    try:
        response = await asyncio.wait_for(
            chain.ainvoke({
                "user_input": text,
                "default_limit": settings.avito_max_items_default
            }),
            timeout=40.0
        )
        result = json.loads(response.content)
        logger.info(f"LLM parsed: {result}")
        return result
    except asyncio.TimeoutError:
        logger.error("Ollama таймаут (40 сек)")
        return _fallback(text)
    except Exception as e:
        logger.error(f"Ошибка LLM: {e}")
        return _fallback(text)

def _fallback(text: str) -> Dict[str, Any]:
    return {
        "query": text,
        "limit": settings.avito_max_items_default,
        "fields": ["IMEI", "SN", "MAC", "PASSWORD"],
        "category_hint": "other"
    }