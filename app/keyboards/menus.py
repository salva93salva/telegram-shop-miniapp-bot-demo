from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard(mini_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Apri lo Store",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛍 Sfoglia il catalogo",
                    callback_data="catalog:categories",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛒 Il mio carrello",
                    callback_data="cart:show",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧾 I miei ordini",
                    callback_data="orders:show",
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Informazioni",
                    callback_data="menu:info",
                )
            ],
        ]
    )


def categories_keyboard(categories: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for category in categories:
        builder.button(
            text=(
                f"📁 {category['name']} "
                f"({category['product_count']})"
            ),
            callback_data=f"catalog:category:{category['id']}",
        )

    builder.button(
        text="⬅️ Menu principale",
        callback_data="menu:main",
    )
    builder.adjust(1)
    return builder.as_markup()


def products_keyboard(
    products: list[dict],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for product in products:
        icon = "📥" if product["product_type"] == "digital" else "📦"
        builder.button(
            text=f"{icon} {product['name']}",
            callback_data=f"catalog:product:{product['id']}",
        )

    builder.button(
        text="⬅️ Categorie",
        callback_data="catalog:categories",
    )
    builder.adjust(1)
    return builder.as_markup()


def product_keyboard(
    product_id: int,
    category_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Aggiungi al carrello",
                    callback_data=f"cart:add:{product_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Torna ai prodotti",
                    callback_data=f"catalog:category:{category_id}",
                )
            ],
        ]
    )


def cart_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if any(item["product_type"] == "digital" for item in items):
        builder.button(
            text="⭐ Checkout prodotti digitali",
            callback_data="checkout:digital",
        )

    if any(item["product_type"] == "physical" for item in items):
        builder.button(
            text="📦 Checkout prodotti fisici",
            callback_data="checkout:physical",
        )

    for item in items:
        builder.button(
            text=f"❌ Rimuovi {item['name']}",
            callback_data=f"cart:remove:{item['id']}",
        )

    builder.button(
        text="🗑 Svuota il carrello",
        callback_data="cart:clear",
    )
    builder.button(
        text="🛍 Continua gli acquisti",
        callback_data="catalog:categories",
    )
    builder.button(
        text="⬅️ Menu principale",
        callback_data="menu:main",
    )
    builder.adjust(1)
    return builder.as_markup()


def demo_payment_keyboard(
    order_id: int,
    payment_token: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Completa pagamento demo",
                    callback_data=(
                        f"paydemo:{order_id}:{payment_token}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Torna al carrello",
                    callback_data="cart:show",
                )
            ],
        ]
    )


def stars_invoice_keyboard(
    invoice_link: str,
    stars: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⭐ Paga {stars} Stars",
                    url=invoice_link,
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Torna al carrello",
                    callback_data="cart:show",
                )
            ],
        ]
    )


def cancel_checkout_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Annulla checkout",
                    callback_data="checkout:cancel",
                )
            ]
        ]
    )


def confirm_physical_order_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Conferma ordine fisico",
                    callback_data="checkout:physical:confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Annulla checkout",
                    callback_data="checkout:cancel",
                )
            ],
        ]
    )


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Menu principale",
                    callback_data="menu:main",
                )
            ]
        ]
    )
