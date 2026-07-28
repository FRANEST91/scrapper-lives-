import os
import time
import random
import csv as csv_module
from dotenv import load_dotenv
from gen import cc_gen, cargar_bin_db, buscar_bin
from main import (
    cargar_proxies, registrar_cuenta, check_card,
    format_proxy, MONTOS, flush_lives
)
from publisher import insert_pending
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("worker")

load_dotenv()

CHARGE_OPTION = os.getenv("CHARGE_OPTION", "1")
CARD_AMOUNT = int(os.getenv("CARD_AMOUNT", "10"))
SLEEP_BETWEEN_CYCLES = int(os.getenv("SLEEP_BETWEEN_CYCLES", "300"))
BAS_BIN_FILE = os.getenv("BAS_BIN_FILE", "bas_bin.csv")

def leer_series(csv_path):
    if not os.path.exists(csv_path):
        logger.error("Archivo %s no encontrado.", csv_path)
        return []
    series = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv_module.DictReader(f)
        for row in reader:
            card = row.get("Card Data", "").strip()
            if card and "|" in card:
                series.append(card)
    logger.info("Leídas %d tarjetas plantilla desde %s", len(series), csv_path)
    return series

def extraer_prefijo(cc):
    prefijo = ""
    for c in cc:
        if c.isdigit():
            prefijo += c
        else:
            break
    return prefijo

def ejecutar_ciclo():
    if CHARGE_OPTION not in MONTOS:
        logger.error("CHARGE_OPTION inválido.")
        return

    series = leer_series(BAS_BIN_FILE)
    if not series:
        return

    plantilla = random.choice(series)
    logger.info("Plantilla seleccionada: %s", plantilla)

    parts = plantilla.split("|")
    if len(parts) < 3:
        logger.error("Plantilla con formato incorrecto: %s", plantilla)
        return

    cc_plantilla = parts[0]
    mes = parts[1].zfill(2)
    ano = parts[2]
    if len(ano) == 2:
        ano = "20" + ano

    bin_prefix = extraer_prefijo(cc_plantilla)
    logger.info("Prefijo extraído: %s (longitud %d)", bin_prefix, len(bin_prefix))
    logger.info("Generando %d tarjetas con prefijo %s, exp %s/%s", CARD_AMOUNT, bin_prefix, mes, ano)

    combos = cc_gen(bin_prefix, mes, ano, CARD_AMOUNT)
    logger.info("Se generaron %d tarjetas completas.", len(combos))

    monto, monto_nombre = MONTOS[CHARGE_OPTION]
    proxies_list = cargar_proxies()
    bin_db = cargar_bin_db()

    proxy_url = format_proxy(random.choice(proxies_list)) if proxies_list else None
    token = registrar_cuenta(proxy_url)
    if not token:
        logger.error("No se pudo generar la cuenta. Abortando ciclo.")
        return
    logger.info("Cuenta creada y token obtenido. Iniciando verificación...")

    lives = 0
    for i, combo in enumerate(combos):
        if not combo or "|" not in combo:
            continue
        cparts = combo.strip().split("|")
        if len(cparts) < 4:
            continue
        cc, mm, yy, cvv = cparts[0], cparts[1], cparts[2], cparts[3]
        bin_info = buscar_bin(cc, bin_db)
        logger.info("Verificando %d/%d: %s...%s", i+1, len(combos), cc[:6], cc[-4:])

        tipo, display, detalle = check_card(cc, mm, yy, cvv, monto, monto_nombre, token, proxy_url, bin_info)

        if tipo == "token_expired":
            logger.warning("Token expirado. Ciclo detenido.")
            break
        if tipo == "error" and ("API APAGADA" in detalle or "API NO DISPONIBLE" in detalle):
            logger.warning("API no disponible: %s. Ciclo detenido.", detalle)
            break

        if tipo == "live":
            lives += 1
            insert_pending(combo)
            logger.info("LIVE: %s", display)
        elif tipo == "dead":
            logger.info("DEAD: %s", display)
        else:
            logger.error("ERROR: %s - %s", display, detalle)

        if i < len(combos) - 1:
            time.sleep(random.uniform(0.8, 1.5))

    logger.info("Ciclo completado. Lives encontradas: %d", lives)
    if lives > 0:
        flush_lives(monto_nombre)

def main():
    logger.info("Iniciando worker automático...")
    while True:
        try:
            ejecutar_ciclo()
        except Exception as e:
            logger.exception("Error en ciclo: %s", e)
        logger.info("Esperando %d segundos...", SLEEP_BETWEEN_CYCLES)
        time.sleep(SLEEP_BETWEEN_CYCLES)

if __name__ == "__main__":
    main()
