from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest

from app.database.repository import (
    CartError,
    Database,
    cart_totals,
    format_product_price,
)
from app.handlers.orders import (
    build_invoice_payload,
    parse_invoice_payload,
)


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Database(
            Path(self.temporary_directory.name) / "shop.db"
        )
        asyncio.run(self.database.initialize())

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_demo_categories_are_created_once(self) -> None:
        first = asyncio.run(self.database.list_active_categories())
        asyncio.run(self.database.initialize())
        second = asyncio.run(self.database.list_active_categories())

        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertEqual(
            sum(item["product_count"] for item in first),
            4,
        )

    def test_catalog_contains_digital_and_physical_products(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        products = [
            product
            for category in categories
            for product in asyncio.run(
                self.database.list_active_products(category["id"])
            )
        ]

        self.assertEqual(
            {product["product_type"] for product in products},
            {"digital", "physical"},
        )

    def test_product_details_include_category(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        product = asyncio.run(
            self.database.list_active_products(categories[0]["id"])
        )[0]
        details = asyncio.run(
            self.database.get_active_product(product["id"])
        )

        self.assertIsNotNone(details)
        self.assertEqual(
            details["category_name"],
            categories[0]["name"],
        )

    def test_prices_use_correct_payment_unit(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        products = [
            product
            for category in categories
            for product in asyncio.run(
                self.database.list_active_products(category["id"])
            )
        ]
        digital = next(
            item for item in products
            if item["product_type"] == "digital"
        )
        physical = next(
            item for item in products
            if item["product_type"] == "physical"
        )

        self.assertIn("Stars", format_product_price(digital))
        self.assertIn("EUR", format_product_price(physical))

    def test_unknown_product_is_not_returned(self) -> None:
        product = asyncio.run(
            self.database.get_active_product(999999)
        )
        self.assertIsNone(product)

    def test_cart_is_kept_separate_for_each_user(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        product = asyncio.run(
            self.database.list_active_products(categories[0]["id"])
        )[0]

        asyncio.run(self.database.add_to_cart(101, product["id"]))

        self.assertEqual(
            len(asyncio.run(self.database.list_cart_items(101))),
            1,
        )
        self.assertEqual(
            asyncio.run(self.database.list_cart_items(202)),
            [],
        )

    def test_digital_product_quantity_stays_one(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        product = asyncio.run(
            self.database.list_active_products(categories[0]["id"])
        )[0]

        asyncio.run(self.database.add_to_cart(101, product["id"]))
        quantity = asyncio.run(
            self.database.add_to_cart(101, product["id"])
        )
        self.assertEqual(quantity, 1)

    def test_physical_product_quantity_increases(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        physical_category = next(
            item for item in categories
            if item["name"] == "Prodotti fisici"
        )
        product = asyncio.run(
            self.database.list_active_products(
                physical_category["id"]
            )
        )[0]

        asyncio.run(self.database.add_to_cart(101, product["id"]))
        quantity = asyncio.run(
            self.database.add_to_cart(101, product["id"])
        )
        self.assertEqual(quantity, 2)

    def test_cart_remove_and_clear(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        products = [
            product
            for category in categories
            for product in asyncio.run(
                self.database.list_active_products(category["id"])
            )
        ]

        for product in products[:2]:
            asyncio.run(self.database.add_to_cart(101, product["id"]))

        self.assertTrue(
            asyncio.run(
                self.database.remove_from_cart(101, products[0]["id"])
            )
        )
        self.assertEqual(asyncio.run(self.database.clear_cart(101)), 1)
        self.assertEqual(
            asyncio.run(self.database.list_cart_items(101)),
            [],
        )

    def test_cart_totals_keep_stars_and_euros_separate(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        products = [
            product
            for category in categories
            for product in asyncio.run(
                self.database.list_active_products(category["id"])
            )
        ]

        for product in products:
            asyncio.run(self.database.add_to_cart(101, product["id"]))

        items = asyncio.run(self.database.list_cart_items(101))
        totals = cart_totals(items)
        self.assertGreater(totals["stars"], 0)
        self.assertGreater(totals["cents"], 0)

    def test_stock_limit_is_enforced(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        physical_category = next(
            item for item in categories
            if item["name"] == "Prodotti fisici"
        )
        product = asyncio.run(
            self.database.list_active_products(
                physical_category["id"]
            )
        )[0]

        for _ in range(product["stock_quantity"]):
            asyncio.run(self.database.add_to_cart(101, product["id"]))

        with self.assertRaises(CartError):
            asyncio.run(
                self.database.add_to_cart(101, product["id"])
            )

    def test_digital_order_snapshots_cart_and_total(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        digital_category = next(
            item for item in categories
            if item["name"] == "Prodotti digitali"
        )
        products = asyncio.run(
            self.database.list_active_products(
                digital_category["id"]
            )
        )

        for product in products:
            asyncio.run(self.database.add_to_cart(101, product["id"]))

        order = asyncio.run(self.database.create_digital_order(101))
        items = asyncio.run(
            self.database.list_order_items(order["id"])
        )
        self.assertEqual(len(items), len(products))
        self.assertEqual(
            order["total_stars"],
            sum(item["price_stars"] for item in products),
        )

    def test_completed_order_delivers_once_and_clears_digital_cart(self):
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        products = [
            product
            for category in categories
            for product in asyncio.run(
                self.database.list_active_products(category["id"])
            )
        ]

        for product in products:
            asyncio.run(self.database.add_to_cart(101, product["id"]))

        order = asyncio.run(self.database.create_digital_order(101))
        first = asyncio.run(
            self.database.complete_digital_order(
                order["id"],
                101,
                order["payment_token"],
                "demo-reference",
            )
        )
        second = asyncio.run(
            self.database.complete_digital_order(
                order["id"],
                101,
                order["payment_token"],
                "another-reference",
            )
        )
        remaining = asyncio.run(self.database.list_cart_items(101))

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(
            all(item["product_type"] == "physical" for item in remaining)
        )

    def test_order_history_is_private_to_user(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        product = asyncio.run(
            self.database.list_active_products(categories[0]["id"])
        )[0]
        asyncio.run(self.database.add_to_cart(101, product["id"]))
        asyncio.run(self.database.create_digital_order(101))

        self.assertEqual(
            len(asyncio.run(self.database.list_user_orders(101))),
            1,
        )
        self.assertEqual(
            asyncio.run(self.database.list_user_orders(202)),
            [],
        )

    def test_physical_order_updates_stock_and_keeps_digital_cart(self):
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        products = [
            product
            for category in categories
            for product in asyncio.run(
                self.database.list_active_products(category["id"])
            )
        ]
        physical = next(
            item for item in products
            if item["product_type"] == "physical"
        )
        digital = next(
            item for item in products
            if item["product_type"] == "digital"
        )
        original_stock = physical["stock_quantity"]
        asyncio.run(self.database.add_to_cart(101, physical["id"]))
        asyncio.run(self.database.add_to_cart(101, digital["id"]))

        order = asyncio.run(
            self.database.create_physical_order(
                101,
                "Mario Demo",
                "Via Demo 10",
                "00100 Roma",
                "+39 000 0000000",
            )
        )
        remaining = asyncio.run(self.database.list_cart_items(101))
        updated = asyncio.run(
            self.database.get_active_product(physical["id"])
        )

        self.assertEqual(order["total_cents"], physical["price_cents"])
        self.assertEqual(updated["stock_quantity"], original_stock - 1)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["product_type"], "digital")

    def test_physical_order_keeps_shipping_snapshot(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        physical_category = next(
            item for item in categories
            if item["name"] == "Prodotti fisici"
        )
        product = asyncio.run(
            self.database.list_active_products(
                physical_category["id"]
            )
        )[0]
        asyncio.run(self.database.add_to_cart(101, product["id"]))
        created = asyncio.run(
            self.database.create_physical_order(
                101,
                "Mario Demo",
                "Via Demo 10",
                "00100 Roma",
                "+39 000 0000000",
            )
        )
        order = asyncio.run(
            self.database.get_order(created["id"], 101)
        )

        self.assertEqual(order["shipping_name"], "Mario Demo")
        self.assertEqual(order["shipping_address"], "Via Demo 10")
        self.assertEqual(
            order["payment_method"],
            "cash_on_delivery_demo",
        )

    def test_stars_invoice_payload_round_trip(self) -> None:
        payload = build_invoice_payload(12, 34567, "secure-token")
        self.assertEqual(
            parse_invoice_payload(payload),
            (12, 34567, "secure-token"),
        )
        self.assertIsNone(parse_invoice_payload("invalid"))

    def test_pending_digital_order_requires_all_identifiers(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        product = asyncio.run(
            self.database.list_active_products(categories[0]["id"])
        )[0]
        asyncio.run(self.database.add_to_cart(101, product["id"]))
        order = asyncio.run(self.database.create_digital_order(101))

        valid = asyncio.run(
            self.database.get_pending_digital_order(
                order["id"],
                101,
                order["payment_token"],
            )
        )
        wrong_user = asyncio.run(
            self.database.get_pending_digital_order(
                order["id"],
                202,
                order["payment_token"],
            )
        )
        wrong_token = asyncio.run(
            self.database.get_pending_digital_order(
                order["id"],
                101,
                "wrong",
            )
        )

        self.assertIsNotNone(valid)
        self.assertIsNone(wrong_user)
        self.assertIsNone(wrong_token)

    def test_completed_stars_order_records_payment_method(self) -> None:
        categories = asyncio.run(
            self.database.list_active_categories()
        )
        product = asyncio.run(
            self.database.list_active_products(categories[0]["id"])
        )[0]
        asyncio.run(self.database.add_to_cart(101, product["id"]))
        order = asyncio.run(self.database.create_digital_order(101))
        asyncio.run(
            self.database.complete_digital_order(
                order["id"],
                101,
                order["payment_token"],
                "telegram-charge-id",
                payment_method="telegram_stars",
            )
        )
        stored = asyncio.run(
            self.database.get_order(order["id"], 101)
        )

        self.assertEqual(stored["status"], "paid")
        self.assertEqual(stored["payment_method"], "telegram_stars")
        self.assertEqual(
            stored["payment_reference"],
            "telegram-charge-id",
        )

    def test_admin_stats_and_product_visibility(self) -> None:
        stats = asyncio.run(self.database.get_admin_stats())
        products = asyncio.run(self.database.list_all_products())
        product = products[0]

        self.assertEqual(stats["products_total"], 4)
        self.assertEqual(stats["products_active"], 4)
        self.assertTrue(
            asyncio.run(
                self.database.set_product_active(product["id"], False)
            )
        )

        updated_products = asyncio.run(
            self.database.list_all_products()
        )
        updated = next(
            item for item in updated_products
            if item["id"] == product["id"]
        )
        self.assertEqual(updated["active"], 0)

    def test_admin_stock_never_goes_below_zero(self) -> None:
        products = asyncio.run(self.database.list_all_products())
        physical = next(
            item for item in products
            if item["product_type"] == "physical"
        )

        for _ in range(physical["stock_quantity"]):
            self.assertTrue(
                asyncio.run(
                    self.database.adjust_product_stock(
                        physical["id"],
                        -1,
                    )
                )
            )

        self.assertFalse(
            asyncio.run(
                self.database.adjust_product_stock(
                    physical["id"],
                    -1,
                )
            )
        )

    def test_admin_creates_digital_product_with_photo_and_file(self) -> None:
        product = asyncio.run(
            self.database.create_product(
                product_type="digital",
                name="Manuale digitale",
                description="File di prova consegnato automaticamente.",
                price_stars=99,
                delivery_file_id="telegram-document-file-id",
                photo_file_id="telegram-photo-file-id",
            )
        )

        self.assertEqual(product["product_type"], "digital")
        self.assertEqual(product["price_stars"], 99)
        self.assertEqual(
            product["photo_file_id"],
            "telegram-photo-file-id",
        )

        asyncio.run(self.database.add_to_cart(101, product["id"]))
        order = asyncio.run(self.database.create_digital_order(101))
        item = asyncio.run(
            self.database.list_order_items(order["id"])
        )[0]
        self.assertEqual(
            item["delivery_file_id"],
            "telegram-document-file-id",
        )

    def test_admin_creates_and_edits_physical_product(self) -> None:
        product = asyncio.run(
            self.database.create_product(
                product_type="physical",
                name="Prodotto personalizzato",
                description="Descrizione iniziale.",
                price_cents=2590,
                stock_quantity=7,
            )
        )

        self.assertTrue(
            asyncio.run(
                self.database.update_product_text(
                    product["id"],
                    "name",
                    "Prodotto aggiornato",
                )
            )
        )
        self.assertTrue(
            asyncio.run(
                self.database.update_product_price(product["id"], 3190)
            )
        )
        self.assertTrue(
            asyncio.run(
                self.database.set_product_stock(product["id"], 12)
            )
        )
        self.assertTrue(
            asyncio.run(
                self.database.update_product_photo(
                    product["id"],
                    "new-photo-id",
                )
            )
        )

        updated = asyncio.run(
            self.database.get_admin_product(product["id"])
        )
        self.assertEqual(updated["name"], "Prodotto aggiornato")
        self.assertEqual(updated["price_cents"], 3190)
        self.assertEqual(updated["stock_quantity"], 12)
        self.assertEqual(updated["photo_file_id"], "new-photo-id")

    def test_digital_product_requires_delivery(self) -> None:
        with self.assertRaises(ValueError):
            asyncio.run(
                self.database.create_product(
                    product_type="digital",
                    name="Prodotto incompleto",
                    description="Questo prodotto non ha una consegna.",
                    price_stars=50,
                )
            )

    def test_admin_updates_digital_delivery(self) -> None:
        product = asyncio.run(
            self.database.create_product(
                product_type="digital",
                name="Corso digitale",
                description="Contenuto digitale di prova.",
                price_stars=150,
                delivery_content="https://example.com/old",
            )
        )

        self.assertTrue(
            asyncio.run(
                self.database.update_digital_delivery(
                    product["id"],
                    delivery_content=None,
                    delivery_file_id="replacement-file-id",
                )
            )
        )
        updated = asyncio.run(
            self.database.get_admin_product(product["id"])
        )
        self.assertIsNone(updated["delivery_content"])
        self.assertEqual(
            updated["delivery_file_id"],
            "replacement-file-id",
        )

    def test_admin_order_filters_keep_completed_out_of_open_list(self):
        products = asyncio.run(self.database.list_all_products())
        digital = next(
            item for item in products
            if item["product_type"] == "digital"
        )
        physical = next(
            item for item in products
            if item["product_type"] == "physical"
        )

        asyncio.run(self.database.add_to_cart(501, digital["id"]))
        digital_order = asyncio.run(
            self.database.create_digital_order(501)
        )
        asyncio.run(
            self.database.complete_digital_order(
                digital_order["id"],
                501,
                digital_order["payment_token"],
                "filter-test-payment",
            )
        )

        asyncio.run(self.database.add_to_cart(502, physical["id"]))
        physical_order = asyncio.run(
            self.database.create_physical_order(
                502,
                "Cliente Fisico",
                "Via Test 1",
                "00100 Roma",
                "+39 000000",
            )
        )

        open_orders = asyncio.run(
            self.database.list_admin_orders(filter_name="open")
        )
        completed_orders = asyncio.run(
            self.database.list_admin_orders(filter_name="completed")
        )

        self.assertEqual(
            [item["id"] for item in open_orders],
            [physical_order["id"]],
        )
        self.assertEqual(
            [item["id"] for item in completed_orders],
            [digital_order["id"]],
        )

    def test_admin_order_list_is_paginated(self) -> None:
        product = asyncio.run(
            self.database.create_product(
                product_type="physical",
                name="Prodotto per paginazione",
                description="Prodotto con scorta sufficiente per il test.",
                price_cents=1000,
                stock_quantity=20,
            )
        )

        for index in range(15):
            user_id = 1000 + index
            asyncio.run(
                self.database.add_to_cart(user_id, product["id"])
            )
            asyncio.run(
                self.database.create_physical_order(
                    user_id,
                    f"Cliente {index}",
                    "Via Test 1",
                    "00100 Roma",
                    "+39 000000",
                )
            )

        first_page = asyncio.run(
            self.database.list_admin_orders(
                limit=10,
                offset=0,
                filter_name="open",
            )
        )
        second_page = asyncio.run(
            self.database.list_admin_orders(
                limit=10,
                offset=10,
                filter_name="open",
            )
        )

        self.assertEqual(
            asyncio.run(self.database.count_admin_orders("open")),
            15,
        )
        self.assertEqual(len(first_page), 10)
        self.assertEqual(len(second_page), 5)
        self.assertTrue(
            set(item["id"] for item in first_page).isdisjoint(
                item["id"] for item in second_page
            )
        )

    def test_admin_searches_orders_by_id_customer_and_date(self) -> None:
        products = asyncio.run(self.database.list_all_products())
        physical = next(
            item for item in products
            if item["product_type"] == "physical"
        )
        telegram_user_id = 987654321
        asyncio.run(
            self.database.add_to_cart(telegram_user_id, physical["id"])
        )
        created = asyncio.run(
            self.database.create_physical_order(
                telegram_user_id,
                "Cliente Ricerca",
                "Via Test 1",
                "00100 Roma",
                "+39 000000",
            )
        )
        stored = asyncio.run(
            self.database.get_admin_order(created["id"])
        )
        date_text = stored["created_at"][:10]

        by_order = asyncio.run(
            self.database.search_admin_orders(str(created["id"]))
        )
        by_user = asyncio.run(
            self.database.search_admin_orders(str(telegram_user_id))
        )
        by_date = asyncio.run(
            self.database.search_admin_orders(date_text)
        )

        self.assertIn(created["id"], [item["id"] for item in by_order])
        self.assertIn(created["id"], [item["id"] for item in by_user])
        self.assertIn(created["id"], [item["id"] for item in by_date])

    def test_admin_deletes_product_but_preserves_order_snapshot(self):
        product = asyncio.run(
            self.database.create_product(
                product_type="digital",
                name="Prodotto eliminabile",
                description="Prodotto usato per verificare l'eliminazione.",
                price_stars=25,
                delivery_file_id="preserved-delivery-file",
            )
        )
        asyncio.run(self.database.add_to_cart(701, product["id"]))
        order = asyncio.run(self.database.create_digital_order(701))
        asyncio.run(self.database.add_to_cart(702, product["id"]))

        self.assertTrue(
            asyncio.run(self.database.delete_product(product["id"]))
        )
        self.assertIsNone(
            asyncio.run(self.database.get_admin_product(product["id"]))
        )
        self.assertEqual(
            asyncio.run(self.database.list_cart_items(702)),
            [],
        )

        items = asyncio.run(
            self.database.list_order_items(order["id"])
        )
        self.assertEqual(items[0]["product_name"], "Prodotto eliminabile")
        self.assertEqual(
            items[0]["delivery_file_id"],
            "preserved-delivery-file",
        )
        self.assertTrue(
            asyncio.run(
                self.database.complete_digital_order(
                    order["id"],
                    701,
                    order["payment_token"],
                    "payment-after-product-delete",
                )
            )
        )

    def test_deleting_unknown_product_returns_false(self) -> None:
        self.assertFalse(
            asyncio.run(self.database.delete_product(999999))
        )

    def test_admin_physical_order_follows_safe_status_flow(self) -> None:
        products = asyncio.run(self.database.list_all_products())
        physical = next(
            item for item in products
            if item["product_type"] == "physical"
        )
        asyncio.run(self.database.add_to_cart(101, physical["id"]))
        order = asyncio.run(
            self.database.create_physical_order(
                101,
                "Mario Demo",
                "Via Demo 10",
                "00100 Roma",
                "+39 000 0000000",
            )
        )

        self.assertFalse(
            asyncio.run(
                self.database.update_physical_order_status(
                    order["id"],
                    "completed",
                )
            )
        )

        for status in ("processing", "shipped", "completed"):
            self.assertTrue(
                asyncio.run(
                    self.database.update_physical_order_status(
                        order["id"],
                        status,
                    )
                )
            )

        stored = asyncio.run(
            self.database.get_admin_order(order["id"])
        )
        self.assertEqual(stored["fulfillment_status"], "completed")
        self.assertFalse(
            asyncio.run(
                self.database.update_physical_order_status(
                    order["id"],
                    "cancelled",
                )
            )
        )

    def test_admin_cancellation_restores_stock_once(self) -> None:
        products = asyncio.run(self.database.list_all_products())
        physical = next(
            item for item in products
            if item["product_type"] == "physical"
        )
        original_stock = physical["stock_quantity"]
        asyncio.run(self.database.add_to_cart(101, physical["id"]))
        order = asyncio.run(
            self.database.create_physical_order(
                101,
                "Mario Demo",
                "Via Demo 10",
                "00100 Roma",
                "+39 000 0000000",
            )
        )

        self.assertTrue(
            asyncio.run(
                self.database.update_physical_order_status(
                    order["id"],
                    "cancelled",
                )
            )
        )
        self.assertFalse(
            asyncio.run(
                self.database.update_physical_order_status(
                    order["id"],
                    "cancelled",
                )
            )
        )

        updated = next(
            item
            for item in asyncio.run(self.database.list_all_products())
            if item["id"] == physical["id"]
        )
        self.assertEqual(updated["stock_quantity"], original_stock)

    def test_database_backup_contains_saved_orders(self) -> None:
        products = asyncio.run(self.database.list_all_products())
        digital = next(
            item for item in products
            if item["product_type"] == "digital"
        )
        asyncio.run(self.database.add_to_cart(101, digital["id"]))
        asyncio.run(self.database.create_digital_order(101))
        backup_path = Path(self.temporary_directory.name) / "backup.db"

        self.assertTrue(
            asyncio.run(self.database.backup_to(backup_path))
        )

        restored_database = Database(backup_path)
        restored_stats = asyncio.run(
            restored_database.get_admin_stats()
        )
        self.assertEqual(restored_stats["orders_total"], 1)

    def test_backup_does_not_create_a_missing_source(self) -> None:
        missing_path = (
            Path(self.temporary_directory.name) / "missing.db"
        )
        destination = (
            Path(self.temporary_directory.name) / "missing-backup.db"
        )
        missing_database = Database(missing_path)

        self.assertFalse(
            asyncio.run(missing_database.backup_to(destination))
        )
        self.assertFalse(missing_path.exists())
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
