from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from time import time
from urllib.parse import parse_qsl, urlencode, urlparse

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_admin_ids(raw_value: str) -> frozenset[int]:
    result: set[int] = set()

    for item in raw_value.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            result.add(int(item))
        except ValueError as error:
            raise RuntimeError(
                "ADMIN_IDS deve contenere soltanto ID Telegram "
                "numerici separati da virgole."
            ) from error

    return frozenset(result)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    database_path: Path
    shop_name: str
    payment_mode: str
    support_contact: str
    mini_app_url: str
    api_host: str
    api_port: int


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    bot_token = os.getenv("BOT_TOKEN", "").strip()

    if not bot_token:
        raise RuntimeError(
            "BOT_TOKEN non configurato nel file .env."
        )

    shop_name = os.getenv(
        "SHOP_NAME",
        "Demo Digital & Physical Shop",
    ).strip()

    if not 1 <= len(shop_name) <= 100:
        raise RuntimeError(
            "SHOP_NAME deve contenere da 1 a 100 caratteri."
        )

    raw_database_path = os.getenv(
        "DATABASE_PATH",
        "data/shop.db",
    ).strip()

    database_path = Path(raw_database_path)

    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path

    database_path.parent.mkdir(parents=True, exist_ok=True)

    payment_mode = os.getenv("PAYMENT_MODE", "demo").strip().lower()

    if payment_mode not in {"demo", "stars"}:
        raise RuntimeError(
            "PAYMENT_MODE deve essere 'demo' oppure 'stars'."
        )

    support_contact = os.getenv(
        "SUPPORT_CONTACT",
        "Assistenza demo non attiva",
    ).strip()

    if not 1 <= len(support_contact) <= 200:
        raise RuntimeError(
            "SUPPORT_CONTACT deve contenere da 1 a 200 caratteri."
        )

    mini_app_url = os.getenv("MINI_APP_URL", "").strip()
    parsed_mini_app_url = urlparse(mini_app_url)

    if (
        parsed_mini_app_url.scheme != "https"
        or not parsed_mini_app_url.netloc
    ):
        raise RuntimeError(
            "MINI_APP_URL deve contenere un indirizzo HTTPS valido."
        )

    mini_app_url = parsed_mini_app_url._replace(
        query=urlencode(
            [
                *parse_qsl(parsed_mini_app_url.query),
                ("app_version", str(int(time()))),
            ]
        )
    ).geturl()

    api_host = os.getenv("API_HOST", "0.0.0.0").strip()

    if not api_host:
        raise RuntimeError("API_HOST non può essere vuoto.")

    raw_api_port = os.getenv("PORT", "8000").strip()

    try:
        api_port = int(raw_api_port)
    except ValueError as error:
        raise RuntimeError("PORT deve contenere un numero intero.") from error

    if not 1 <= api_port <= 65535:
        raise RuntimeError("PORT deve essere compresa tra 1 e 65535.")

    return Settings(
        bot_token=bot_token,
        admin_ids=parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        database_path=database_path,
        shop_name=shop_name,
        payment_mode=payment_mode,
        support_contact=support_contact,
        mini_app_url=mini_app_url,
        api_host=api_host,
        api_port=api_port,
    )
