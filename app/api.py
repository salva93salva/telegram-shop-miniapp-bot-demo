from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
from io import BytesIO
import json
from urllib.parse import parse_qsl, urlparse

from aiogram import Bot
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import Settings
from app.database.repository import CartError, Database
from app.handlers.cart import cart_text
from app.keyboards.menus import cart_keyboard


MAX_INIT_DATA_AGE_SECONDS = 3600


class CartItemRequest(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=99)


class CartSyncRequest(BaseModel):
    items: list[CartItemRequest] = Field(min_length=1, max_length=50)


def mini_app_origin(mini_app_url: str) -> str:
    parsed = urlparse(mini_app_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    now: datetime | None = None,
) -> dict:
    if not init_data:
        raise ValueError("Dati Telegram mancanti.")

    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop("hash", "")

    if not received_hash:
        raise ValueError("Firma Telegram mancante.")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Firma Telegram non valida.")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError) as error:
        raise ValueError("Data di autenticazione non valida.") from error

    current_time = now or datetime.now(timezone.utc)
    age_seconds = current_time.timestamp() - auth_date

    if age_seconds < -30 or age_seconds > MAX_INIT_DATA_AGE_SECONDS:
        raise ValueError("Sessione Telegram scaduta. Riapri la Mini App.")

    try:
        user = json.loads(fields["user"])
        telegram_user_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Utente Telegram non valido.") from error

    if telegram_user_id <= 0:
        raise ValueError("Utente Telegram non valido.")

    user["id"] = telegram_user_id
    return user


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

    has_photo = bool(product["has_photo"])

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
        "has_photo": has_photo,
        "photo_url": (
            f"/api/products/{product['id']}/photo"
            if has_photo
            else None
        ),
    }


def create_api(
    database: Database,
    settings: Settings,
    bot: Bot | None = None,
) -> FastAPI:
    app = FastAPI(
        title=f"{settings.shop_name} API",
        version="1.1.0",
        docs_url=None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[mini_app_origin(settings.mini_app_url)],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Telegram-Init-Data"],
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

    @app.get("/api/products/{product_id}/photo")
    async def product_photo(product_id: int) -> StreamingResponse:
        if bot is None:
            raise HTTPException(
                status_code=503,
                detail="Servizio immagini non disponibile.",
            )

        product = await database.get_active_product(product_id)

        if product is None or not product["photo_file_id"]:
            raise HTTPException(
                status_code=404,
                detail="Foto prodotto non disponibile.",
            )

        image = BytesIO()

        try:
            await bot.download(
                product["photo_file_id"],
                destination=image,
            )
        except Exception as error:
            raise HTTPException(
                status_code=502,
                detail="Impossibile recuperare la foto da Telegram.",
            ) from error

        image.seek(0)
        return StreamingResponse(
            image,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.post("/api/cart/sync")
    async def sync_cart(
        request: CartSyncRequest,
        telegram_init_data: str = Header(
            default="",
            alias="X-Telegram-Init-Data",
        ),
    ) -> dict:
        if bot is None:
            raise HTTPException(
                status_code=503,
                detail="Checkout Telegram non disponibile.",
            )

        try:
            user = validate_telegram_init_data(
                telegram_init_data,
                settings.bot_token,
            )
        except ValueError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

        try:
            items = await database.replace_cart(
                telegram_user_id=user["id"],
                requested_items=[
                    (item.product_id, item.quantity)
                    for item in request.items
                ],
            )
        except CartError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        try:
            await bot.send_message(
                user["id"],
                "✅ <b>Carrello ricevuto dalla Mini App</b>\n\n"
                + cart_text(items),
                reply_markup=cart_keyboard(items),
            )
            bot_info = await bot.get_me()
        except Exception as error:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Carrello salvato, ma Telegram non ha potuto aprire "
                    "il checkout. Torna nella chat del bot e apri il carrello."
                ),
            ) from error

        return {
            "status": "ok",
            "cart_count": sum(item["quantity"] for item in items),
            "bot_url": f"https://t.me/{bot_info.username}",
        }

    return app
