from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import Settings
from app.database.repository import (
    Database,
    format_product_price,
)


router = Router(name="admin")

FULFILLMENT_LABELS = {
    "new": "Nuovo",
    "processing": "In lavorazione",
    "shipped": "Spedito",
    "completed": "Completato",
    "cancelled": "Annullato",
}

ORDER_FILTER_LABELS = {
    "open": "Da gestire",
    "completed": "Completati",
    "cancelled": "Annullati",
    "digital": "Digitali",
    "physical": "Fisici",
    "all": "Tutti",
}
ORDERS_PER_PAGE = 10


class OrderSearch(StatesGroup):
    query = State()
    results = State()


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Statistiche",
                    callback_data="admin:stats",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧾 Ordini",
                    callback_data="admin:orders",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Prodotti e scorte",
                    callback_data="admin:products",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🩺 Stato servizio",
                    callback_data="admin:health",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💾 Scarica backup",
                    callback_data="admin:backup",
                )
            ],
        ]
    )


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Pannello amministratore",
                    callback_data="admin:main",
                )
            ]
        ]
    )


def is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


def private_admin_message(
    message: Message,
    settings: Settings,
) -> bool:
    return (
        message.chat.type == ChatType.PRIVATE
        and message.from_user is not None
        and is_admin(message.from_user.id, settings)
    )


async def authorize_callback(
    callback: CallbackQuery,
    settings: Settings,
) -> bool:
    if (
        callback.message is None
        or callback.message.chat.type != ChatType.PRIVATE
        or not is_admin(callback.from_user.id, settings)
    ):
        await callback.answer("Accesso non autorizzato.", show_alert=True)
        return False

    return True


