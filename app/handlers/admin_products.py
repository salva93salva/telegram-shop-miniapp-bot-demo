from __future__ import annotations

from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import Settings
from app.database.repository import Database, format_product_price
from app.handlers.admin import (
    admin_menu_keyboard,
    authorize_callback,
    private_admin_message,
)


router = Router(name="admin_products")


class NewProduct(StatesGroup):
    product_type = State()
    name = State()
    description = State()
    price = State()
    stock = State()
    delivery = State()
    photo = State()


class EditProduct(StatesGroup):
    value = State()
    photo = State()
    delivery = State()


def product_back_keyboard(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Torna al prodotto",
                    callback_data=f"admin:product:{product_id}",
                )
            ]
        ]
    )


def skip_photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Continua senza foto",
                    callback_data="admin:new:photo:skip",
                )
            ]
        ]
    )


def parse_euro_price(value: str) -> int | None:
    normalized = value.strip().replace(",", ".")

    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None

    cents = amount * 100

    if amount < 0 or cents != cents.to_integral_value():
        return None

    result = int(cents)
    return result if result <= 100_000_000 else None


async def require_admin_message(
    message: Message,
    settings: Settings,
) -> bool:
    if private_admin_message(message, settings):
        return True

    await message.answer("⛔ Accesso non autorizzato.")
    return False


async def ask_for_photo(message: Message, state: FSMContext) -> None:
    await state.set_state(NewProduct.photo)
    await message.answer(
        "🖼 Invia una foto del prodotto oppure premi "
        "<b>Continua senza foto</b>.",
        reply_markup=skip_photo_keyboard(),
    )


async def finish_new_product(
    message: Message,
    state: FSMContext,
    database: Database,
    photo_file_id: str | None,
) -> None:
    data = await state.get_data()

    try:
        product = await database.create_product(
            product_type=data["product_type"],
            name=data["name"],
            description=data["description"],
            price_stars=data.get("price_stars"),
            price_cents=data.get("price_cents"),
            stock_quantity=data.get("stock_quantity"),
            delivery_content=data.get("delivery_content"),
            delivery_file_id=data.get("delivery_file_id"),
            photo_file_id=photo_file_id,
        )
    except (KeyError, ValueError, RuntimeError) as error:
        await state.clear()
        await message.answer(
            f"⚠️ Prodotto non creato: {escape(str(error))}",
            reply_markup=admin_menu_keyboard(),
        )
        return

    await state.clear()
    await message.answer(
        "✅ <b>Prodotto creato</b>\n\n"
        f"Nome: {escape(product['name'])}\n"
        f"Codice: <code>{escape(product['sku'])}</code>\n"
        f"Prezzo: {escape(format_product_price(product))}",
        reply_markup=product_back_keyboard(product["id"]),
    )


