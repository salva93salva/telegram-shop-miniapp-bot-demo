from __future__ import annotations

from html import escape
import logging
import re
import secrets

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.methods import CreateInvoiceLink
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.config import Settings
from app.database.repository import Database, OrderError
from app.keyboards.menus import (
    back_to_main_keyboard,
    cancel_checkout_keyboard,
    confirm_physical_order_keyboard,
    demo_payment_keyboard,
    stars_invoice_keyboard,
)


router = Router(name="orders")


class PhysicalCheckout(StatesGroup):
    shipping_name = State()
    shipping_address = State()
    shipping_city_postal = State()
    shipping_phone = State()
    confirmation = State()


def build_invoice_payload(
    order_id: int,
    telegram_user_id: int,
    payment_token: str,
) -> str:
    return (
        f"shop:{order_id}:{telegram_user_id}:{payment_token}"
    )


def parse_invoice_payload(
    payload: str,
) -> tuple[int, int, str] | None:
    parts = payload.split(":")

    if len(parts) != 4 or parts[0] != "shop":
        return None

    try:
        return int(parts[1]), int(parts[2]), parts[3]
    except ValueError:
        return None


async def send_digital_delivery(
    message: Message,
    database: Database,
    order_id: int,
    payment_label: str,
) -> None:
    items = await database.list_order_items(order_id)

    await message.answer(
        f"✅ <b>{escape(payment_label)}</b>\n\n"
        f"Ordine #{order_id}\n\n"
        "I contenuti acquistati vengono consegnati qui sotto."
    )

    for item in items:
        title = f"📥 <b>{escape(item['product_name'])}</b>"

        if item["delivery_file_id"]:
            await message.answer_document(
                item["delivery_file_id"],
                caption=title,
            )
            continue

        content = item["delivery_content"] or (
            "Contenuto dimostrativo non configurato"
        )
        await message.answer(
            f"{title}\n{escape(content)}"
        )

    await message.answer(
        "Conserva questi messaggi per ritrovare i contenuti acquistati.",
        reply_markup=back_to_main_keyboard(),
    )


async def notify_admins_about_order(
    bot: Bot,
    settings: Settings,
    database: Database,
    order_id: int,
) -> None:
    if not settings.admin_ids:
        return

    order = await database.get_admin_order(order_id)

    if order is None:
        return

    if order["order_type"] == "digital":
        total = f"{order['total_stars']} Stars"
        icon = "⭐"
    else:
        euros, cents = divmod(order["total_cents"], 100)
        total = f"{euros},{cents:02d} {order['currency']}"
        icon = "📦"

    notification = (
        f"{icon} <b>Nuovo ordine #{order_id}</b>\n\n"
        f"Tipo: {order['order_type']}\n"
        f"Totale: {total}\n"
        f"Cliente Telegram: <code>"
        f"{order['telegram_user_id']}</code>\n\n"
        "Apri /admin per visualizzare i dettagli."
    )

    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, notification)
        except Exception:
            logging.exception(
                "Impossibile notificare l'amministratore %s",
                admin_id,
            )


