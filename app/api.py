from __future__ import annotations

from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database.repository import Database


def mini_app_origin(mini_app_url: str) -> str:
    parsed = urlparse(mini_app_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def serialize_product(product: dict) -> dict:
    if product["product_type"] == "digital":
        amount = product["price_stars"]
        currency = "XTR"
        price_label = f"{amount} Stars"
        available = True
    else:
        amount = product["price_cents"]
        currency = product["currency"]
        price_label = (
            f"{amount / 100:.2f} {currency}"
            .replace(".", ",")
        )
        available = (
            product["stock_quantity"] is None
            or product["stock_quantity"] > 0
        )

    return {
        "id": product["id"],
        "sku": product["sku"],
        "name": product["name"],
        "description": product["description"],
        "product_type": product["product_type"],
        "category": {
            "id": product["category_id"],
            "name": product["category_name"],
        },
        "price": {
            "amount": amount,
            "currency": currency,
            "label": price_label,
        },
        "stock_quantity": product["stock_quantity"],
        "available": available,
        "has_photo": bool(product["has_photo"]),
    }


def create_api(
    database: Database,
    settings: Settings,
) -> FastAPI:
    app = FastAPI(
        title=f"{settings.shop_name} API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[mini_app_origin(settings.mini_app_url)],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "service": "telegram-shop-miniapp-bot",
        }

    @app.get("/api/catalog")
    async def catalog() -> dict:
        products = await database.list_mini_app_products()
        return {
            "shop_name": settings.shop_name,
            "products": [
                serialize_product(product)
                for product in products
            ],
        }

    return app
