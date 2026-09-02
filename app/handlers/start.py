from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.keyboards.menus import (
    back_to_main_keyboard,
    main_menu_keyboard,
)


router = Router(name="start")


def welcome_text(settings: Settings) -> str:
    return (
        f"👋 <b>Benvenuto in {escape(settings.shop_name)}</b>\n\n"
        "Qui puoi acquistare prodotti digitali e fisici.\n\n"
        "Il catalogo è dimostrativo: nessun pagamento reale "
        "verrà richiesto in questa fase."
    )


@router.message(CommandStart())
async def command_start(
    message: Message,
    settings: Settings,
) -> None:
    await message.answer(
        welcome_text(settings),
        reply_markup=main_menu_keyboard(settings.mini_app_url),
    )


@router.message(Command("id"))
async def command_id(message: Message) -> None:
    if message.from_user is None:
        return

    await message.answer(
        "🆔 Il tuo Telegram ID è: "
        f"<code>{message.from_user.id}</code>"
    )


@router.callback_query(F.data == "menu:main")
async def callback_main(
    callback: CallbackQuery,
    settings: Settings,
) -> None:
    if callback.message is not None:
        await callback.message.edit_text(
            welcome_text(settings),
            reply_markup=main_menu_keyboard(settings.mini_app_url),
        )

    await callback.answer()


@router.callback_query(F.data == "menu:info")
async def callback_info(
    callback: CallbackQuery,
    settings: Settings,
) -> None:
    if callback.message is not None:
        await callback.message.edit_text(
            f"ℹ️ <b>{escape(settings.shop_name)}</b>\n\n"
            "Demo riutilizzabile di negozio Telegram.\n\n"
            "📥 I prodotti digitali useranno Telegram Stars e "
            "saranno consegnati automaticamente.\n"
            "📦 I prodotti fisici useranno indirizzo, spedizione "
            "e il metodo di pagamento del cliente.",
            reply_markup=back_to_main_keyboard(),
        )

    await callback.answer()
