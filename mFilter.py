import asyncio
import re
import logging
import httpx
import aiosqlite
import datetime
import os # --- AÑADIDO PARA RENDER --- (Solo para leer el puerto, es indispensable)
from telethon import TelegramClient, events
from telethon.tl.types import User
from fastapi import FastAPI # --- AÑADIDO PARA RENDER ---
import uvicorn # --- AÑADIDO PARA RENDER ---
from contextlib import asynccontextmanager # --- AÑADIDO PARA RENDER ---

# --- Configuración de Logging ---
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)

# --- Credenciales y Configuración (PROPORCIONADAS POR EL USUARIO) ---
API_ID = 20491337
API_HASH = '72f87102bdc7c1044b2fa298dee9dca5'
BOT_TOKEN = '7562671189:AAEJIWFW8LfESm09CYcR6GgPbhg5eZ5NbAk'
NOTIFY_CHAT_ID = 1048966581

# --- NUEVA CONFIGURACIÓN: GeNeSiS Lounge y Usuarios de Confianza ---
GENESIS_LOUNGE_ID = 2124901271
TRUSTED_USER_IDS = {
    1282048314: "GENESIS_CHAI",
    7207841877: "muktartt",
    5056344791: "Altrealite",
}

# --- Canales a Monitorear ---
MONITORED_CHANNELS = {
    2124901271: "GeNeSiS_Lounge",
    2331240414: "Capo's Cousins",
    2604509392: "Beijing don't lie",
    2382209373: "Patrol Pump",
    2048249888: "AI CALL | $SOL",
    2198683628: "Felix Alpha",
    2314485533: "KOL SignalX",
    2338895089: "Pals Gem",
    2495900078: "PUM FUN",
    2433457093: "Chino",
    2341018601: "Solana Dex Paid",
    2318939340: "Solana Xpert Wallet"
}

# --- Expresiones Regulares ---
CA_PATTERN = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

# --- Nombre de la Base de Datos (MODIFICADO PARA RENDER) ---
# Render proporciona un "Disco Persistente" que montaremos en /data
# Esto asegura que nuestra base de datos no se borre en cada reinicio.
DB_FILE = "/data/memecoins.db"

# --- NUEVA CONFIGURACIÓN: Umbral de Market Cap y Intervalo de Verificación ---
MARKET_CAP_THRESHOLD = 5000  # USD
CHECK_INTERVAL_HOURS = 24    # Frecuencia de verificación en horas

# Inicializa el cliente de Telethon (para escuchar)
client = TelegramClient('bot_session', API_ID, API_HASH)

# --- AÑADIDO PARA RENDER: Lifespan Manager de FastAPI ---
# Esta función gestionará el ciclo de vida del bot junto con el servidor web.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Código que se ejecuta al iniciar el servidor
    logging.info("Iniciando el ciclo de vida de la aplicación...")
    await init_db()
    # Inicia el cliente de Telegram en segundo plano
    # .start() es no bloqueante a diferencia de .run_until_disconnected()
    await client.start(bot_token=BOT_TOKEN)
    # Crea las tareas en segundo plano
    asyncio.create_task(market_cap_monitor())
    
    logging.info("Bot y tareas en segundo plano iniciados correctamente.")
    logging.info(f"Monitoreando {len(MONITORED_CHANNELS)} canales.")
    logging.info(f"El monitor de Market Cap se ejecutará cada {CHECK_INTERVAL_HOURS} horas.")
    
    yield # Aquí es cuando la aplicación está "viva" y atendiendo peticiones
    
    # Código que se ejecuta al apagar el servidor
    logging.info("Apagando la aplicación...")
    await client.disconnect()
    logging.info("Cliente de Telegram desconectado.")

# --- AÑADIDO PARA RENDER: Inicialización de FastAPI ---
app = FastAPI(lifespan=lifespan)

@app.get("/", include_in_schema=False)
async def health_check():
    """Endpoint para que UptimeRobot verifique que el bot está vivo."""
    return {"status": "ok", "message": "Bot is running"}

# --- TODAS TUS FUNCIONES (sin cambios) ---

