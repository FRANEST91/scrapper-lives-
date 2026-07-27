# Scrapper Lives - Bot de Verificación de Tarjetas

Script automático para verificar tarjetas de crédito contra la API de ParkingPay y publicar resultados en Telegram.

## 🚀 Variables de Entorno (Railway)

Coloca estas variables en el dashboard de Railway:

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `BOT_TOKEN` | **REQUERIDO** - Token de tu bot de Telegram (de @BotFather) | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
| `DESTINATION_CHAT` | **REQUERIDO** - ID del chat donde publicar resultados | `-1001234567890` |
| `BUTTON_URL` | URL del botón en los mensajes de Telegram (opcional) | `https://tudominio.com` |
| `CHARGE_OPTION` | Tipo de cargo a probar (1=1 MXN, 2=20 MXN, 3=50 MXN, 4=100 MXN) | `1` |
| `CARD_AMOUNT` | Cantidad de tarjetas a verificar por ciclo | `10` |
| `SLEEP_BETWEEN_CYCLES` | Segundos de espera entre ciclos | `300` |
| `BAS_BIN_FILE` | Ruta del archivo CSV de entrada (opcional) | `bas_bin.csv` |
| `CSV_BIN_FILE` | Ruta del archivo CSV de BINs (opcional) | `tarjetas.csv` |
| `DB_PATH` | Ruta de la base de datos SQLite (opcional) | `published.db` |

## ✅ Variables Obligatorias

Solo estas 2 son **obligatorias**:
1. **BOT_TOKEN** - Tu token de Telegram
2. **DESTINATION_CHAT** - Tu ID de chat

El resto tienen valores por defecto y son opcionales.

## 📚 Cómo obtener tus datos

### Bot Token
1. Abre Telegram y busca **@BotFather**
2. Usa el comando `/newbot`
3. Sigue las instrucciones y obtén tu token

### Chat ID (DESTINATION_CHAT)
1. Abre Telegram y busca **@userinfobot**
2. El bot te mostrará tu ID (empieza con `-100`)
3. O crea un grupo, agrega el bot y obtén el ID del grupo

## 🔧 Despliegue en Railway

1. Conecta tu repositorio a Railway
2. Ve a **Variables** en el panel
3. Agrega las variables requeridas (BOT_TOKEN y DESTINATION_CHAT)
4. Las demás son opcionales con valores por defecto
5. Deploy automático al hacer push

## 📊 Estructura del Proyecto

- **main.py** - Funciones principales de registro y verificación de tarjetas
- **worker.py** - Loop principal que ejecuta ciclos de verificación
- **publisher.py** - Maneja la publicación de resultados en Telegram
- **gen.py** - Funciones generales (BINs, etc.)
- **Procfile** - Configuración para Railway
- **requirements.txt** - Dependencias Python

---

**Desarrollado por**: @MrMxyzptlk04 y @Chack0071
