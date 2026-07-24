import asyncio
import csv
import os
from telegram import Bot
from telegram.error import TelegramError

# ========== CONFIGURACIÓN (cambia estos valores) ==========
BOT_TOKEN = "AQUÍ_VA_EL_TOKEN_DE_TU_BOT"         # Token del bot de @BotFather
CHANNEL_ID = "@nombre_de_tu_canal"               # ID o @usuario del canal (ej. -1001234567890)
CSV_FILE = "posts.csv"                           # Nombre del archivo CSV en la raíz
INTERVALO_SEGUNDOS = 60                          # Tiempo entre publicaciones (ej. 30, 60, 120...)
COLUMNA_MENSAJE = "mensaje"                      # Nombre de la columna que contiene el texto a publicar
# =========================================================

async def publicar_en_bucle():
    bot = Bot(token=BOT_TOKEN)

    # Verificar que el archivo CSV existe
    if not os.path.exists(CSV_FILE):
        print(f"❌ No se encontró el archivo {CSV_FILE}")
        return

    # Leer todas las filas del CSV
    with open(CSV_FILE, newline='', encoding='utf-8') as f:
        lector = csv.DictReader(f)
        filas = list(lector)
    
    if not filas:
        print("⚠️ El archivo CSV está vacío.")
        return

    if COLUMNA_MENSAJE not in filas[0]:
        print(f"❌ La columna '{COLUMNA_MENSAJE}' no existe en el CSV.")
        print(f"   Columnas disponibles: {list(filas[0].keys())}")
        return

    print(f"📤 Iniciando publicaciones cada {INTERVALO_SEGUNDOS} segundos.")
    print(f"   Archivo: {CSV_FILE} | Canal: {CHANNEL_ID}")
    print(f"   Total de mensajes en la lista: {len(filas)}")

    indice = 0
    while True:
        fila = filas[indice]
        texto = fila[COLUMNA_MENSAJE].strip()

        if texto:  # Solo publica si el mensaje no está vacío
            try:
                await bot.send_message(chat_id=CHANNEL_ID, text=texto)
                print(f"✅ Publicado [{indice+1}/{len(filas)}]: {texto[:50]}...")
            except TelegramError as e:
                print(f"❌ Error al publicar: {e}")
        else:
            print(f"⏭️  Fila {indice+1} vacía, se omite.")

        indice = (indice + 1) % len(filas)   # Recicla la lista automáticamente
        await asyncio.sleep(INTERVALO_SEGUNDOS)

if __name__ == "__main__":
    asyncio.run(publicar_en_bucle())
