import asyncio
import os
import re
import csv
import sqlite3
import logging
import html
from typing import Dict, Optional, List
from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError, RetryAfter, TimedOut

# ----------------------------------------------------------------------
# Cargar variables de entorno
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DESTINATION_CHAT = os.getenv("DESTINATION_CHAT")          # ID o @username
SEND_INTERVAL_SECONDS = int(os.getenv("SEND_INTERVAL_SECONDS", "80"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))  # segundos entre ciclos
BUTTON_URL = os.getenv("BUTTON_URL", "")                   # URL del botón inline (opcional)

# ----------------------------------------------------------------------
# Archivos CSV (en el mismo directorio que main.py)
#   bas_bin.csv        -> contiene la columna "Card Data" con las tarjetas
#   tarjetas.csv       -> contiene la base de datos de BINs (bin, brand, tipo, etc.)
CSV_CARDS_FILE = os.getenv("CSV_CARDS_FILE", "bas_bin.csv")
CSV_BIN_FILE   = os.getenv("CSV_BIN_FILE",   "tarjetas.csv")
DB_PATH        = os.getenv("DB_PATH", "published.db")

if not BOT_TOKEN or not DESTINATION_CHAT:
    raise ValueError("BOT_TOKEN y DESTINATION_CHAT son obligatorios en el archivo .env")

# ----------------------------------------------------------------------
# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("cc_publisher")

