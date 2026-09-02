from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.database.repository import (
    CartError,
    Database,
    cart_totals,
    format_product_price,
)
from app.keyboards.menus import (
    back_to_main_keyboard,
    cart_keyboard,
)


router = Router(name="cart")


def cart_text(items: list[dict]) -> str:
    lines = ["🛒 <b>Il tuo carrello</b>"]

    for item in items:
        lines.append(
            "\n"
            f"• <b>{escape(item['name'])}</b>\n"
            f"  Quantità: {item['quantity']}\n"
            f"  Prezzo unitario: "
            f"{escape(format_product_price(item))}"
        )

    totals = cart_totals(items)
    lines.append("\n<b>Totali separati:</b>")

    if totals["stars"]:
        lines.append(f"⭐ Digitali: {totals['stars']} Stars")

    if totals["cents"]:
        euros, cents = divmod(totals["cents"], 100)
        lines.append(f"📦 Fisici: {euros},{cents:02d} EUR")

    lines.append(
        "\nI due totali saranno pagati separatamente perché "
        "seguono sistemi di pagamento differenti."
    )
    return "\n".join(lines)


async def show_cart(
    callback: CallbackQuery,
    database: Database,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    items = await database.list_cart_items(callback.from_user.id)

    if not items:
        await callback.message.edit_text(
            "🛒 <b>Il tuo carrello è vuoto.</b>\n\n"
            "Sfoglia il catalogo e scegli un prodotto.",
            reply_markup=back_to_main_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        cart_text(items),
        reply_markup=cart_keyboard(items),
    )
    await callback.answer()


@router.callback_query(F.data == "cart:show")
async def callback_show_cart(
    callback: CallbackQuery,
    database: Database,
) -> None:
    await show_cart(callback, database)


@router.callback_query(F.data.startswith("cart:add:"))
async def callback_add_to_cart(
    callback: CallbackQuery,
    database: Database,
) -> None:
    if callback.data is None:
        await callback.answer()
        return

    try:
        product_id = int(callback.data.rsplit(":", 1)[1])
        quantity = await database.add_to_cart(
            telegram_user_id=callback.from_user.id,
            product_id=product_id,
        )
    except CartError as error:
        await callback.answer(str(error), show_alert=True)
        return
    except (IndexError, ValueError):
        await callback.answer(
            "Prodotto non valido.",
            show_alert=True,
        )
        return

    await callback.answer(
        f"✅ Aggiunto al carrello. Quantità: {quantity}",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("cart:remove:"))
async def callback_remove_from_cart(
    callback: CallbackQuery,
    database: Database,
) -> None:
    if callback.data is None:
        await callback.answer()
        return

    try:
        product_id = int(callback.data.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Prodotto non valido.", show_alert=True)
        return

    await database.remove_from_cart(
        telegram_user_id=callback.from_user.id,
        product_id=product_id,
    )
    await show_cart(callback, database)


@router.callback_query(F.data == "cart:clear")
async def callback_clear_cart(
    callback: CallbackQuery,
    database: Database,
) -> None:
    await database.clear_cart(callback.from_user.id)
    await show_cart(callback, database)
