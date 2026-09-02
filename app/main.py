from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import uvicorn

from app.api import create_api
from app.config import load_settings
from app.database.repository import Database
from app.handlers import admin, admin_products, cart, catalog, orders, start


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        stream=sys.stdout,
    )

    settings = load_settings()
    database = Database(settings.database_path)
    await database.initialize()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

    dispatcher.include_router(admin_products.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(cart.router)
    dispatcher.include_router(orders.router)
    dispatcher.include_router(catalog.router)
    dispatcher.include_router(start.router)

    api = create_api(database, settings)
    api_server = uvicorn.Server(
        uvicorn.Config(
            api,
            host=settings.api_host,
            port=settings.api_port,
            log_level="info",
            access_log=False,
        )
    )
    running_tasks: list[asyncio.Task] = []

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print(
            "Shop Bot e API avviati. "
            "Premi CTRL+C per fermarli."
        )

        running_tasks = [
            asyncio.create_task(api_server.serve()),
            asyncio.create_task(
                dispatcher.start_polling(
                    bot,
                    settings=settings,
                    database=database,
                )
            ),
        ]

        finished, _ = await asyncio.wait(
            running_tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in finished:
            error = task.exception()
            if error is not None:
                raise error
    finally:
        api_server.should_exit = True

        for task in running_tasks:
            if not task.done():
                task.cancel()

        if running_tasks:
            await asyncio.gather(
                *running_tasks,
                return_exceptions=True,
            )

        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
