from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from urllib.parse import urlencode

from httpx import ASGITransport, AsyncClient

from app.api import create_api, validate_telegram_init_data
from app.config import Settings
from app.database.repository import Database


def build_init_data(
    bot_token: str,
    telegram_user_id: int,
    auth_date: int,
) -> str:
    fields = {
        "auth_date": str(auth_date),
        "query_id": "test-query",
        "user": json.dumps(
            {
                "id": telegram_user_id,
                "first_name": "Test",
                "username": "test_user",
            },
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()
    fields["hash"] = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(fields)


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        self.messages.append(
            {"chat_id": chat_id, "text": text, "kwargs": kwargs}
        )

    async def get_me(self) -> SimpleNamespace:
        return SimpleNamespace(username="test_miniapp_bot")


class MiniAppApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        database_path = (
            Path(self.temporary_directory.name) / "shop.db"
        )
        self.database = Database(database_path)
        await self.database.initialize()
        self.settings = Settings(
            bot_token="test-token",
            admin_ids=frozenset({1}),
            database_path=database_path,
            shop_name="Test Mini App Shop",
            payment_mode="demo",
            support_contact="Test support",
            mini_app_url="https://miniapp.example.com/store",
            api_host="127.0.0.1",
            api_port=8000,
        )
        self.app = create_api(self.database, self.settings)

    async def asyncTearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_catalog_exposes_safe_active_products(self) -> None:
        transport = ASGITransport(app=self.app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/catalog",
                headers={"Origin": "https://miniapp.example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "https://miniapp.example.com",
        )
        payload = response.json()
        self.assertEqual(payload["shop_name"], "Test Mini App Shop")
        self.assertGreater(len(payload["products"]), 0)

        product = payload["products"][0]
        self.assertIn("price", product)
        self.assertIn("available", product)
        self.assertNotIn("delivery_content", product)
        self.assertNotIn("delivery_file_id", product)
        self.assertNotIn("photo_file_id", product)

    async def test_health_endpoint(self) -> None:
        transport = ASGITransport(app=self.app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    async def test_signed_mini_app_cart_is_saved_and_sent_to_bot(self) -> None:
        fake_bot = FakeBot()
        app = create_api(self.database, self.settings, fake_bot)
        transport = ASGITransport(app=app)
        init_data = build_init_data(
            self.settings.bot_token,
            telegram_user_id=987654,
            auth_date=int(datetime.now(timezone.utc).timestamp()),
        )

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/cart/sync",
                headers={
                    "Origin": "https://miniapp.example.com",
                    "X-Telegram-Init-Data": init_data,
                },
                json={
                    "items": [
                        {"product_id": 1, "quantity": 3},
                        {"product_id": 3, "quantity": 2},
                    ]
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cart_count"], 3)
        self.assertEqual(
            response.json()["bot_url"],
            "https://t.me/test_miniapp_bot",
        )
        items = await self.database.list_cart_items(987654)
        quantities = {item["id"]: item["quantity"] for item in items}
        self.assertEqual(quantities, {1: 1, 3: 2})
        self.assertEqual(fake_bot.messages[0]["chat_id"], 987654)

    async def test_cart_sync_rejects_unsigned_requests(self) -> None:
        app = create_api(self.database, self.settings, FakeBot())
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/cart/sync",
                headers={"Origin": "https://miniapp.example.com"},
                json={"items": [{"product_id": 1, "quantity": 1}]},
            )

        self.assertEqual(response.status_code, 401)

    def test_expired_init_data_is_rejected(self) -> None:
        now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        init_data = build_init_data(
            self.settings.bot_token,
            telegram_user_id=123,
            auth_date=int(now.timestamp()) - 3601,
        )

        with self.assertRaisesRegex(ValueError, "scaduta"):
            validate_telegram_init_data(
                init_data,
                self.settings.bot_token,
                now=now,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