@router.callback_query(F.data == "checkout:digital")
async def callback_digital_checkout(
    callback: CallbackQuery,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        order = await database.create_digital_order(
            callback.from_user.id
        )
    except OrderError as error:
        await callback.answer(str(error), show_alert=True)
        return

    if settings.payment_mode == "demo":
        await callback.message.edit_text(
            f"⭐ <b>Ordine digitale #{order['id']}</b>\n\n"
            f"Totale: <b>{order['total_stars']} Stars</b>\n\n"
            "Questa è una simulazione gratuita: non verranno "
            "prelevate Stars. Dopo la conferma riceverai i "
            "contenuti dimostrativi.",
            reply_markup=demo_payment_keyboard(
                order["id"],
                order["payment_token"],
            ),
        )
    else:
        payload = build_invoice_payload(
            order["id"],
            callback.from_user.id,
            order["payment_token"],
        )
        invoice_link = await bot(
            CreateInvoiceLink(
                title=f"Ordine digitale #{order['id']}",
                description=(
                    "Prodotti digitali con consegna automatica "
                    "dopo la conferma del pagamento."
                ),
                payload=payload,
                currency="XTR",
                prices=[
                    LabeledPrice(
                        label=f"Ordine #{order['id']}",
                        amount=order["total_stars"],
                    )
                ],
            )
        )
        await callback.message.edit_text(
            f"⭐ <b>Ordine digitale #{order['id']}</b>\n\n"
            f"Totale reale: <b>{order['total_stars']} Stars</b>\n\n"
            "Premi il pulsante soltanto se vuoi effettuare "
            "un pagamento reale.",
            reply_markup=stars_invoice_keyboard(
                invoice_link,
                order["total_stars"],
            ),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("paydemo:"))
async def callback_demo_payment(
    callback: CallbackQuery,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return

    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer("Pagamento non valido.", show_alert=True)
        return

    try:
        order_id = int(parts[1])
    except ValueError:
        await callback.answer("Ordine non valido.", show_alert=True)
        return

    completed = await database.complete_digital_order(
        order_id=order_id,
        telegram_user_id=callback.from_user.id,
        payment_token=parts[2],
        payment_reference=f"demo-{secrets.token_hex(8)}",
        payment_method="demo",
    )

    if not completed:
        await callback.answer(
            "Ordine già elaborato o conferma non valida.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "✅ Pagamento demo verificato. Invio dei contenuti…"
    )
    await send_digital_delivery(
        callback.message,
        database,
        order_id,
        "Pagamento demo completato",
    )
    await notify_admins_about_order(
        bot,
        settings,
        database,
        order_id,
    )
    await callback.answer()


@router.pre_checkout_query()
async def approve_pre_checkout(
    query: PreCheckoutQuery,
    database: Database,
) -> None:
    parsed = parse_invoice_payload(query.invoice_payload)

    if parsed is None:
        await query.answer(
            ok=False,
            error_message="Dati del pagamento non validi.",
        )
        return

    order_id, expected_user_id, payment_token = parsed
    order = await database.get_pending_digital_order(
        order_id,
        expected_user_id,
        payment_token,
    )
    valid = (
        order is not None
        and query.from_user.id == expected_user_id
        and query.currency == "XTR"
        and query.total_amount == order["total_stars"]
    )

    if not valid:
        await query.answer(
            ok=False,
            error_message=(
                "Ordine o importo non validi. Torna al carrello "
                "e crea un nuovo checkout."
            ),
        )
        return

    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_stars_payment(
    message: Message,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    payment = message.successful_payment

    if payment is None or message.from_user is None:
        return

    parsed = parse_invoice_payload(payment.invoice_payload)

    if parsed is None:
        await message.answer(
            "Pagamento ricevuto, ma ordine non riconoscibile. "
            "Contatta l'assistenza con la ricevuta Telegram."
        )
        return

    order_id, expected_user_id, payment_token = parsed
    order = await database.get_pending_digital_order(
        order_id,
        expected_user_id,
        payment_token,
    )

    if (
        order is None
        or message.from_user.id != expected_user_id
        or payment.currency != "XTR"
        or payment.total_amount != order["total_stars"]
    ):
        await message.answer(
            "Pagamento ricevuto, ma la verifica dell'ordine "
            "non è riuscita. Contatta l'assistenza."
        )
        return

    completed = await database.complete_digital_order(
        order_id=order_id,
        telegram_user_id=expected_user_id,
        payment_token=payment_token,
        payment_reference=payment.telegram_payment_charge_id,
        payment_method="telegram_stars",
    )

    if not completed:
        await message.answer(
            "Questo pagamento risulta già elaborato. "
            "Controlla I miei ordini."
        )
        return

    await send_digital_delivery(
        message,
        database,
        order_id,
        "Pagamento Telegram Stars completato",
    )
    await notify_admins_about_order(
        bot,
        settings,
        database,
        order_id,
    )


@router.message(Command("paysupport"))
async def command_payment_support(
    message: Message,
    settings: Settings,
) -> None:
    await message.answer(
        "💳 <b>Assistenza pagamenti</b>\n\n"
        f"Contatto: {escape(settings.support_contact)}\n\n"
        "Non inviare password, codici di accesso o dati "
        "completi della carta. Conserva la ricevuta Telegram."
    )


@router.callback_query(F.data == "orders:show")
async def callback_order_history(
    callback: CallbackQuery,
    database: Database,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    orders = await database.list_user_orders(callback.from_user.id)

    if not orders:
        await callback.message.edit_text(
            "🧾 Non hai ancora effettuato ordini.",
            reply_markup=back_to_main_keyboard(),
        )
        await callback.answer()
        return

    status_labels = {
        "pending": "In attesa",
        "paid": "Pagato",
        "cancelled": "Annullato",
    }
    lines = ["🧾 <b>I tuoi ultimi ordini</b>"]

    for order in orders:
        if order["order_type"] == "digital":
            total = f"{order['total_stars']} Stars"
            status = status_labels[order["status"]]
        else:
            euros, cents = divmod(order["total_cents"], 100)
            total = f"{euros},{cents:02d} {order['currency']}"
            physical_labels = {
                "new": "Ricevuto",
                "processing": "In lavorazione",
                "shipped": "Spedito",
                "completed": "Completato",
                "cancelled": "Annullato",
            }
            status = physical_labels.get(
                order["fulfillment_status"],
                status_labels[order["status"]],
            )

        lines.append(
            f"\nOrdine #{order['id']} — {status}\n"
            f"Totale: {total}"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=back_to_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "checkout:physical")
async def callback_physical_checkout(
    callback: CallbackQuery,
    database: Database,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    items = await database.list_cart_items(callback.from_user.id)

    if not any(item["product_type"] == "physical" for item in items):
        await callback.answer(
            "Il carrello non contiene prodotti fisici.",
            show_alert=True,
        )
        return

    await state.clear()
    await state.set_state(PhysicalCheckout.shipping_name)
    await callback.message.edit_text(
        "📦 <b>Checkout prodotti fisici</b>\n\n"
        "Per questa prova usa dati inventati.\n\n"
        "Scrivi il nome del destinatario, per esempio:\n"
        "<code>Mario Demo</code>",
        reply_markup=cancel_checkout_keyboard(),
    )
    await callback.answer()


@router.message(PhysicalCheckout.shipping_name, F.text)
async def receive_shipping_name(
    message: Message,
    state: FSMContext,
) -> None:
    value = message.text.strip()

    if not 2 <= len(value) <= 100:
        await message.answer("Inserisci un nome da 2 a 100 caratteri.")
        return

    await state.update_data(shipping_name=value)
    await state.set_state(PhysicalCheckout.shipping_address)
    await message.answer(
        "Scrivi un indirizzo dimostrativo, per esempio:\n"
        "<code>Via Demo 10</code>",
        reply_markup=cancel_checkout_keyboard(),
    )


@router.message(PhysicalCheckout.shipping_address, F.text)
async def receive_shipping_address(
    message: Message,
    state: FSMContext,
) -> None:
    value = message.text.strip()

    if not 5 <= len(value) <= 200:
        await message.answer(
            "Inserisci un indirizzo da 5 a 200 caratteri."
        )
        return

    await state.update_data(shipping_address=value)
    await state.set_state(PhysicalCheckout.shipping_city_postal)
    await message.answer(
        "Scrivi città e CAP dimostrativi, per esempio:\n"
        "<code>00100 Roma</code>",
        reply_markup=cancel_checkout_keyboard(),
    )


@router.message(PhysicalCheckout.shipping_city_postal, F.text)
async def receive_shipping_city(
    message: Message,
    state: FSMContext,
) -> None:
    value = message.text.strip()

    if not 3 <= len(value) <= 100:
        await message.answer(
            "Inserisci città e CAP da 3 a 100 caratteri."
        )
        return

    await state.update_data(shipping_city_postal=value)
    await state.set_state(PhysicalCheckout.shipping_phone)
    await message.answer(
        "Scrivi un numero dimostrativo, per esempio:\n"
        "<code>+39 000 0000000</code>",
        reply_markup=cancel_checkout_keyboard(),
    )


@router.message(PhysicalCheckout.shipping_phone, F.text)
async def receive_shipping_phone(
    message: Message,
    state: FSMContext,
) -> None:
    value = message.text.strip()

    if (
        not 6 <= len(value) <= 30
        or re.fullmatch(r"[+0-9 ()-]+", value) is None
    ):
        await message.answer(
            "Inserisci un numero valido usando cifre, spazi e +."
        )
        return

    await state.update_data(shipping_phone=value)
    await state.set_state(PhysicalCheckout.confirmation)
    data = await state.get_data()
    await message.answer(
        "📦 <b>Controlla i dati dimostrativi</b>\n\n"
        f"Destinatario: {escape(data['shipping_name'])}\n"
        f"Indirizzo: {escape(data['shipping_address'])}\n"
        f"Città/CAP: {escape(data['shipping_city_postal'])}\n"
        f"Telefono: {escape(data['shipping_phone'])}\n\n"
        "Metodo: pagamento alla consegna dimostrativo.\n"
        "Nessuna spedizione o pagamento reale sarà effettuato.",
        reply_markup=confirm_physical_order_keyboard(),
    )


@router.callback_query(
    PhysicalCheckout.confirmation,
    F.data == "checkout:physical:confirm",
)
async def confirm_physical_order(
    callback: CallbackQuery,
    bot: Bot,
    database: Database,
    settings: Settings,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()

    try:
        order = await database.create_physical_order(
            telegram_user_id=callback.from_user.id,
            shipping_name=data["shipping_name"],
            shipping_address=data["shipping_address"],
            shipping_city_postal=data["shipping_city_postal"],
            shipping_phone=data["shipping_phone"],
        )
    except (KeyError, OrderError) as error:
        await state.clear()
        await callback.answer(str(error), show_alert=True)
        return

    await state.clear()
    euros, cents = divmod(order["total_cents"], 100)
    await callback.message.edit_text(
        "✅ <b>Ordine fisico dimostrativo ricevuto</b>\n\n"
        f"Ordine #{order['id']}\n"
        f"Totale: {euros},{cents:02d} {order['currency']}\n"
        "Metodo: pagamento alla consegna dimostrativo.\n\n"
        "In produzione l'amministratore riceverà la notifica "
        "e potrà aggiornare lo stato della spedizione.",
        reply_markup=back_to_main_keyboard(),
    )
    await notify_admins_about_order(
        bot,
        settings,
        database,
        order["id"],
    )
    await callback.answer()


@router.callback_query(F.data == "checkout:cancel")
async def cancel_checkout(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    if callback.message is not None:
        await callback.message.edit_text(
            "Checkout annullato. Il carrello non è stato modificato.",
            reply_markup=back_to_main_keyboard(),
        )

    await callback.answer()
