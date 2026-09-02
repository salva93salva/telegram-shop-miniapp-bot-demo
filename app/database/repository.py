from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import secrets

import aiosqlite


DEMO_CATEGORIES = (
    ("Prodotti digitali", 10),
    ("Prodotti fisici", 20),
)

DEMO_PRODUCTS = (
    (
        "Prodotti digitali",
        "DIGI-EBOOK-001",
        "Guida PDF dimostrativa",
        "Un prodotto digitale di esempio consegnabile "
        "automaticamente dopo il pagamento.",
        "digital",
        75,
        None,
        None,
        None,
        "https://example.com/demo-guida.pdf",
    ),
    (
        "Prodotti digitali",
        "DIGI-TEMPLATE-001",
        "Pacchetto template",
        "Raccolta dimostrativa di template scaricabili.",
        "digital",
        120,
        None,
        None,
        None,
        "https://example.com/demo-template.zip",
    ),
    (
        "Prodotti fisici",
        "PHYS-TSHIRT-001",
        "T-shirt dimostrativa",
        "Prodotto fisico di esempio, taglia e spedizione "
        "saranno aggiunte durante il checkout.",
        "physical",
        None,
        2490,
        "EUR",
        12,
        None,
    ),
    (
        "Prodotti fisici",
        "PHYS-MUG-001",
        "Tazza dimostrativa",
        "Prodotto fisico di esempio con quantità disponibile.",
        "physical",
        None,
        1490,
        "EUR",
        8,
        None,
    ),
)

ADMIN_ORDER_FILTERS = {
    "open": (
        "order_type = 'physical' AND "
        "fulfillment_status IN ('new', 'processing', 'shipped')"
    ),
    "completed": (
        "(order_type = 'physical' AND fulfillment_status = 'completed') "
        "OR (order_type = 'digital' AND status = 'paid')"
    ),
    "cancelled": (
        "status = 'cancelled' OR fulfillment_status = 'cancelled'"
    ),
    "digital": "order_type = 'digital'",
    "physical": "order_type = 'physical'",
    "all": "1 = 1",
}


class CartError(ValueError):
    """Il carrello non può essere modificato come richiesto."""


class OrderError(ValueError):
    """L'ordine non può essere creato o completato."""