async def init_db():
    """Inicializa la base de datos y crea las tablas si no existen."""
    # Asegurarse de que el directorio /data existe
    db_dir = os.path.dirname(DB_FILE)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logging.info(f"Directorio de base de datos '{db_dir}' creado.")

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
        CREATE TABLE IF NOT EXISTS memecoins (
            ca_address TEXT PRIMARY KEY,
            symbol TEXT,
            name TEXT,
            genesis_mention_by TEXT,
            first_seen TIMESTAMP
        )
        ''')
        await db.execute('''
        CREATE TABLE IF NOT EXISTS mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memecoin_ca TEXT,
            channel_id INTEGER,
            channel_name TEXT,
            mention_time TIMESTAMP,
            FOREIGN KEY (memecoin_ca) REFERENCES memecoins (ca_address) ON DELETE CASCADE
        )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_memecoin_ca ON mentions (memecoin_ca)')
        await db.commit()
    logging.info("Base de datos SQLite inicializada correctamente.")

async def add_memecoin_to_db(ca, symbol, name):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO memecoins (ca_address, symbol, name, first_seen) VALUES (?, ?, ?, ?)",
            (ca, symbol, name, datetime.datetime.utcnow())
        )
        await db.commit()

async def add_mention_to_db(ca, channel_id, channel_name):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO mentions (memecoin_ca, channel_id, channel_name, mention_time) VALUES (?, ?, ?, ?)",
            (ca, channel_id, channel_name, datetime.datetime.utcnow())
        )
        await db.commit()

async def get_memecoin_from_db(ca):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT * FROM memecoins WHERE ca_address = ?", (ca,)) as cursor:
            return await cursor.fetchone()

async def get_mentions_from_db(ca):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT * FROM mentions WHERE memecoin_ca = ?", (ca,)) as cursor:
            return await cursor.fetchall()

async def update_genesis_mention_in_db(ca, user_name):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE memecoins SET genesis_mention_by = ? WHERE ca_address = ?", (user_name, ca)
        )
        await db.commit()

async def get_all_memecoin_cas():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT ca_address, symbol, name FROM memecoins") as cursor:
            return await cursor.fetchall()

async def delete_memecoin_from_db(ca):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("DELETE FROM memecoins WHERE ca_address = ?", (ca,))
        await db.commit()
        return cursor.rowcount > 0
        