# ----------------------------------------------------------------------
# Base de datos de control (evita republicar la misma tarjeta)
def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS published (
            card_data TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    return conn

def is_published(conn: sqlite3.Connection, card_data: str) -> bool:
    row = conn.execute("SELECT 1 FROM published WHERE card_data = ?", (card_data,)).fetchone()
    return row is not None

def mark_published(conn: sqlite3.Connection, card_data: str) -> None:
    conn.execute("INSERT OR IGNORE INTO published (card_data) VALUES (?)", (card_data,))
    conn.commit()

# ----------------------------------------------------------------------
# Lógica de BIN y formateo

COUNTRY_CODE_BY_NAME = {
    "ARGENTINA": "AR", "AUSTRALIA": "AU", "AUSTRIA": "AT", "BANGLADESH": "BD", "BELGIUM": "BE",
    "BRAZIL": "BR", "BULGARIA": "BG", "CANADA": "CA", "CHILE": "CL", "CHINA": "CN",
    "COLOMBIA": "CO", "COSTA RICA": "CR", "CROATIA": "HR", "DENMARK": "DK", "DOMINICAN REPUBLIC": "DO",
    "ECUADOR": "EC", "EGYPT": "EG", "FINLAND": "FI", "FRANCE": "FR", "GERMANY": "DE", "GREECE": "GR",
    "GUATEMALA": "GT", "HONG KONG": "HK", "INDIA": "IN", "INDONESIA": "ID", "IRELAND": "IE",
    "ITALY": "IT", "JAPAN": "JP", "KOREA, REPUBLIC OF": "KR", "LEBANON": "LB", "MALAYSIA": "MY",
    "MEXICO": "MX", "NETHERLANDS": "NL", "NIGERIA": "NG", "NORWAY": "NO", "PAKISTAN": "PK",
    "PANAMA": "PA", "PERU": "PE", "PHILIPPINES": "PH", "POLAND": "PL", "PORTUGAL": "PT",
    "ROMANIA": "RO", "RUSSIAN FEDERATION": "RU", "SAUDI ARABIA": "SA", "SERBIA": "RS",
    "SINGAPORE": "SG", "SOUTH AFRICA": "ZA", "SPAIN": "ES", "SWEDEN": "SE", "SWITZERLAND": "CH",
    "TAIWAN, PROVINCE OF CHINA": "TW", "THAILAND": "TH", "TURKEY": "TR", "UKRAINE": "UA",
    "UNITED ARAB EMIRATES": "AE", "UNITED KINGDOM": "GB", "UNITED STATES": "US",
    "VENEZUELA, BOLIVARIAN REPUBLIC OF": "VE", "VIET NAM": "VN",
}

def country_flag(country_name: str) -> str:
    country_code = COUNTRY_CODE_BY_NAME.get((country_name or "").strip().upper())
    if not country_code:
        return ""
    return "".join(chr(ord(char) + 127397) for char in country_code)

def load_bin_database(csv_path: str) -> Dict[str, Dict[str, str]]:
    bin_db: Dict[str, Dict[str, str]] = {}
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bin_code = row.get("bin", "").strip()
                if bin_code:
                    bin_db[bin_code] = {
                        "brand": row.get("brand", "Desconocido").strip(),
                        "tipo": row.get("tipo", "Desconocido").strip(),
                        "nivel": row.get("nivel", "").strip(),
                        "banco": row.get("Banco", "Desconocido").strip(),
                        "pais": row.get("país", "Desconocido").strip(),
                        "bin": bin_code,
                    }
        logger.info(f"Base de datos BIN cargada: {len(bin_db)} entradas desde {csv_path}")
    except FileNotFoundError:
        logger.warning(f"Archivo CSV de BINs no encontrado: '{csv_path}'")
    except Exception:
        logger.exception(f"Error cargando BINs desde {csv_path}")
    return bin_db

def mask_card_number(card_number: str) -> str:
    if 'x' in card_number.lower():
        return card_number
    if len(card_number) <= 4:
        return "X" * len(card_number)
    show_digits = min(12, len(card_number) - 4)
    return card_number[:show_digits] + "X" * (len(card_number) - show_digits)

def get_bin_info(card_number: str, bin_database: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    clean_number = re.sub(r'[^0-9]', '', card_number.split('|')[0])
    for length in (6, 5, 4):
        if len(clean_number) >= length:
            bin_code = clean_number[:length]
            if bin_code in bin_database:
                return bin_database[bin_code]
    return None

def format_card_message(card_data: str, bin_database: Dict[str, Dict[str, str]]) -> Optional[str]:
    parts = card_data.split("|")
    if len(parts) == 4:
        card_num, month, year, cvv = parts
    elif len(parts) == 3:
        card_num, month, year = parts
        cvv = "xxx"
    else:
        return None

    if len(card_num) < 12 or len(month) != 2:
        return None

    bin_info = get_bin_info(card_num, bin_database)
    censored_card_num = mask_card_number(card_num)
    display_year = f"20{year}" if len(year) == 2 else year
    cvv_display = cvv[:3] if cvv != "xxx" else "No disponible"
    censored = f"{censored_card_num}|{month}|{display_year}|{cvv_display}"

    tipo = brand = nivel = banco = pais = bin_code_found = "Desconocido"
    if bin_info:
        tipo = bin_info.get("tipo", "Desconocido")
        brand = bin_info.get("brand", "Desconocido")
        nivel = bin_info.get("nivel", "")
        banco = bin_info.get("banco", "Desconocido")
        pais = bin_info.get("pais", "Desconocido")
        bin_code_found = bin_info.get("bin", "Desconocido")

    country_with_flag = f"{pais} {country_flag(pais)}".strip()

    message = (
        f"<b>OLIMPO SCRAPPER</b>\n\n"
        f"<b>#<code>{html.escape(bin_code_found)}</code></b>\n"
        f"<b>━━━━━━━━</b>\n"
        f"<b>Serie= <code>{html.escape(censored)}</code></b>\n"
        f"<b>Bin= <code>{html.escape(bin_code_found)}</code></b>\n"
        f"<b>Banco= {html.escape(banco)}</b>\n"
        f"<b>Marca= {html.escape(brand)}</b>\n"
        f"<b>Tipo= {html.escape(tipo)}</b>\n"
        f"<b>Nivel= {html.escape(nivel)}</b>\n"
        f"<b>País= {html.escape(country_with_flag)}</b>\n"
        f"<b>━━━━━━━━</b>\n"
        f"<b>DESARROLLADO POR</b>\n"
        f"<b><code>@MrMxyzptlk04</code></b>\n"
        f"<b><code>@Chack0071</code></b>\n"
        f"<b>━━━━━━━━</b>\n"
    )
    return message

# ----------------------------------------------------------------------
# Lectura del CSV de tarjetas (columna "Card Data")
def read_card_data_list(csv_path: str) -> List[str]:
    cards = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            if "Card Data" not in fieldnames:
                logger.error(
                    f"El archivo {csv_path} no contiene la columna 'Card Data'. "
                    f"Columnas detectadas: {fieldnames}"
                )
                raise ValueError(f"No se encontró la columna 'Card Data' en {csv_path}")
            for row in reader:
                card = row["Card Data"].strip()
                if card:
                    cards.append(card)
        logger.info(f"Leídas {len(cards)} tarjetas desde {csv_path}")
    except FileNotFoundError:
        logger.error(f"Archivo CSV de tarjetas no encontrado: {csv_path}")
    except Exception:
        logger.exception(f"Error leyendo CSV de tarjetas: {csv_path}")
    return cards

# ----------------------------------------------------------------------
# Envío de un solo mensaje (con reintento simple y botón inline opcional)
async def send_card(bot: Bot, chat_id: str, message: str) -> bool:
    # Construir botón inline si BUTTON_URL está configurado
    reply_markup = None
    if BUTTON_URL:
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⭐ OLIMPO", url=BUTTON_URL)]]
        )

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return True
    except RetryAfter as e:
        logger.warning(f"Rate limit, esperando {e.retry_after}s")
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return True
        except TelegramError as e2:
            logger.error(f"Fallo tras retry: {e2}")
            return False
    except TimedOut:
        logger.error("Timeout enviando mensaje")
        return False
    except TelegramError as e:
        logger.error(f"Error de Telegram: {e}")
        return False

# ----------------------------------------------------------------------
# Ciclo de publicación: lee CSV de tarjetas, envía las no publicadas
async def publish_cycle(bot: Bot, bin_db: Dict, conn: sqlite3.Connection):
    cards = read_card_data_list(CSV_CARDS_FILE)
    if not cards:
        logger.info("Sin tarjetas en el CSV.")
        return

    new_count = 0
    total = len(cards)
    for idx, card_data in enumerate(cards, 1):
        if is_published(conn, card_data):
            continue

        msg = format_card_message(card_data, bin_db)
        if not msg:
            logger.warning(f"Formato inválido para: {card_data}")
            continue

        success = await send_card(bot, DESTINATION_CHAT, msg)
        if success:
            mark_published(conn, card_data)
            new_count += 1
            logger.info(f"Publicada ({idx}/{total}): {card_data}")
        else:
            logger.error(f"Fallo al publicar ({idx}/{total}): {card_data}")

        # Esperar entre mensajes, excepto después del último
        if idx < total:
            await asyncio.sleep(SEND_INTERVAL_SECONDS)

    if new_count:
        logger.info(f"Ciclo completado: {new_count} nuevas tarjetas publicadas.")
    else:
        logger.info("Ciclo completado: sin tarjetas nuevas.")

# ----------------------------------------------------------------------
# Bucle principal
async def main():
    logger.info("Iniciando publicador de tarjetas...")
    logger.info(f"Archivo de tarjetas (columna 'Card Data'): {CSV_CARDS_FILE}")
    logger.info(f"Base de datos BIN: {CSV_BIN_FILE}")
    if BUTTON_URL:
        logger.info(f"Botón inline configurado con URL: {BUTTON_URL}")

    conn = init_db(DB_PATH)
    bin_db = load_bin_database(CSV_BIN_FILE)
    bot = Bot(token=BOT_TOKEN)

    try:
        while True:
            try:
                await publish_cycle(bot, bin_db, conn)
            except Exception as e:
                logger.exception(f"Error en ciclo de publicación: {e}")

            logger.info(f"Esperando {CHECK_INTERVAL} segundos hasta el próximo ciclo...")
            await asyncio.sleep(CHECK_INTERVAL)
    except asyncio.CancelledError:
        logger.info("Deteniendo publicador...")
    finally:
        conn.close()
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
