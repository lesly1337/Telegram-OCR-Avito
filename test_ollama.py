import asyncio
from app.agent.nlu import parse_user_request

async def main():
    print("Отправляем запрос в Ollama...")
    result = await parse_user_request("найди 15 iphone 13, нужны sn и imei")
    print("Результат:", result)

if __name__ == "__main__":
    asyncio.run(main())