@router.message(Command("cancel"))
async def cancel_admin_product_action(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    current_state = await state.get_state()

    if current_state is None:
        return

    if not await require_admin_message(message, settings):
        return

    await state.clear()
    await message.answer(
        "Operazione annullata.",
        reply_markup=admin_menu_keyboard(),
    )


@router.callback_query(F.data == "admin:add")
async def start_new_product(
    callback: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    await state.clear()
    await state.set_state(NewProduct.product_type)
    await callback.message.edit_text(
        "➕ <b>Nuovo prodotto</b>\n\nScegli il tipo:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📥 Digitale",
                        callback_data="admin:new:type:digital",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📦 Fisico",
                        callback_data="admin:new:type:physical",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Annulla",
                        callback_data="admin:products",
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(
    NewProduct.product_type,
    F.data.startswith("admin:new:type:"),
)
async def receive_new_product_type(
    callback: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    product_type = (callback.data or "").rsplit(":", 1)[-1]

    if product_type not in {"digital", "physical"}:
        await callback.answer("Tipo non valido.", show_alert=True)
        return

    await state.update_data(product_type=product_type)
    await state.set_state(NewProduct.name)
    await callback.message.edit_text(
        "Scrivi il <b>nome del prodotto</b> (massimo 120 caratteri).\n\n"
        "Per interrompere usa /cancel."
    )
    await callback.answer()


@router.message(NewProduct.name, F.text)
async def receive_new_product_name(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await require_admin_message(message, settings):
        return

    value = (message.text or "").strip()

    if not 1 <= len(value) <= 120:
        await message.answer("Inserisci un nome da 1 a 120 caratteri.")
        return

    await state.update_data(name=value)
    await state.set_state(NewProduct.description)
    await message.answer(
        "Scrivi la <b>descrizione</b> del prodotto "
        "(massimo 1000 caratteri)."
    )


@router.message(NewProduct.description, F.text)
async def receive_new_product_description(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await require_admin_message(message, settings):
        return

    value = (message.text or "").strip()

    if not 1 <= len(value) <= 1000:
        await message.answer(
            "Inserisci una descrizione da 1 a 1000 caratteri."
        )
        return

    data = await state.get_data()
    await state.update_data(description=value)
    await state.set_state(NewProduct.price)

    if data["product_type"] == "digital":
        prompt = "Inserisci il prezzo in <b>Telegram Stars</b>, ad esempio 75."
    else:
        prompt = "Inserisci il prezzo in <b>euro</b>, ad esempio 24,90."

    await message.answer(prompt)


@router.message(NewProduct.price, F.text)
async def receive_new_product_price(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await require_admin_message(message, settings):
        return

    data = await state.get_data()
    value = (message.text or "").strip()

    if data["product_type"] == "digital":
        try:
            price_stars = int(value)
        except ValueError:
            price_stars = 0

        if not 1 <= price_stars <= 1_000_000:
            await message.answer("Inserisci un numero intero di Stars maggiore di 0.")
            return

        await state.update_data(price_stars=price_stars)
        await state.set_state(NewProduct.delivery)
        await message.answer(
            "📎 Invia il <b>file digitale</b> da consegnare al cliente "
            "oppure scrivi un link o un testo di consegna."
        )
        return

    price_cents = parse_euro_price(value)

    if price_cents is None:
        await message.answer("Prezzo non valido. Esempio corretto: 24,90")
        return

    await state.update_data(price_cents=price_cents)
    await state.set_state(NewProduct.stock)
    await message.answer("Inserisci la <b>quantità iniziale disponibile</b>.")


@router.message(NewProduct.stock, F.text)
async def receive_new_product_stock(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await require_admin_message(message, settings):
        return

    try:
        stock = int((message.text or "").strip())
    except ValueError:
        stock = -1

    if not 0 <= stock <= 1_000_000:
        await message.answer("Inserisci una quantità intera da 0 in su.")
        return

    await state.update_data(stock_quantity=stock)
    await ask_for_photo(message, state)


@router.message(NewProduct.delivery, F.document)
async def receive_new_product_document(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await require_admin_message(message, settings):
        return

    await state.update_data(
        delivery_file_id=message.document.file_id,
        delivery_content=None,
    )
    await ask_for_photo(message, state)


@router.message(NewProduct.delivery, F.text)
async def receive_new_product_delivery_text(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await require_admin_message(message, settings):
        return

    value = (message.text or "").strip()

    if not 1 <= len(value) <= 2000:
        await message.answer("Inserisci un testo o link da 1 a 2000 caratteri.")
        return

    await state.update_data(
        delivery_content=value,
        delivery_file_id=None,
    )
    await ask_for_photo(message, state)


@router.message(NewProduct.delivery)
async def reject_new_product_delivery(message: Message) -> None:
    await message.answer("Invia un documento oppure scrivi un link o un testo.")


@router.message(NewProduct.photo, F.photo)
async def receive_new_product_photo(
    message: Message,
    settings: Settings,
    state: FSMContext,
    database: Database,
) -> None:
    if not await require_admin_message(message, settings):
        return

    await finish_new_product(
        message,
        state,
        database,
        message.photo[-1].file_id,
    )


@router.callback_query(
    NewProduct.photo,
    F.data == "admin:new:photo:skip",
)
async def skip_new_product_photo(
    callback: CallbackQuery,
    settings: Settings,
    state: FSMContext,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    await finish_new_product(
        callback.message,
        state,
        database,
        None,
    )
    await callback.answer()


@router.message(NewProduct.photo)
async def reject_new_product_photo(message: Message) -> None:
    await message.answer("Invia una foto oppure usa il pulsante per saltarla.")


@router.callback_query(F.data.startswith("admin:editmenu:"))
async def show_edit_product_menu(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    try:
        product_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Prodotto non valido.", show_alert=True)
        return

    product = await database.get_admin_product(product_id)

    if product is None:
        await callback.answer("Prodotto non trovato.", show_alert=True)
        return

    await state.clear()
    builder = InlineKeyboardBuilder()

    for field, label in (
        ("name", "Nome"),
        ("description", "Descrizione"),
        ("price", "Prezzo"),
        ("photo", "Foto"),
    ):
        builder.button(
            text=f"✏️ {label}",
            callback_data=f"admin:edit:{product_id}:{field}",
        )

    if product["product_type"] == "physical":
        builder.button(
            text="✏️ Scorta",
            callback_data=f"admin:edit:{product_id}:stock",
        )
    else:
        builder.button(
            text="✏️ File o consegna",
            callback_data=f"admin:edit:{product_id}:delivery",
        )

    builder.button(
        text="⬅️ Torna al prodotto",
        callback_data=f"admin:product:{product_id}",
    )
    builder.adjust(1)
    await callback.message.edit_text(
        f"✏️ <b>Modifica {escape(product['name'])}</b>\n\n"
        "Scegli il dato da modificare:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:edit:"))
async def start_edit_product_field(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 4 or parts[3] not in {
        "name", "description", "price", "stock", "photo", "delivery"
    }:
        await callback.answer("Richiesta non valida.", show_alert=True)
        return

    try:
        product_id = int(parts[2])
    except ValueError:
        await callback.answer("Prodotto non valido.", show_alert=True)
        return

    product = await database.get_admin_product(product_id)

    if product is None:
        await callback.answer("Prodotto non trovato.", show_alert=True)
        return

    field = parts[3]
    await state.clear()
    await state.update_data(
        product_id=product_id,
        product_type=product["product_type"],
        edit_field=field,
    )

    prompts = {
        "name": "Scrivi il nuovo nome del prodotto.",
        "description": "Scrivi la nuova descrizione.",
        "price": (
            "Inserisci il nuovo prezzo in Stars."
            if product["product_type"] == "digital"
            else "Inserisci il nuovo prezzo in euro, ad esempio 24,90."
        ),
        "stock": "Inserisci la nuova quantità disponibile.",
        "photo": "Invia la nuova foto oppure usa /removephoto per rimuoverla.",
        "delivery": (
            "Invia il nuovo file digitale oppure scrivi il nuovo link "
            "o testo di consegna."
        ),
    }

    if field == "photo":
        await state.set_state(EditProduct.photo)
    elif field == "delivery":
        await state.set_state(EditProduct.delivery)
    else:
        await state.set_state(EditProduct.value)

    await callback.message.edit_text(
        prompts[field] + "\n\nPer interrompere usa /cancel."
    )
    await callback.answer()


@router.message(EditProduct.value, F.text)
async def receive_product_edit_value(
    message: Message,
    settings: Settings,
    state: FSMContext,
    database: Database,
) -> None:
    if not await require_admin_message(message, settings):
        return

    data = await state.get_data()
    field = data["edit_field"]
    product_id = data["product_id"]
    value = (message.text or "").strip()

    if field in {"name", "description"}:
        updated = await database.update_product_text(
            product_id,
            field,
            value,
        )
    elif field == "price":
        if data["product_type"] == "digital":
            try:
                amount = int(value)
            except ValueError:
                amount = 0
        else:
            parsed = parse_euro_price(value)
            amount = parsed if parsed is not None else -1
        updated = await database.update_product_price(product_id, amount)
    else:
        try:
            amount = int(value)
        except ValueError:
            amount = -1
        updated = await database.set_product_stock(product_id, amount)

    if not updated:
        await message.answer("Valore non valido. Riprova oppure usa /cancel.")
        return

    await state.clear()
    await message.answer(
        "✅ Prodotto aggiornato.",
        reply_markup=product_back_keyboard(product_id),
    )


@router.message(EditProduct.photo, Command("removephoto"))
async def remove_product_photo(
    message: Message,
    settings: Settings,
    state: FSMContext,
    database: Database,
) -> None:
    if not await require_admin_message(message, settings):
        return

    data = await state.get_data()
    await database.update_product_photo(data["product_id"], None)
    await state.clear()
    await message.answer(
        "✅ Foto rimossa.",
        reply_markup=product_back_keyboard(data["product_id"]),
    )


@router.message(EditProduct.photo, F.photo)
async def replace_product_photo(
    message: Message,
    settings: Settings,
    state: FSMContext,
    database: Database,
) -> None:
    if not await require_admin_message(message, settings):
        return

    data = await state.get_data()
    await database.update_product_photo(
        data["product_id"],
        message.photo[-1].file_id,
    )
    await state.clear()
    await message.answer(
        "✅ Foto aggiornata.",
        reply_markup=product_back_keyboard(data["product_id"]),
    )


@router.message(EditProduct.photo)
async def reject_product_photo_edit(message: Message) -> None:
    await message.answer("Invia una foto oppure usa /removephoto.")


async def finish_delivery_edit(
    message: Message,
    state: FSMContext,
    database: Database,
    *,
    delivery_content: str | None,
    delivery_file_id: str | None,
) -> None:
    data = await state.get_data()
    updated = await database.update_digital_delivery(
        data["product_id"],
        delivery_content=delivery_content,
        delivery_file_id=delivery_file_id,
    )

    if not updated:
        await message.answer("Contenuto non valido. Riprova oppure usa /cancel.")
        return

    await state.clear()
    await message.answer(
        "✅ Consegna digitale aggiornata.",
        reply_markup=product_back_keyboard(data["product_id"]),
    )


@router.message(EditProduct.delivery, F.document)
async def replace_delivery_document(
    message: Message,
    settings: Settings,
    state: FSMContext,
    database: Database,
) -> None:
    if not await require_admin_message(message, settings):
        return

    await finish_delivery_edit(
        message,
        state,
        database,
        delivery_content=None,
        delivery_file_id=message.document.file_id,
    )


@router.message(EditProduct.delivery, F.text)
async def replace_delivery_text(
    message: Message,
    settings: Settings,
    state: FSMContext,
    database: Database,
) -> None:
    if not await require_admin_message(message, settings):
        return

    value = (message.text or "").strip()

    if not 1 <= len(value) <= 2000:
        await message.answer("Inserisci un testo o link da 1 a 2000 caratteri.")
        return

    await finish_delivery_edit(
        message,
        state,
        database,
        delivery_content=value,
        delivery_file_id=None,
    )


@router.message(EditProduct.delivery)
async def reject_delivery_edit(message: Message) -> None:
    await message.answer("Invia un documento oppure scrivi un link o un testo.")