async def send_notification_via_bot(message_text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': NOTIFY_CHAT_ID,
        'text': message_text,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(url, json=payload, timeout=20)
            if response.status_code != 200:
                logging.error(f"Error al enviar notificación vía bot: Status {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Error inesperado al enviar notificación vía bot: {e}")

async def get_dexscreener_data(token_address):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('pairs'): return data['pairs'][0]
            else:
                logging.error(f"Error en DexScreener para {token_address}: Status {response.status_code}")
    except Exception as e:
        logging.error(f"Excepción en DexScreener para {token_address}: {e}")
    return None

def format_dexscreener_info(dexscreener_data, ca_address):
    if not dexscreener_data: return "ℹ️ No se pudieron obtener datos de DexScreener."
    price_usd = float(dexscreener_data.get('priceUsd', '0'))
    liquidity_usd = dexscreener_data.get('liquidity', {}).get('usd', 0)
    market_cap = dexscreener_data.get('fdv', 0)
    volume_24h = dexscreener_data.get('volume', {}).get('h24', 0)
    price_change_24h = dexscreener_data.get('priceChange', {}).get('h24', 0)
    message = f"📊 Datos de DexScreener:\n"
    message += f"Precio USD: ${price_usd:,.8f}\n"
    message += f"Market Cap (FDV): ${market_cap:,.2f}\n"
    message += f"Liquidez: ${liquidity_usd:,.2f}\n"
    message += f"Volumen (24h): ${volume_24h:,.2f}\n"
    message += f"Cambio Precio (24h): {price_change_24h:.2f}%\n\n"
    message += f"🔗 Enlaces:\n[DexScreener](https://dexscreener.com/solana/{ca_address})"
    message += f" | [GMGN](https://gmgn.ai/sol/token/{ca_address})"
    if info := dexscreener_data.get('info'):
        if websites := info.get('websites'): message += f" | [Website]({websites[0]['url']})"
        if socials := info.get('socials'):
            for social in socials:
                if p := social.get('platform'): message += f" | [{p.capitalize()}]({social.get('url')})"
    return message.strip()

# ... (resto de tus funciones format_, find_ca_, etc. sin cambios)
def format_genesis_notification(ca, sender, dexscreener_data, existing_mentions):
    sender_name = f"@{sender.username}" if sender.username else sender.first_name
    message = f"🚨 Alerta de CA en GeNeSiS Lounge 🚨\n\n"
    message += f"👤 Compartido por: {sender_name}\n"
    message += f"Contrato (CA): `{ca}`\n\n"
    message += "📜 Historial en otros canales:\n"
    if existing_mentions:
        unique_channels = {m[3] for m in existing_mentions} 
        message += f"❗️ Este CA ya ha sido mencionado {len(existing_mentions)} veces en {len(unique_channels)} canales.\n"
        message += f"Canales: {', '.join(unique_channels)}\n\n"
    else:
        message += "✅ ¡Este CA parece ser nuevo! No se encontraron menciones previas.\n\n"
    message += format_dexscreener_info(dexscreener_data, ca)
    return message

def format_standard_notification(ca, token_data, reason, total_mentions, channel_list, dexscreener_data, genesis_info=None):
    symbol = token_data[1] or f'Token({ca[:5]}..)'
    name = token_data[2] or 'N/A'
    message = f"🚨 Alerta de Memecoin: {symbol} ({name}) 🚨\n\n"
    message += f"Motivo: {reason}\n"
    message += f"Menciones Totales: {total_mentions} en {len(channel_list)} canales distintos.\n"
    message += f"Canales: {', '.join(channel_list)}\n"
    message += f"Contrato (CA): `{ca}`\n\n"
    if genesis_info:
        message += f"💡 Dato Adicional: Este CA fue compartido en GeNeSiS Lounge por {genesis_info}.\n\n"
    message += format_dexscreener_info(dexscreener_data, ca)
    return message.strip()

async def find_ca_in_message_chain(message):
    current_msg = message
    for _ in range(5):
        if not current_msg: break
        if current_msg.text and (ca_match := CA_PATTERN.search(current_msg.text)):
            return ca_match.group(0)
        if hasattr(current_msg, 'get_reply_message') and current_msg.is_reply:
            current_msg = await current_msg.get_reply_message()
        else:
            break
    return None

# --- EVENT HANDLERS DE TELETHON (sin cambios) ---
@client.on(events.NewMessage(chats=list(MONITORED_CHANNELS.keys())))
async def new_message_handler(event):
    if event.message.fwd_from: return
    
    message = event.message
    chat_id = event.chat_id
    normalized_chat_id = int(str(chat_id)[4:]) if str(chat_id).startswith('-100') else chat_id
    channel_name = MONITORED_CHANNELS.get(normalized_chat_id, f"ID:{normalized_chat_id}")

    ca = await find_ca_in_message_chain(message)
    if not ca: return
        
    logging.info(f"CA Detectado: {ca} (en '{channel_name}')")

    memecoin_data = await get_memecoin_from_db(ca)

    if normalized_chat_id == GENESIS_LOUNGE_ID:
        sender = await message.get_sender()
        if not isinstance(sender, User) or sender.id not in TRUSTED_USER_IDS:
            logging.info(f"CA en GeNeSiS ignorado (autor no confiable). ID: {getattr(sender, 'id', 'N/A')}")
            return
            
        sender_name = f"@{sender.username}" if sender.username else sender.first_name
        logging.info(f"¡ALERTA! CA de usuario de confianza ({sender_name}) en GeNeSiS Lounge.")
        
        await add_mention_to_db(ca, normalized_chat_id, channel_name)
        existing_mentions = await get_mentions_from_db(ca) 

        if not memecoin_data:
            dex_data = await get_dexscreener_data(ca)
            if dex_data and (base_token := dex_data.get('baseToken')):
                await add_memecoin_to_db(ca, base_token.get('symbol'), base_token.get('name'))
        
        await update_genesis_mention_in_db(ca, sender_name)
        
        dexscreener_data = await get_dexscreener_data(ca)
        notification = format_genesis_notification(ca, sender, dexscreener_data, existing_mentions)
        await send_notification_via_bot(notification)
        return

    await add_mention_to_db(ca, normalized_chat_id, channel_name)

    all_mentions_rows = await get_mentions_from_db(ca)
    total_mentions = len(all_mentions_rows)
    unique_channels_after_this = {m[3] for m in all_mentions_rows}

    if not memecoin_data:
        dex_data = await get_dexscreener_data(ca)
        if not dex_data or not (base_token := dex_data.get('baseToken')):
            logging.warning(f"No se encontraron datos en DexScreener para el nuevo CA: {ca}. Se ignora la notificación.")
            return
        
        await add_memecoin_to_db(ca, base_token.get('symbol'), base_token.get('name'))
        logging.info(f"Primera mención de {ca} ({base_token.get('symbol')}). Almacenado en DB.")

    if total_mentions >= 3:
        reason = f"Alcanzó la **{total_mentions}ª mención** (en {len(unique_channels_after_this)} canales distintos)."
        logging.info(f"¡ALERTA! Razón: {reason} para CA: {ca}")
            
        dexscreener_data = await get_dexscreener_data(ca)
        updated_memecoin_data = await get_memecoin_from_db(ca)        
            
        message_to_send = format_standard_notification(
            ca, updated_memecoin_data, reason, total_mentions,
            list(unique_channels_after_this), dexscreener_data,
            genesis_info=updated_memecoin_data[3]
        )
        await send_notification_via_bot(message_to_send)
    else:
        logging.info(f"CA {ca} mencionado {total_mentions} veces. Se requiere la 3ª mención para notificar.")

@client.on(events.NewMessage(pattern=r'/stats', from_users=NOTIFY_CHAT_ID))
async def stats_handler(event):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT() FROM memecoins") as cursor:
            total_coins = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT() FROM mentions") as cursor:
            total_mentions = (await cursor.fetchone())[0]
            
    message = f"📊 *Estadísticas del Bot*\n\n"
    message += f"🪙 *Memecoins únicos monitoreados:* `{total_coins}`\n"
    message += f"🗣️ *Menciones totales registradas:* `{total_mentions}`"
    
    await event.reply(message, parse_mode='Markdown')

@client.on(events.NewMessage(pattern=r'/eliminar (.+)', from_users=NOTIFY_CHAT_ID))
async def delete_handler(event):
    ca_to_delete = event.pattern_match.group(1).strip()
    if not CA_PATTERN.match(ca_to_delete):
        await event.reply("❌ El formato del Contrato (CA) no parece válido.")
        return

    deleted = await delete_memecoin_from_db(ca_to_delete)

    if deleted:
        message = f"✅ Se eliminó el CA `{ca_to_delete}` y todas sus menciones de la base de datos."
        logging.info(message)
        await event.reply(message, parse_mode='Markdown')
    else:
        message = f"🤷‍♂️ No se encontró el CA `{ca_to_delete}` en la base de datos."
        await event.reply(message, parse_mode='Markdown')

# --- TAREA EN SEGUNDO PLANO (sin cambios) ---
async def market_cap_monitor():
    while True:
        await asyncio.sleep(CHECK_INTERVAL_HOURS * 3600)
        logging.info(f"Iniciando verificación de market cap (cada {CHECK_INTERVAL_HOURS} horas)...")
        try:
            memecoins_to_check = await get_all_memecoin_cas()
            deleted_count = 0
            for ca_address, symbol, name in memecoins_to_check:
                dex_data = await get_dexscreener_data(ca_address)
                if dex_data:
                    market_cap = dex_data.get('fdv', 0)
                    if market_cap < MARKET_CAP_THRESHOLD:
                        deleted = await delete_memecoin_from_db(ca_address)
                        if deleted:
                            deleted_count += 1
                            logging.debug(f"📉 Memecoin eliminado: {symbol} ({name}) con CA `{ca_address}`. Market Cap (${market_cap:,.2f}) por debajo de ${MARKET_CAP_THRESHOLD:,.2f}.")
                else:
                    logging.warning(f"No se pudieron obtener datos de DexScreener para CA `{ca_address}` durante el monitoreo de market cap. Se mantendrá por ahora.")
            
            if deleted_count > 0:
                logging.info(f"Monitoreo de Market Cap completado: Se eliminaron {deleted_count} memecoins.")
            else:
                logging.info("Monitoreo de Market Cap completado: No se encontraron memecoins para eliminar.")
        except Exception as e:
            logging.error(f"Error en el monitor de market cap: {e}")

# --- BLOQUE PRINCIPAL MODIFICADO PARA RENDER ---
if __name__ == "__main__":
    # Render establece la variable de entorno PORT. Debemos usarla.
    # El uso de os.environ.get() aquí NO requiere un archivo .env,
    # es la forma estándar de comunicarse con la plataforma de hosting.
    port = int(os.environ.get("PORT", 8000))
    # Uvicorn ejecutará nuestra aplicación FastAPI.
    # El 'lifespan' manager se encargará de iniciar y detener el bot de Telethon.
    uvicorn.run(app, host="0.0.0.0", port=port)
