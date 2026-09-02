from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.database.repository import Database, format_product_price
from app.keyboards.menus import (
    back_to_main_keyboard,
    categories_keyboard,
    product_keyboard,
    products_keyboard,
)


router = Router(name="catalog")


async def replace_with_text(
    callback: CallbackQuery,
    text: str,
    reply_markup,
) -> None:
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=reply_markup)
    else:
        await callback.message.edit_text(text, reply_markup=reply_markup)


@router.callback_query(F.data == "catalog:categories")
async def callback_categories(
    callback: CallbackQuery,
    database: Database,
) -> None:
    categories = await database.list_active_categories()

    if callback.message is None:
        await callback.answer()
        return

    if not categories:
        await replace_with_text(
            callback,
            "⚠️ Il catalogo non contiene prodotti disponibili.",
            back_to_main_keyboard(),
        )
        await callback.answer()
        return

    await replace_with_text(
        callback,
        "🛍 <b>Scegli una categoria:</b>",
        categories_keyboard(categories),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:category:"))
async def callback_category(
    callback: CallbackQuery,
    database: Database,
) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return

    try:
        category_id = int(callback.data.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Categoria non valida.", show_alert=True)
        return

    category = await database.get_active_category(category_id)

    if category is None:
        await callback.answer(
            "Questa categoria non è più disponibile.",
            show_alert=True,
        )
        return

    products = await database.list_active_products(category_id)

    if not products:
        await replace_with_text(
            callback,
            f"📁 <b>{escape(category['name'])}</b>\n\n"
            "Nessun prodotto disponibile.",
            back_to_main_keyboard(),
        )
        await callback.answer()
        return

    await replace_with_text(
        callback,
        f"📁 <b>{escape(category['name'])}</b>\n\n"
        "Seleziona un prodotto:",
        products_keyboard(products),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:product:"))
async def callback_product(
    callback: CallbackQuery,
    database: Database,
) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return

    try:
        product_id = int(callback.data.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Prodotto non valido.", show_alert=True)
        return

    product = await database.get_active_product(product_id)

    if product is None:
        await callback.answer(
            "Questo prodotto non è più disponibile.",
            show_alert=True,
        )
        return

    if product["product_type"] == "digital":
        type_text = "📥 Prodotto digitale"
        availability = "Consegna automatica dopo il pagamento"
    else:
        type_text = "📦 Prodotto fisico"
        stock = product["stock_quantity"]
        availability = (
            f"Disponibilità: {stock} pezzi"
            if stock is not None
            else "Disponibilità da confermare"
        )

    description = product["description"]

    if product["photo_file_id"] and len(description) > 650:
        description = description[:647].rstrip() + "..."

    text = (
        f"<b>{escape(product['name'])}</b>\n\n"
        f"{escape(description)}\n\n"
        f"{type_text}\n"
        f"Prezzo: <b>{escape(format_product_price(product))}</b>\n"
        f"{escape(availability)}\n\n"
        f"Codice: <code>{escape(product['sku'])}</code>"
    )
    keyboard = product_keyboard(
        product_id=product["id"],
        category_id=product["category_id"],
    )

    if product["photo_file_id"]:
        await callback.message.delete()
        await callback.message.answer_photo(
            product["photo_file_id"],
            caption=text,
            reply_markup=keyboard,
        )
    else:
        await replace_with_text(callback, text, keyboard)

    await callback.answer()
