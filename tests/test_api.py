from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from httpx import ASGITransport, AsyncClient

from app.api import create_api
from app.config import Settings
from app.database.repository import Database


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