class Database:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    async def connect(self) -> aiosqlite.Connection:
        connection = await aiosqlite.connect(self.database_path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA journal_mode = WAL")
        return connection

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = await self.connect()

        try:
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1
                        CHECK (active IN (0, 1))
                );

                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER NOT NULL
                        REFERENCES categories(id),
                    sku TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    product_type TEXT NOT NULL
                        CHECK (product_type IN ('digital', 'physical')),
                    price_stars INTEGER,
                    price_cents INTEGER,
                    currency TEXT,
                    stock_quantity INTEGER,
                    delivery_content TEXT,
                    delivery_file_id TEXT,
                    photo_file_id TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                        CHECK (active IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (
                        (
                            product_type = 'digital'
                            AND price_stars IS NOT NULL
                            AND price_stars > 0
                            AND price_cents IS NULL
                            AND currency IS NULL
                        )
                        OR
                        (
                            product_type = 'physical'
                            AND price_stars IS NULL
                            AND price_cents IS NOT NULL
                            AND price_cents >= 0
                            AND length(currency) = 3
                        )
                    ),
                    CHECK (
                        stock_quantity IS NULL
                        OR stock_quantity >= 0
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_products_catalog
                ON products (category_id, active, name);

                CREATE TABLE IF NOT EXISTS cart_items (
                    telegram_user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL
                        REFERENCES products(id) ON DELETE CASCADE,
                    quantity INTEGER NOT NULL
                        CHECK (quantity > 0),
                    added_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (telegram_user_id, product_id)
                );

                CREATE INDEX IF NOT EXISTS idx_cart_user
                ON cart_items (telegram_user_id, updated_at);

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    order_type TEXT NOT NULL
                        CHECK (order_type IN ('digital', 'physical')),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'paid', 'cancelled')),
                    total_stars INTEGER,
                    total_cents INTEGER,
                    currency TEXT,
                    payment_token TEXT NOT NULL UNIQUE,
                    payment_reference TEXT UNIQUE,
                    payment_method TEXT,
                    shipping_name TEXT,
                    shipping_address TEXT,
                    shipping_city_postal TEXT,
                    shipping_phone TEXT,
                    fulfillment_status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL,
                    paid_at TEXT
                );

                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL
                        REFERENCES orders(id) ON DELETE CASCADE,
                    product_id INTEGER NOT NULL,
                    sku TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    product_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_price_stars INTEGER,
                    unit_price_cents INTEGER,
                    currency TEXT,
                    delivery_content TEXT,
                    delivery_file_id TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_orders_user
                ON orders (telegram_user_id, created_at);
                """
            )

            await self._ensure_product_columns(connection)
            await self._ensure_order_columns(connection)
            await self._ensure_order_item_columns(connection)
            await self._seed_demo_catalog(connection)
            await self._ensure_demo_delivery_content(connection)
            await connection.commit()
        finally:
            await connection.close()

    async def _ensure_product_columns(
        self,
        connection: aiosqlite.Connection,
    ) -> None:
        cursor = await connection.execute("PRAGMA table_info(products)")
        columns = {row["name"] for row in await cursor.fetchall()}
        await cursor.close()

        missing_columns = {
            "delivery_content": "TEXT",
            "delivery_file_id": "TEXT",
            "photo_file_id": "TEXT",
        }

        for name, column_type in missing_columns.items():
            if name not in columns:
                await connection.execute(
                    f"ALTER TABLE products ADD COLUMN {name} {column_type}"
                )

    async def _ensure_order_columns(
        self,
        connection: aiosqlite.Connection,
    ) -> None:
        cursor = await connection.execute("PRAGMA table_info(orders)")
        columns = {row["name"] for row in await cursor.fetchall()}
        await cursor.close()
        missing_columns = {
            "payment_method": "TEXT",
            "shipping_name": "TEXT",
            "shipping_address": "TEXT",
            "shipping_city_postal": "TEXT",
            "shipping_phone": "TEXT",
            "fulfillment_status": "TEXT NOT NULL DEFAULT 'new'",
        }

        for name, column_type in missing_columns.items():
            if name not in columns:
                await connection.execute(
                    f"ALTER TABLE orders ADD COLUMN {name} {column_type}"
                )

    async def _ensure_order_item_columns(
        self,
        connection: aiosqlite.Connection,
    ) -> None:
        cursor = await connection.execute(
            "PRAGMA table_info(order_items)"
        )
        columns = {row["name"] for row in await cursor.fetchall()}
        await cursor.close()

        if "delivery_file_id" not in columns:
            await connection.execute(
                "ALTER TABLE order_items ADD COLUMN delivery_file_id TEXT"
            )

    async def _ensure_demo_delivery_content(
        self,
        connection: aiosqlite.Connection,
    ) -> None:
        await connection.executemany(
            """
            UPDATE products
            SET delivery_content = ?
            WHERE sku = ? AND delivery_content IS NULL
            """,
            (
                (
                    "https://example.com/demo-guida.pdf",
                    "DIGI-EBOOK-001",
                ),
                (
                    "https://example.com/demo-template.zip",
                    "DIGI-TEMPLATE-001",
                ),
            ),
        )

    async def _seed_demo_catalog(
        self,
        connection: aiosqlite.Connection,
    ) -> None:
        cursor = await connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?",
            ("demo_catalog_seeded",),
        )
        seeded = await cursor.fetchone()
        await cursor.close()

        if seeded is not None:
            return

        await connection.executemany(
            """
            INSERT OR IGNORE INTO categories (name, sort_order)
            VALUES (?, ?)
            """,
            DEMO_CATEGORIES,
        )

        now = datetime.now(timezone.utc).isoformat()

        for product in DEMO_PRODUCTS:
            (
                category_name,
                sku,
                name,
                description,
                product_type,
                price_stars,
                price_cents,
                currency,
                stock_quantity,
                delivery_content,
            ) = product

            await connection.execute(
                """
                INSERT OR IGNORE INTO products (
                    category_id,
                    sku,
                    name,
                    description,
                    product_type,
                    price_stars,
                    price_cents,
                    currency,
                    stock_quantity,
                    delivery_content,
                    created_at,
                    updated_at
                )
                SELECT
                    id, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                FROM categories
                WHERE name = ? COLLATE NOCASE
                """,
                (
                    sku,
                    name,
                    description,
                    product_type,
                    price_stars,
                    price_cents,
                    currency,
                    stock_quantity,
                    delivery_content,
                    now,
                    now,
                    category_name,
                ),
            )

        await connection.execute(
            """
            INSERT INTO app_metadata (key, value)
            VALUES (?, ?)
            """,
            ("demo_catalog_seeded", "1"),
        )

    async def list_active_categories(self) -> list[dict]:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT
                    categories.id,
                    categories.name,
                    COUNT(products.id) AS product_count
                FROM categories
                JOIN products
                  ON products.category_id = categories.id
                 AND products.active = 1
                WHERE categories.active = 1
                GROUP BY categories.id, categories.name
                ORDER BY categories.sort_order, categories.id
                """
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def get_active_category(
        self,
        category_id: int,
    ) -> dict | None:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT id, name
                FROM categories
                WHERE id = ? AND active = 1
                """,
                (category_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row is not None else None
        finally:
            await connection.close()

    async def list_mini_app_products(self) -> list[dict]:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT
                    products.id,
                    products.sku,
                    products.name,
                    products.description,
                    products.product_type,
                    products.price_stars,
                    products.price_cents,
                    products.currency,
                    products.stock_quantity,
                    products.photo_file_id IS NOT NULL
                        AS has_photo,
                    categories.id AS category_id,
                    categories.name AS category_name
                FROM products
                JOIN categories
                  ON categories.id = products.category_id
                WHERE products.active = 1
                  AND categories.active = 1
                ORDER BY
                    categories.sort_order,
                    categories.id,
                    products.name,
                    products.id
                """
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def list_active_products(
        self,
        category_id: int,
    ) -> list[dict]:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT *
                FROM products
                WHERE category_id = ? AND active = 1
                ORDER BY name, id
                """,
                (category_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def get_active_product(
        self,
        product_id: int,
    ) -> dict | None:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT
                    products.*,
                    categories.name AS category_name
                FROM products
                JOIN categories
                  ON categories.id = products.category_id
                WHERE products.id = ?
                  AND products.active = 1
                  AND categories.active = 1
                """,
                (product_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row is not None else None
        finally:
            await connection.close()

    async def add_to_cart(
        self,
        telegram_user_id: int,
        product_id: int,
    ) -> int:
        connection = await self.connect()

        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                SELECT products.*
                FROM products
                JOIN categories
                  ON categories.id = products.category_id
                WHERE products.id = ?
                  AND products.active = 1
                  AND categories.active = 1
                """,
                (product_id,),
            )
            product = await cursor.fetchone()
            await cursor.close()

            if product is None:
                raise CartError(
                    "Questo prodotto non è più disponibile."
                )

            cursor = await connection.execute(
                """
                SELECT quantity
                FROM cart_items
                WHERE telegram_user_id = ? AND product_id = ?
                """,
                (telegram_user_id, product_id),
            )
            existing = await cursor.fetchone()
            await cursor.close()
            current_quantity = (
                existing["quantity"] if existing is not None else 0
            )

            if product["product_type"] == "digital":
                new_quantity = 1
            else:
                stock = product["stock_quantity"]

                if stock is not None and current_quantity >= stock:
                    raise CartError(
                        "Hai raggiunto la quantità disponibile."
                    )

                new_quantity = current_quantity + 1

            now = datetime.now(timezone.utc).isoformat()
            await connection.execute(
                """
                INSERT INTO cart_items (
                    telegram_user_id,
                    product_id,
                    quantity,
                    added_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (telegram_user_id, product_id)
                DO UPDATE SET
                    quantity = excluded.quantity,
                    updated_at = excluded.updated_at
                """,
                (
                    telegram_user_id,
                    product_id,
                    new_quantity,
                    now,
                    now,
                ),
            )
            await connection.commit()
            return new_quantity
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def list_cart_items(
        self,
        telegram_user_id: int,
    ) -> list[dict]:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT
                    products.*,
                    cart_items.quantity
                FROM cart_items
                JOIN products
                  ON products.id = cart_items.product_id
                JOIN categories
                  ON categories.id = products.category_id
                WHERE cart_items.telegram_user_id = ?
                  AND products.active = 1
                  AND categories.active = 1
                ORDER BY products.product_type, products.name
                """,
                (telegram_user_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def remove_from_cart(
        self,
        telegram_user_id: int,
        product_id: int,
    ) -> bool:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                DELETE FROM cart_items
                WHERE telegram_user_id = ? AND product_id = ?
                """,
                (telegram_user_id, product_id),
            )
            await connection.commit()
            return cursor.rowcount == 1
        finally:
            await connection.close()

    async def clear_cart(self, telegram_user_id: int) -> int:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                DELETE FROM cart_items
                WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            )
            await connection.commit()
            return cursor.rowcount
        finally:
            await connection.close()

    async def create_digital_order(
        self,
        telegram_user_id: int,
    ) -> dict:
        connection = await self.connect()

        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                SELECT
                    products.*,
                    cart_items.quantity
                FROM cart_items
                JOIN products
                  ON products.id = cart_items.product_id
                JOIN categories
                  ON categories.id = products.category_id
                WHERE cart_items.telegram_user_id = ?
                  AND products.product_type = 'digital'
                  AND products.active = 1
                  AND categories.active = 1
                ORDER BY products.id
                """,
                (telegram_user_id,),
            )
            items = await cursor.fetchall()
            await cursor.close()

            if not items:
                raise OrderError(
                    "Il carrello non contiene prodotti digitali."
                )

            total_stars = sum(
                item["price_stars"] * item["quantity"]
                for item in items
            )
            token = secrets.token_urlsafe(12)
            now = datetime.now(timezone.utc).isoformat()
            cursor = await connection.execute(
                """
                INSERT INTO orders (
                    telegram_user_id,
                    order_type,
                    total_stars,
                    payment_token,
                    created_at
                )
                VALUES (?, 'digital', ?, ?, ?)
                """,
                (telegram_user_id, total_stars, token, now),
            )
            order_id = cursor.lastrowid

            await connection.executemany(
                """
                INSERT INTO order_items (
                    order_id,
                    product_id,
                    sku,
                    product_name,
                    product_type,
                    quantity,
                    unit_price_stars,
                    delivery_content,
                    delivery_file_id
                )
                VALUES (?, ?, ?, ?, 'digital', ?, ?, ?, ?)
                """,
                [
                    (
                        order_id,
                        item["id"],
                        item["sku"],
                        item["name"],
                        item["quantity"],
                        item["price_stars"],
                        item["delivery_content"],
                        item["delivery_file_id"],
                    )
                    for item in items
                ],
            )
            await connection.commit()
            return {
                "id": order_id,
                "telegram_user_id": telegram_user_id,
                "total_stars": total_stars,
                "payment_token": token,
                "status": "pending",
            }
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def complete_digital_order(
        self,
        order_id: int,
        telegram_user_id: int,
        payment_token: str,
        payment_reference: str,
        payment_method: str = "demo",
    ) -> bool:
        connection = await self.connect()

        try:
            await connection.execute("BEGIN IMMEDIATE")
            paid_at = datetime.now(timezone.utc).isoformat()
            cursor = await connection.execute(
                """
                UPDATE orders
                SET
                    status = 'paid',
                    payment_reference = ?,
                    payment_method = ?,
                    fulfillment_status = 'completed',
                    paid_at = ?
                WHERE id = ?
                  AND telegram_user_id = ?
                  AND payment_token = ?
                  AND order_type = 'digital'
                  AND status = 'pending'
                """,
                (
                    payment_reference,
                    payment_method,
                    paid_at,
                    order_id,
                    telegram_user_id,
                    payment_token,
                ),
            )

            if cursor.rowcount != 1:
                await connection.rollback()
                return False

            await connection.execute(
                """
                DELETE FROM cart_items
                WHERE telegram_user_id = ?
                  AND product_id IN (
                      SELECT product_id
                      FROM order_items
                      WHERE order_id = ?
                  )
                """,
                (telegram_user_id, order_id),
            )
            await connection.commit()
            return True
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def get_pending_digital_order(
        self,
        order_id: int,
        telegram_user_id: int,
        payment_token: str,
    ) -> dict | None:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT * FROM orders
                WHERE id = ?
                  AND telegram_user_id = ?
                  AND payment_token = ?
                  AND order_type = 'digital'
                  AND status = 'pending'
                """,
                (order_id, telegram_user_id, payment_token),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row is not None else None
        finally:
            await connection.close()

    async def get_order(
        self,
        order_id: int,
        telegram_user_id: int,
    ) -> dict | None:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT * FROM orders
                WHERE id = ? AND telegram_user_id = ?
                """,
                (order_id, telegram_user_id),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row is not None else None
        finally:
            await connection.close()

    async def list_order_items(self, order_id: int) -> list[dict]:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT * FROM order_items
                WHERE order_id = ?
                ORDER BY id
                """,
                (order_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def list_user_orders(
        self,
        telegram_user_id: int,
    ) -> list[dict]:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT * FROM orders
                WHERE telegram_user_id = ?
                ORDER BY id DESC
                LIMIT 20
                """,
                (telegram_user_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def create_physical_order(
        self,
        telegram_user_id: int,
        shipping_name: str,
        shipping_address: str,
        shipping_city_postal: str,
        shipping_phone: str,
    ) -> dict:
        connection = await self.connect()

        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                SELECT
                    products.*,
                    cart_items.quantity
                FROM cart_items
                JOIN products
                  ON products.id = cart_items.product_id
                JOIN categories
                  ON categories.id = products.category_id
                WHERE cart_items.telegram_user_id = ?
                  AND products.product_type = 'physical'
                  AND products.active = 1
                  AND categories.active = 1
                ORDER BY products.id
                """,
                (telegram_user_id,),
            )
            items = await cursor.fetchall()
            await cursor.close()

            if not items:
                raise OrderError(
                    "Il carrello non contiene prodotti fisici."
                )

            currencies = {item["currency"] for item in items}

            if len(currencies) != 1:
                raise OrderError(
                    "I prodotti fisici devono usare la stessa valuta."
                )

            for item in items:
                stock = item["stock_quantity"]

                if stock is not None and item["quantity"] > stock:
                    raise OrderError(
                        f"Quantità non disponibile per {item['name']}."
                    )

            total_cents = sum(
                item["price_cents"] * item["quantity"]
                for item in items
            )
            currency = next(iter(currencies))
            token = secrets.token_urlsafe(12)
            now = datetime.now(timezone.utc).isoformat()
            cursor = await connection.execute(
                """
                INSERT INTO orders (
                    telegram_user_id,
                    order_type,
                    total_cents,
                    currency,
                    payment_token,
                    payment_method,
                    shipping_name,
                    shipping_address,
                    shipping_city_postal,
                    shipping_phone,
                    created_at
                )
                VALUES (
                    ?, 'physical', ?, ?, ?, 'cash_on_delivery_demo',
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    telegram_user_id,
                    total_cents,
                    currency,
                    token,
                    shipping_name,
                    shipping_address,
                    shipping_city_postal,
                    shipping_phone,
                    now,
                ),
            )
            order_id = cursor.lastrowid

            await connection.executemany(
                """
                INSERT INTO order_items (
                    order_id,
                    product_id,
                    sku,
                    product_name,
                    product_type,
                    quantity,
                    unit_price_cents,
                    currency
                )
                VALUES (?, ?, ?, ?, 'physical', ?, ?, ?)
                """,
                [
                    (
                        order_id,
                        item["id"],
                        item["sku"],
                        item["name"],
                        item["quantity"],
                        item["price_cents"],
                        item["currency"],
                    )
                    for item in items
                ],
            )

            for item in items:
                cursor = await connection.execute(
                    """
                    UPDATE products
                    SET stock_quantity = CASE
                        WHEN stock_quantity IS NULL THEN NULL
                        ELSE stock_quantity - ?
                    END
                    WHERE id = ?
                      AND (
                          stock_quantity IS NULL
                          OR stock_quantity >= ?
                      )
                    """,
                    (item["quantity"], item["id"], item["quantity"]),
                )

                if cursor.rowcount != 1:
                    raise OrderError(
                        f"Scorte cambiate per {item['name']}. "
                        "Controlla nuovamente il carrello."
                    )

            await connection.execute(
                """
                DELETE FROM cart_items
                WHERE telegram_user_id = ?
                  AND product_id IN (
                      SELECT product_id
                      FROM order_items
                      WHERE order_id = ?
                  )
                """,
                (telegram_user_id, order_id),
            )
            await connection.commit()
            return {
                "id": order_id,
                "telegram_user_id": telegram_user_id,
                "total_cents": total_cents,
                "currency": currency,
                "status": "pending",
            }
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def get_admin_stats(self) -> dict:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM products) AS products_total,
                    (
                        SELECT COUNT(*) FROM products
                        WHERE active = 1
                    ) AS products_active,
                    (SELECT COUNT(*) FROM orders) AS orders_total,
                    (
                        SELECT COUNT(*) FROM orders
                        WHERE order_type = 'physical'
                          AND fulfillment_status NOT IN (
                              'completed', 'cancelled'
                          )
                    ) AS physical_open,
                    COALESCE((
                        SELECT SUM(total_stars) FROM orders
                        WHERE order_type = 'digital'
                          AND status = 'paid'
                    ), 0) AS digital_stars,
                    COALESCE((
                        SELECT SUM(total_cents) FROM orders
                        WHERE order_type = 'physical'
                          AND fulfillment_status != 'cancelled'
                    ), 0) AS physical_cents
                """
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row)
        finally:
            await connection.close()

    async def list_admin_orders(
        self,
        limit: int = 20,
        offset: int = 0,
        filter_name: str = "all",
    ) -> list[dict]:
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)
        condition = ADMIN_ORDER_FILTERS.get(
            filter_name,
            ADMIN_ORDER_FILTERS["all"],
        )
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                f"""
                SELECT * FROM orders
                WHERE {condition}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def count_admin_orders(self, filter_name: str = "all") -> int:
        condition = ADMIN_ORDER_FILTERS.get(
            filter_name,
            ADMIN_ORDER_FILTERS["all"],
        )
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                f"SELECT COUNT(*) AS total FROM orders WHERE {condition}"
            )
            row = await cursor.fetchone()
            await cursor.close()
            return int(row["total"])
        finally:
            await connection.close()

    async def search_admin_orders(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        query = query.strip()
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)

        if query.isdigit():
            condition = "id = ? OR telegram_user_id = ?"
            parameters: tuple = (int(query), int(query))
        else:
            try:
                datetime.strptime(query, "%Y-%m-%d")
            except ValueError:
                return []
            condition = "substr(created_at, 1, 10) = ?"
            parameters = (query,)

        connection = await self.connect()

        try:
            cursor = await connection.execute(
                f"""
                SELECT * FROM orders
                WHERE {condition}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                parameters + (safe_limit, safe_offset),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def count_admin_order_search(self, query: str) -> int:
        query = query.strip()

        if query.isdigit():
            condition = "id = ? OR telegram_user_id = ?"
            parameters: tuple = (int(query), int(query))
        else:
            try:
                datetime.strptime(query, "%Y-%m-%d")
            except ValueError:
                return 0
            condition = "substr(created_at, 1, 10) = ?"
            parameters = (query,)

        connection = await self.connect()

        try:
            cursor = await connection.execute(
                f"SELECT COUNT(*) AS total FROM orders WHERE {condition}",
                parameters,
            )
            row = await cursor.fetchone()
            await cursor.close()
            return int(row["total"])
        finally:
            await connection.close()

    async def get_admin_order(self, order_id: int) -> dict | None:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                "SELECT * FROM orders WHERE id = ?",
                (order_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row is not None else None
        finally:
            await connection.close()

    async def update_physical_order_status(
        self,
        order_id: int,
        fulfillment_status: str,
    ) -> bool:
        allowed_transitions = {
            "new": {"processing", "cancelled"},
            "processing": {"shipped", "cancelled"},
            "shipped": {"completed"},
            "completed": set(),
            "cancelled": set(),
        }

        connection = await self.connect()

        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                SELECT order_type, fulfillment_status
                FROM orders
                WHERE id = ?
                """,
                (order_id,),
            )
            order = await cursor.fetchone()
            await cursor.close()

            if order is None or order["order_type"] != "physical":
                await connection.rollback()
                return False

            current_status = order["fulfillment_status"]

            if fulfillment_status not in allowed_transitions.get(
                current_status,
                set(),
            ):
                await connection.rollback()
                return False

            if fulfillment_status == "cancelled":
                cursor = await connection.execute(
                    """
                    SELECT product_id, quantity
                    FROM order_items
                    WHERE order_id = ?
                      AND product_type = 'physical'
                    """,
                    (order_id,),
                )
                items = await cursor.fetchall()
                await cursor.close()

                for item in items:
                    await connection.execute(
                        """
                        UPDATE products
                        SET stock_quantity = CASE
                            WHEN stock_quantity IS NULL THEN NULL
                            ELSE stock_quantity + ?
                        END
                        WHERE id = ?
                        """,
                        (item["quantity"], item["product_id"]),
                    )

            cursor = await connection.execute(
                """
                UPDATE orders
                SET
                    fulfillment_status = ?,
                    status = CASE
                        WHEN ? = 'cancelled' THEN 'cancelled'
                        ELSE status
                    END
                WHERE id = ?
                """,
                (fulfillment_status, fulfillment_status, order_id),
            )
            await connection.commit()
            return cursor.rowcount == 1
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def list_all_products(self) -> list[dict]:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT
                    products.*,
                    categories.name AS category_name
                FROM products
                JOIN categories
                  ON categories.id = products.category_id
                ORDER BY categories.sort_order, products.id
                """
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def get_admin_product(self, product_id: int) -> dict | None:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                SELECT
                    products.*,
                    categories.name AS category_name
                FROM products
                JOIN categories
                  ON categories.id = products.category_id
                WHERE products.id = ?
                """,
                (product_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row is not None else None
        finally:
            await connection.close()

    async def create_product(
        self,
        *,
        product_type: str,
        name: str,
        description: str,
        price_stars: int | None = None,
        price_cents: int | None = None,
        stock_quantity: int | None = None,
        delivery_content: str | None = None,
        delivery_file_id: str | None = None,
        photo_file_id: str | None = None,
    ) -> dict:
        name = name.strip()
        description = description.strip()
        delivery_content = (
            delivery_content.strip() if delivery_content else None
        )

        if product_type not in {"digital", "physical"}:
            raise ValueError("Tipo prodotto non valido.")

        if not 1 <= len(name) <= 120:
            raise ValueError("Il nome deve avere da 1 a 120 caratteri.")

        if not 1 <= len(description) <= 1000:
            raise ValueError(
                "La descrizione deve avere da 1 a 1000 caratteri."
            )

        if product_type == "digital":
            if price_stars is None or not 1 <= price_stars <= 1_000_000:
                raise ValueError("Prezzo Stars non valido.")
            if not delivery_content and not delivery_file_id:
                raise ValueError("Consegna digitale non configurata.")
            price_cents = None
            stock_quantity = None
            currency = None
            category_name = "Prodotti digitali"
            sku_prefix = "DIGI"
        else:
            if price_cents is None or not 0 <= price_cents <= 100_000_000:
                raise ValueError("Prezzo in euro non valido.")
            if (
                stock_quantity is None
                or not 0 <= stock_quantity <= 1_000_000
            ):
                raise ValueError("Scorta non valida.")
            price_stars = None
            currency = "EUR"
            delivery_content = None
            delivery_file_id = None
            category_name = "Prodotti fisici"
            sku_prefix = "PHYS"

        sku = f"{sku_prefix}-{secrets.token_hex(5).upper()}"
        now = datetime.now(timezone.utc).isoformat()
        connection = await self.connect()

        try:
            await connection.execute(
                """
                INSERT OR IGNORE INTO categories (name, sort_order)
                VALUES (?, ?)
                """,
                (
                    category_name,
                    10 if product_type == "digital" else 20,
                ),
            )
            cursor = await connection.execute(
                "SELECT id FROM categories WHERE name = ? COLLATE NOCASE",
                (category_name,),
            )
            category = await cursor.fetchone()
            await cursor.close()
            cursor = await connection.execute(
                """
                INSERT INTO products (
                    category_id,
                    sku,
                    name,
                    description,
                    product_type,
                    price_stars,
                    price_cents,
                    currency,
                    stock_quantity,
                    delivery_content,
                    delivery_file_id,
                    photo_file_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category["id"],
                    sku,
                    name,
                    description,
                    product_type,
                    price_stars,
                    price_cents,
                    currency,
                    stock_quantity,
                    delivery_content,
                    delivery_file_id,
                    photo_file_id,
                    now,
                    now,
                ),
            )
            product_id = cursor.lastrowid
            await cursor.close()
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

        product = await self.get_admin_product(product_id)

        if product is None:
            raise RuntimeError("Prodotto appena creato non trovato.")

        return product

    async def update_product_text(
        self,
        product_id: int,
        field: str,
        value: str,
    ) -> bool:
        limits = {"name": 120, "description": 1000}

        if field not in limits:
            return False

        value = value.strip()

        if not 1 <= len(value) <= limits[field]:
            return False

        connection = await self.connect()

        try:
            cursor = await connection.execute(
                f"""
                UPDATE products
                SET {field} = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    value,
                    datetime.now(timezone.utc).isoformat(),
                    product_id,
                ),
            )
            await connection.commit()
            return cursor.rowcount == 1
        finally:
            await connection.close()

    async def update_product_price(
        self,
        product_id: int,
        amount: int,
    ) -> bool:
        if not 0 <= amount <= 100_000_000:
            return False

        connection = await self.connect()

        try:
            cursor = await connection.execute(
                "SELECT product_type FROM products WHERE id = ?",
                (product_id,),
            )
            product = await cursor.fetchone()
            await cursor.close()

            if product is None:
                return False

            if product["product_type"] == "digital":
                if 1 <= amount <= 1_000_000:
                    query = "price_stars = ?"
                else:
                    return False
            else:
                query = "price_cents = ?"

            cursor = await connection.execute(
                f"""
                UPDATE products
                SET {query}, updated_at = ?
                WHERE id = ?
                """,
                (
                    amount,
                    datetime.now(timezone.utc).isoformat(),
                    product_id,
                ),
            )
            await connection.commit()
            return cursor.rowcount == 1
        finally:
            await connection.close()

    async def set_product_stock(
        self,
        product_id: int,
        stock_quantity: int,
    ) -> bool:
        if not 0 <= stock_quantity <= 1_000_000:
            return False

        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                UPDATE products
                SET stock_quantity = ?, updated_at = ?
                WHERE id = ? AND product_type = 'physical'
                """,
                (
                    stock_quantity,
                    datetime.now(timezone.utc).isoformat(),
                    product_id,
                ),
            )
            await connection.commit()
            return cursor.rowcount == 1
        finally:
            await connection.close()

    async def update_product_photo(
        self,
        product_id: int,
        photo_file_id: str | None,
    ) -> bool:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                UPDATE products
                SET photo_file_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    photo_file_id,
                    datetime.now(timezone.utc).isoformat(),
                    product_id,
                ),
            )
            await connection.commit()
            return cursor.rowcount == 1
        finally:
            await connection.close()

    async def update_digital_delivery(
        self,
        product_id: int,
        *,
        delivery_content: str | None,
        delivery_file_id: str | None,
    ) -> bool:
        delivery_content = (
            delivery_content.strip() if delivery_content else None
        )

        if not delivery_content and not delivery_file_id:
            return False

        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                UPDATE products
                SET
                    delivery_content = ?,
                    delivery_file_id = ?,
                    updated_at = ?
                WHERE id = ? AND product_type = 'digital'
                """,
                (
                    delivery_content,
                    delivery_file_id,
                    datetime.now(timezone.utc).isoformat(),
                    product_id,
                ),
            )
            await connection.commit()
            return cursor.rowcount == 1
        finally:
            await connection.close()

    async def set_product_active(
        self,
        product_id: int,
        active: bool,
    ) -> bool:
        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                UPDATE products
                SET active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    1 if active else 0,
                    datetime.now(timezone.utc).isoformat(),
                    product_id,
                ),
            )
            await connection.commit()
            return cursor.rowcount == 1
        finally:
            await connection.close()

    async def delete_product(self, product_id: int) -> bool:
        connection = await self.connect()

        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "DELETE FROM products WHERE id = ?",
                (product_id,),
            )
            deleted = cursor.rowcount == 1
            await cursor.close()

            if deleted:
                await connection.commit()
            else:
                await connection.rollback()

            return deleted
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def adjust_product_stock(
        self,
        product_id: int,
        change: int,
    ) -> bool:
        if change not in {-1, 1}:
            return False

        connection = await self.connect()

        try:
            cursor = await connection.execute(
                """
                UPDATE products
                SET
                    stock_quantity = stock_quantity + ?,
                    updated_at = ?
                WHERE id = ?
                  AND product_type = 'physical'
                  AND stock_quantity IS NOT NULL
                  AND stock_quantity + ? >= 0
                """,
                (
                    change,
                    datetime.now(timezone.utc).isoformat(),
                    product_id,
                    change,
                ),
            )
            await connection.commit()
            return cursor.rowcount == 1
        finally:
            await connection.close()

    async def backup_to(self, destination: Path) -> bool:
        destination = Path(destination)

        if not self.database_path.is_file():
            return False

        if self.database_path.resolve() == destination.resolve():
            return False

        destination.parent.mkdir(parents=True, exist_ok=True)
        source = await aiosqlite.connect(self.database_path)
        target = await aiosqlite.connect(destination)

        try:
            await source.backup(target)
            await target.commit()
        finally:
            await target.close()
            await source.close()

        return destination.is_file() and destination.stat().st_size > 0


def format_product_price(product: dict) -> str:
    if product["product_type"] == "digital":
        return f"⭐ {product['price_stars']} Stars"

    euros, cents = divmod(product["price_cents"], 100)
    return f"{euros},{cents:02d} {product['currency']}"


def cart_totals(items: list[dict]) -> dict:
    return {
        "stars": sum(
            item["price_stars"] * item["quantity"]
            for item in items
            if item["product_type"] == "digital"
        ),
        "cents": sum(
            item["price_cents"] * item["quantity"]
            for item in items
            if item["product_type"] == "physical"
        ),
    }