@router.message(Command("admin"))
async def command_admin(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not private_admin_message(message, settings):
        await message.answer("⛔ Accesso non autorizzato.")
        return

    await state.clear()
    await message.answer(
        "🛠 <b>Pannello amministratore</b>\n\n"
        "Seleziona una sezione:",
        reply_markup=admin_menu_keyboard(),
    )


def health_text(
    settings: Settings,
    database: Database,
    stats: dict,
) -> str:
    database_ok = database.database_path.is_file()
    database_size = (
        database.database_path.stat().st_size
        if database_ok
        else 0
    )
    return (
        "🩺 <b>Stato del servizio</b>\n\n"
        "Bot: <b>OK</b>\n"
        f"Negozio: <b>{escape(settings.shop_name)}</b>\n"
        f"Modalità pagamento: <b>"
        f"{escape(settings.payment_mode)}</b>\n"
        f"Database: <b>{'OK' if database_ok else 'ERRORE'}</b>"
        f" — {database_size} byte\n"
        f"Prodotti attivi: <b>{stats['products_active']}</b>\n"
        f"Ordini registrati: <b>{stats['orders_total']}</b>"
    )


async def send_database_backup(
    message: Message,
    database: Database,
) -> bool:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    with TemporaryDirectory(prefix="telegram-shop-backup-") as folder:
        destination = Path(folder) / f"shop-backup-{timestamp}.db"
        created = await database.backup_to(destination)

        if not created:
            return False

        await message.answer_document(
            FSInputFile(destination),
            caption=(
                "💾 <b>Backup database completato</b>\n\n"
                "Conserva questo file in un luogo sicuro: può "
                "contenere dati personali e dettagli degli ordini."
            ),
        )

    return True


@router.message(Command("health"))
async def command_health(
    message: Message,
    settings: Settings,
    database: Database,
) -> None:
    if not private_admin_message(message, settings):
        await message.answer("⛔ Accesso non autorizzato.")
        return

    stats = await database.get_admin_stats()
    await message.answer(health_text(settings, database, stats))


@router.message(Command("backup"))
async def command_backup(
    message: Message,
    settings: Settings,
    database: Database,
) -> None:
    if not private_admin_message(message, settings):
        await message.answer("⛔ Accesso non autorizzato.")
        return

    if not await send_database_backup(message, database):
        await message.answer("⚠️ Backup non disponibile.")


@router.callback_query(F.data == "admin:main")
async def callback_admin_main(
    callback: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Pannello amministratore</b>\n\n"
        "Seleziona una sezione:",
        reply_markup=admin_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:health")
async def callback_admin_health(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    stats = await database.get_admin_stats()
    await callback.message.edit_text(
        health_text(settings, database, stats),
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:backup")
async def callback_admin_backup(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    created = await send_database_backup(callback.message, database)
    await callback.answer(
        "Backup creato." if created else "Backup non disponibile.",
        show_alert=not created,
    )


@router.callback_query(F.data == "admin:stats")
async def callback_admin_stats(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    stats = await database.get_admin_stats()
    euros, cents = divmod(stats["physical_cents"], 100)
    await callback.message.edit_text(
        "📊 <b>Statistiche negozio</b>\n\n"
        f"Prodotti: {stats['products_total']}\n"
        f"Prodotti attivi: {stats['products_active']}\n"
        f"Ordini totali: {stats['orders_total']}\n"
        f"Ordini fisici aperti: {stats['physical_open']}\n\n"
        f"Vendite digitali registrate: "
        f"{stats['digital_stars']} Stars\n"
        f"Ordini fisici non annullati: "
        f"{euros},{cents:02d} EUR",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:orders")
async def callback_admin_orders(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    await state.clear()
    await show_admin_orders(callback, database, "open", 0)


def order_list_keyboard(
    orders: list[dict],
    filter_name: str,
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="🔎 Cerca ordine",
                callback_data="admin:ordersearch",
            )
        ],
        [
            InlineKeyboardButton(
                text=("• " if filter_name == "open" else "")
                + "Da gestire",
                callback_data="admin:orders:open:0",
            ),
            InlineKeyboardButton(
                text=("• " if filter_name == "completed" else "")
                + "Completati",
                callback_data="admin:orders:completed:0",
            ),
        ],
        [
            InlineKeyboardButton(
                text=("• " if filter_name == "cancelled" else "")
                + "Annullati",
                callback_data="admin:orders:cancelled:0",
            ),
            InlineKeyboardButton(
                text=("• " if filter_name == "digital" else "")
                + "Digitali",
                callback_data="admin:orders:digital:0",
            ),
        ],
        [
            InlineKeyboardButton(
                text=("• " if filter_name == "physical" else "")
                + "Fisici",
                callback_data="admin:orders:physical:0",
            ),
            InlineKeyboardButton(
                text=("• " if filter_name == "all" else "")
                + "Tutti",
                callback_data="admin:orders:all:0",
            ),
        ],
    ]

    for order in orders:
        icon = "⭐" if order["order_type"] == "digital" else "📦"
        status = FULFILLMENT_LABELS.get(
            order["fulfillment_status"],
            order["fulfillment_status"],
        )
        date_text = str(order["created_at"])[:10]
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{icon} #{order['id']} — {status} — {date_text}"
                    ),
                    callback_data=(
                        f"admin:order:{order['id']}:"
                        f"{filter_name}:{page}"
                    ),
                )
            ]
        )

    page_count = max(1, (total + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ Precedenti",
                callback_data=f"admin:orders:{filter_name}:{page - 1}",
            )
        )

    if page + 1 < page_count:
        navigation.append(
            InlineKeyboardButton(
                text="Successivi ➡️",
                callback_data=f"admin:orders:{filter_name}:{page + 1}",
            )
        )

    if navigation:
        rows.append(navigation)

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Pannello amministratore",
                callback_data="admin:main",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_admin_orders(
    callback: CallbackQuery,
    database: Database,
    filter_name: str,
    page: int,
) -> None:
    if filter_name not in ORDER_FILTER_LABELS:
        filter_name = "open"

    total = await database.count_admin_orders(filter_name)
    page_count = max(1, (total + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    safe_page = max(0, min(page, page_count - 1))
    orders = await database.list_admin_orders(
        limit=ORDERS_PER_PAGE,
        offset=safe_page * ORDERS_PER_PAGE,
        filter_name=filter_name,
    )
    label = ORDER_FILTER_LABELS[filter_name]
    await callback.message.edit_text(
        "🧾 <b>Gestione ordini</b>\n\n"
        f"Filtro: <b>{escape(label)}</b>\n"
        f"Risultati: {total} — pagina {safe_page + 1}/{page_count}\n\n"
        + (
            "Seleziona un ordine:"
            if orders
            else "Nessun ordine con questo filtro."
        ),
        reply_markup=order_list_keyboard(
            orders,
            filter_name,
            safe_page,
            total,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:orders:"))
async def callback_admin_orders_filtered(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 4 or parts[2] not in ORDER_FILTER_LABELS:
        await callback.answer("Filtro non valido.", show_alert=True)
        return

    try:
        page = int(parts[3])
    except ValueError:
        await callback.answer("Pagina non valida.", show_alert=True)
        return

    await state.clear()
    await show_admin_orders(callback, database, parts[2], page)


def search_results_keyboard(
    orders: list[dict],
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows = []

    for order in orders:
        icon = "⭐" if order["order_type"] == "digital" else "📦"
        status = FULFILLMENT_LABELS.get(
            order["fulfillment_status"],
            order["fulfillment_status"],
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} #{order['id']} — {status}",
                    callback_data=(
                        f"admin:order:{order['id']}:search:{page}"
                    ),
                )
            ]
        )

    page_count = max(1, (total + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ Precedenti",
                callback_data=f"admin:searchpage:{page - 1}",
            )
        )

    if page + 1 < page_count:
        navigation.append(
            InlineKeyboardButton(
                text="Successivi ➡️",
                callback_data=f"admin:searchpage:{page + 1}",
            )
        )

    if navigation:
        rows.append(navigation)

    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔎 Nuova ricerca",
                    callback_data="admin:ordersearch",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Ordini da gestire",
                    callback_data="admin:orders:open:0",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_search_results(
    message: Message,
    database: Database,
    query: str,
    page: int,
    *,
    edit: bool,
) -> None:
    total = await database.count_admin_order_search(query)
    page_count = max(1, (total + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    safe_page = max(0, min(page, page_count - 1))
    orders = await database.search_admin_orders(
        query,
        limit=ORDERS_PER_PAGE,
        offset=safe_page * ORDERS_PER_PAGE,
    )
    text = (
        "🔎 <b>Risultati ricerca ordini</b>\n\n"
        f"Ricerca: <code>{escape(query)}</code>\n"
        f"Risultati: {total} — pagina {safe_page + 1}/{page_count}\n\n"
        + ("Seleziona un ordine:" if orders else "Nessun ordine trovato.")
    )
    keyboard = search_results_keyboard(orders, safe_page, total)

    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin:ordersearch")
async def callback_admin_order_search(
    callback: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    await state.clear()
    await state.set_state(OrderSearch.query)
    await callback.message.edit_text(
        "🔎 <b>Cerca un ordine</b>\n\n"
        "Invia uno di questi dati:\n"
        "• numero ordine, ad esempio <code>125</code>\n"
        "• Telegram ID del cliente\n"
        "• data nel formato <code>2026-09-02</code>\n\n"
        "Per interrompere usa /cancel."
    )
    await callback.answer()


@router.message(OrderSearch.query, F.text)
async def receive_admin_order_search(
    message: Message,
    settings: Settings,
    database: Database,
    state: FSMContext,
) -> None:
    if not private_admin_message(message, settings):
        await message.answer("⛔ Accesso non autorizzato.")
        return

    query = (message.text or "").strip()
    valid_date = False

    if len(query) == 10:
        try:
            datetime.strptime(query, "%Y-%m-%d")
            valid_date = True
        except ValueError:
            pass

    if not query.isdigit() and not valid_date:
        await message.answer(
            "Formato non valido. Usa un numero ordine, un Telegram ID "
            "oppure una data come 2026-09-02."
        )
        return

    await state.update_data(order_search_query=query)
    await state.set_state(OrderSearch.results)
    await send_search_results(
        message,
        database,
        query,
        0,
        edit=False,
    )


@router.callback_query(F.data.startswith("admin:searchpage:"))
async def callback_admin_search_page(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    data = await state.get_data()
    query = data.get("order_search_query")

    if not query:
        await callback.answer(
            "Ricerca scaduta. Avviane una nuova.",
            show_alert=True,
        )
        return

    try:
        page = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Pagina non valida.", show_alert=True)
        return

    await send_search_results(
        callback.message,
        database,
        query,
        page,
        edit=True,
    )
    await callback.answer()


def order_admin_keyboard(
    order: dict,
    origin: str,
    page: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    transitions = {
        "new": (
            ("processing", "🛠 In lavorazione"),
            ("cancelled", "❌ Annulla ordine"),
        ),
        "processing": (
            ("shipped", "🚚 Spedito"),
            ("cancelled", "❌ Annulla ordine"),
        ),
        "shipped": (("completed", "✅ Completato"),),
    }

    if order["order_type"] == "physical":
        for value, label in transitions.get(
            order["fulfillment_status"],
            (),
        ):
            builder.button(
                text=label,
                callback_data=(
                    f"admin:status:{order['id']}:{value}:{origin}:{page}"
                ),
            )

    back_callback = (
        f"admin:searchpage:{page}"
        if origin == "search"
        else f"admin:orders:{origin}:{page}"
    )
    builder.button(
        text="⬅️ Elenco ordini",
        callback_data=back_callback,
    )
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data.startswith("admin:order:"))
async def callback_admin_order(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    parts = (callback.data or "").split(":")

    if len(parts) not in {3, 5}:
        await callback.answer("Ordine non valido.", show_alert=True)
        return

    try:
        order_id = int(parts[2])
        page = int(parts[4]) if len(parts) == 5 else 0
    except ValueError:
        await callback.answer("Ordine non valido.", show_alert=True)
        return

    origin = parts[3] if len(parts) == 5 else "open"

    if origin != "search" and origin not in ORDER_FILTER_LABELS:
        origin = "open"

    order = await database.get_admin_order(order_id)

    if order is None:
        await callback.answer("Ordine non trovato.", show_alert=True)
        return

    items = await database.list_order_items(order_id)
    item_lines = [
        f"• {escape(item['product_name'])} × {item['quantity']}"
        for item in items
    ]

    if order["order_type"] == "digital":
        total = f"{order['total_stars']} Stars"
        shipping = ""
    else:
        euros, cents = divmod(order["total_cents"], 100)
        total = f"{euros},{cents:02d} {order['currency']}"
        shipping = (
            "\n\n<b>Dati di spedizione</b>\n"
            f"{escape(order['shipping_name'] or '')}\n"
            f"{escape(order['shipping_address'] or '')}\n"
            f"{escape(order['shipping_city_postal'] or '')}\n"
            f"Telefono: {escape(order['shipping_phone'] or '')}"
        )

    status = FULFILLMENT_LABELS.get(
        order["fulfillment_status"],
        order["fulfillment_status"],
    )
    await callback.message.edit_text(
        f"🧾 <b>Ordine #{order_id}</b>\n\n"
        f"Cliente Telegram: <code>{order['telegram_user_id']}</code>\n"
        f"Tipo: {order['order_type']}\n"
        f"Stato: <b>{escape(status)}</b>\n"
        f"Totale: <b>{escape(total)}</b>\n\n"
        + "\n".join(item_lines)
        + shipping,
        reply_markup=order_admin_keyboard(order, origin, page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:status:"))
async def callback_admin_status(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    parts = (callback.data or "").split(":")

    if len(parts) not in {4, 6}:
        await callback.answer("Richiesta non valida.", show_alert=True)
        return

    try:
        order_id = int(parts[2])
        page = int(parts[5]) if len(parts) == 6 else 0
    except ValueError:
        await callback.answer("Ordine non valido.", show_alert=True)
        return


    origin = parts[4] if len(parts) == 6 else "open"

    if origin != "search" and origin not in ORDER_FILTER_LABELS:
        origin = "open"

    updated = await database.update_physical_order_status(
        order_id,
        parts[3],
    )

    if not updated:
        await callback.answer(
            "Stato non modificabile.",
            show_alert=True,
        )
        return

    await callback.answer("Stato aggiornato.")
    order = await database.get_admin_order(order_id)
    status = FULFILLMENT_LABELS[order["fulfillment_status"]]
    back_callback = (
        f"admin:searchpage:{page}"
        if origin == "search"
        else f"admin:orders:{origin}:{page}"
    )
    await callback.message.edit_text(
        f"✅ Ordine #{order_id} aggiornato: <b>{status}</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Elenco ordini",
                        callback_data=back_callback,
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data == "admin:products")
async def callback_admin_products(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
    state: FSMContext,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    await state.clear()
    products = await database.list_all_products()
    builder = InlineKeyboardBuilder()

    builder.button(
        text="➕ Aggiungi prodotto",
        callback_data="admin:add",
    )

    for product in products:
        status = "✅" if product["active"] else "⛔"
        builder.button(
            text=f"{status} {product['name']}",
            callback_data=f"admin:product:{product['id']}",
        )

    builder.button(
        text="⬅️ Pannello amministratore",
        callback_data="admin:main",
    )
    builder.adjust(1)
    await callback.message.edit_text(
        "📦 <b>Prodotti e scorte</b>\n\n"
        "Seleziona un prodotto:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:product:"))
async def callback_admin_product(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    try:
        product_id = int(callback.data.rsplit(":", 1)[1])
    except (AttributeError, ValueError):
        await callback.answer("Prodotto non valido.", show_alert=True)
        return

    products = await database.list_all_products()
    product = next(
        (item for item in products if item["id"] == product_id),
        None,
    )

    if product is None:
        await callback.answer("Prodotto non trovato.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(
        text=(
            "⛔ Disattiva"
            if product["active"]
            else "✅ Riattiva"
        ),
        callback_data=f"admin:toggle:{product_id}",
    )

    if product["product_type"] == "physical":
        builder.button(
            text="➖ Scorta",
            callback_data=f"admin:stock:{product_id}:minus",
        )
        builder.button(
            text="➕ Scorta",
            callback_data=f"admin:stock:{product_id}:plus",
        )

    builder.button(
        text="✏️ Modifica prodotto",
        callback_data=f"admin:editmenu:{product_id}",
    )
    builder.button(
        text="🗑 Elimina prodotto",
        callback_data=f"admin:delete:{product_id}",
    )

    builder.button(
        text="⬅️ Prodotti",
        callback_data="admin:products",
    )
    builder.adjust(1)
    stock = (
        str(product["stock_quantity"])
        if product["stock_quantity"] is not None
        else "non applicabile"
    )
    await callback.message.edit_text(
        f"📦 <b>{escape(product['name'])}</b>\n\n"
        f"Categoria: {escape(product['category_name'])}\n"
        f"Prezzo: {escape(format_product_price(product))}\n"
        f"Attivo: {'sì' if product['active'] else 'no'}\n"
        f"Scorta: {stock}\n"
        f"Foto: {'sì' if product['photo_file_id'] else 'no'}\n"
        f"Consegna digitale: "
        f"{'configurata' if product['product_type'] == 'digital' and (product['delivery_file_id'] or product['delivery_content']) else 'non applicabile'}",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delete:"))
async def callback_admin_delete_product(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
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

    await callback.message.edit_text(
        "⚠️ <b>Conferma eliminazione</b>\n\n"
        f"Prodotto: <b>{escape(product['name'])}</b>\n\n"
        "Il prodotto sparirà dal catalogo e verrà rimosso dai "
        "carrelli. Gli ordini già registrati conserveranno i dati "
        "dell'acquisto.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑 Sì, elimina definitivamente",
                        callback_data=f"admin:deleteconfirm:{product_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Annulla",
                        callback_data=f"admin:product:{product_id}",
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:deleteconfirm:"))
async def callback_admin_confirm_delete_product(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    try:
        product_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Prodotto non valido.", show_alert=True)
        return

    deleted = await database.delete_product(product_id)

    if not deleted:
        await callback.answer("Prodotto non trovato.", show_alert=True)
        return

    await callback.message.edit_text(
        "✅ Prodotto eliminato definitivamente.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Prodotti e scorte",
                        callback_data="admin:products",
                    )
                ]
            ]
        ),
    )
    await callback.answer("Prodotto eliminato.")


@router.callback_query(F.data.startswith("admin:toggle:"))
async def callback_admin_toggle_product(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    try:
        product_id = int(callback.data.rsplit(":", 1)[1])
    except (AttributeError, ValueError):
        await callback.answer("Prodotto non valido.", show_alert=True)
        return

    products = await database.list_all_products()
    product = next(
        (item for item in products if item["id"] == product_id),
        None,
    )

    if product is None:
        await callback.answer("Prodotto non trovato.", show_alert=True)
        return

    await database.set_product_active(product_id, not product["active"])
    await callback.answer("Prodotto aggiornato.")
    await callback.message.edit_text(
        "✅ Stato prodotto aggiornato.",
        reply_markup=admin_back_keyboard(),
    )


@router.callback_query(F.data.startswith("admin:stock:"))
async def callback_admin_stock(
    callback: CallbackQuery,
    settings: Settings,
    database: Database,
) -> None:
    if not await authorize_callback(callback, settings):
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 4:
        await callback.answer("Richiesta non valida.", show_alert=True)
        return

    try:
        product_id = int(parts[2])
    except ValueError:
        await callback.answer("Prodotto non valido.", show_alert=True)
        return

    if parts[3] not in {"plus", "minus"}:
        await callback.answer("Richiesta non valida.", show_alert=True)
        return

    change = 1 if parts[3] == "plus" else -1
    updated = await database.adjust_product_stock(product_id, change)

    if not updated:
        await callback.answer(
            "Scorta non modificabile.",
            show_alert=True,
        )
        return

    await callback.answer("Scorta aggiornata.")
    await callback.message.edit_text(
        "✅ Scorta aggiornata.",
        reply_markup=admin_back_keyboard(),
    )
