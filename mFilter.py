import asyncio

import re

import logging

import httpx

import aiosqlite

import datetime

from telethon import TelegramClient, events

from telethon.tl.types import User



# --- Configuración de Logging (Recomendado) ---

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',

                    level=logging.INFO)



# --- Credenciales y Configuración (PROPORCIONADAS POR EL USUARIO) ---

API_ID = 20491337

API_HASH = '72f87102bdc7c1044b2fa298dee9dca5'

BOT_TOKEN = '7562671189:AAEJIWFW8LfESm09CYcR6GgPbhg5eZ5NbAk'

# ID del chat de Telegram donde el bot enviará las notificaciones

# 🔴 ESTE ID TAMBIÉN SE USARÁ PARA AUTORIZAR LOS COMANDOS

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



# --- Nombre de la Base de Datos ---

DB_FILE = "memecoins.db"



# --- NUEVA CONFIGURACIÓN: Umbral de Market Cap y Intervalo de Verificación ---

MARKET_CAP_THRESHOLD = 5000  # USD

CHECK_INTERVAL_HOURS = 24    # Frecuencia de verificación en horas



# Inicializa el cliente de Telethon (para escuchar)

client = TelegramClient('bot_session', API_ID, API_HASH)





# --- NUEVAS FUNCIONES DE BASE DE DATOS (SQLite) ---



async def init_db():

    """Inicializa la base de datos y crea las tablas si no existen."""

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

        # --- LÍNEA AÑADIDA PARA OPTIMIZACIÓN ---

        await db.execute('CREATE INDEX IF NOT EXISTS idx_memecoin_ca ON mentions (memecoin_ca)')

        # ----------------------------------------

        await db.commit()

        logging.info("Base de datos SQLite inicializada correctamente.")



async def add_memecoin_to_db(ca, symbol, name):

    """Añade un nuevo memecoin a la tabla principal."""

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute(

            "INSERT OR IGNORE INTO memecoins (ca_address, symbol, name, first_seen) VALUES (?, ?, ?, ?)",

            (ca, symbol, name, datetime.datetime.utcnow())

        )

        await db.commit()



async def add_mention_to_db(ca, channel_id, channel_name):

    """Añade una nueva mención para un memecoin."""

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute(

            "INSERT INTO mentions (memecoin_ca, channel_id, channel_name, mention_time) VALUES (?, ?, ?, ?)",

            (ca, channel_id, channel_name, datetime.datetime.utcnow())

        )

        await db.commit()



async def get_memecoin_from_db(ca):

    """Obtiene un memecoin de la base de datos."""

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute("SELECT * FROM memecoins WHERE ca_address = ?", (ca,)) as cursor:

            return await cursor.fetchone()



async def get_mentions_from_db(ca):

    """Obtiene todas las menciones de un memecoin."""

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute("SELECT * FROM mentions WHERE memecoin_ca = ?", (ca,)) as cursor:

            return await cursor.fetchall()



async def update_genesis_mention_in_db(ca, user_name):

    """Actualiza quién mencionó el CA en Genesis Lounge."""

    async with aiosqlite.connect(DB_FILE) as db:

        await db.execute(

            "UPDATE memecoins SET genesis_mention_by = ? WHERE ca_address = ?", (user_name, ca)

        )

        await db.commit()



async def get_all_memecoin_cas():

    """Obtiene todas las direcciones CA de los memecoins en la base de datos."""

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute("SELECT ca_address, symbol, name FROM memecoins") as cursor:

            return await cursor.fetchall()



async def delete_memecoin_from_db(ca):

    """Elimina un memecoin de la base de datos."""

    async with aiosqlite.connect(DB_FILE) as db:

        cursor = await db.execute("DELETE FROM memecoins WHERE ca_address = ?", (ca,))

        await db.commit()

    return cursor.rowcount > 0



# --- FIN DE FUNCIONES DE BASE DE DATOS ---





async def send_notification_via_bot(message_text):

    """Envia una notificación a través de la API de bots de Telegram usando httpx."""

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



def format_dexscreener_info(dexscreener_data, ca_address): # Added ca_address as a parameter

    if not dexscreener_data: return "ℹ️ _No se pudieron obtener datos de DexScreener._"

    price_usd = float(dexscreener_data.get('priceUsd', '0'))

    liquidity_usd = dexscreener_data.get('liquidity', {}).get('usd', 0)

    market_cap = dexscreener_data.get('fdv', 0)

    volume_24h = dexscreener_data.get('volume', {}).get('h24', 0)

    price_change_24h = dexscreener_data.get('priceChange', {}).get('h24', 0)

    message = f"*📊 Datos de DexScreener:*\n"

    message += f"**Precio USD:** `${price_usd:,.8f}`\n"

    message += f"**Market Cap (FDV):** `${market_cap:,.2f}`\n"

    message += f"**Liquidez:** `${liquidity_usd:,.2f}`\n"

    message += f"**Volumen (24h):** `${volume_24h:,.2f}`\n"

    message += f"**Cambio Precio (24h):** `{price_change_24h:.2f}%`\n\n"

    message += f"*🔗 Enlaces:*\n[DexScreener]({dexscreener_data.get('url')})"

    

    # --- ADDED: GMGN.ai Link ---

    message += f" | [GMGN](https://gmgn.ai/sol/token/{ca_address})"

    # ---------------------------



    if info := dexscreener_data.get('info'):

        if websites := info.get('websites'): message += f" | [Website]({websites[0]['url']})"

        if socials := info.get('socials'):

            for social in socials:

                if p := social.get('platform'): message += f" | [{p.capitalize()}]({social.get('url')})"

    return message.strip()



def format_genesis_notification(ca, sender, dexscreener_data, existing_mentions):

    sender_name = f"@{sender.username}" if sender.username else sender.first_name

    message = f"🚨 *Alerta de CA en GeNeSiS Lounge* 🚨\n\n"

    message += f"👤 *Compartido por:* **{sender_name}**\n"

    message += f"**Contrato (CA):** `{ca}`\n\n"

    message += "*📜 Historial en otros canales:*\n"

    if existing_mentions:

        unique_channels = {m[3] for m in existing_mentions} # m[3] es channel_name

        message += f"❗️ Este CA *ya ha sido mencionado* {len(existing_mentions)} veces en {len(unique_channels)} canales.\n"

        message += f"**Canales:** `{'`, `'.join(unique_channels)}`\n\n"

    else:

        message += "✅ ¡Este CA parece ser *nuevo*! No se encontraron menciones previas.\n\n"

    message += format_dexscreener_info(dexscreener_data, ca) # Pass ca_address here

    return message



def format_standard_notification(ca, token_data, reason, total_mentions, channel_list, dexscreener_data, genesis_info=None):

    symbol = token_data[1] or f'Token({ca[:5]}..)' # token_data[1] es symbol

    name = token_data[2] or 'N/A' # token_data[2] es name

    message = f"🚨 *Alerta de Memecoin: {symbol} ({name})* 🚨\n\n"

    message += f"**Motivo:** {reason}\n"

    message += f"**Menciones Totales:** {total_mentions} en {len(channel_list)} canales distintos.\n"

    message += f"**Canales:** `{'`, `'.join(channel_list)}`\n"

    message += f"**Contrato (CA):** `{ca}`\n\n"

    if genesis_info:

        message += f"💡 *Dato Adicional:* Este CA fue compartido en GeNeSiS Lounge por **{genesis_info}**.\n\n"

    message += format_dexscreener_info(dexscreener_data, ca) # Pass ca_address here

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

    

    # --- LÓGICA PARA GeNeSiS_Lounge ---

    if normalized_chat_id == GENESIS_LOUNGE_ID:

        sender = await message.get_sender()

        if not isinstance(sender, User) or sender.id not in TRUSTED_USER_IDS:

            logging.info(f"CA en GeNeSiS ignorado (autor no confiable). ID: {getattr(sender, 'id', 'N/A')}")

            return

            

        sender_name = f"@{sender.username}" if sender.username else sender.first_name

        logging.info(f"¡ALERTA! CA de usuario de confianza ({sender_name}) en GeNeSiS Lounge.")

        

        # Add the mention to the DB first for GeNeSiS, so it's included in existing_mentions

        await add_mention_to_db(ca, normalized_chat_id, channel_name)

        existing_mentions = await get_mentions_from_db(ca) # Get all mentions including the current one



        if not memecoin_data:

            dex_data = await get_dexscreener_data(ca)

            if dex_data and (base_token := dex_data.get('baseToken')):

                await add_memecoin_to_db(ca, base_token.get('symbol'), base_token.get('name'))

        

        await update_genesis_mention_in_db(ca, sender_name)

        

        dexscreener_data = await get_dexscreener_data(ca)

        notification = format_genesis_notification(ca, sender, dexscreener_data, existing_mentions)

        await send_notification_via_bot(notification)

        return



    # --- LÓGICA PARA CANALES DE MONITOREO ESTÁNDAR ---

    # Always add the mention first for standard channels

    await add_mention_to_db(ca, normalized_chat_id, channel_name)

    

    # Reload all mentions for this CA after adding the current one

    all_mentions_rows = await get_mentions_from_db(ca)

    total_mentions = len(all_mentions_rows)

    unique_channels_after_this = {m[3] for m in all_mentions_rows} # m[3] is channel_name



    if not memecoin_data:

        dex_data = await get_dexscreener_data(ca)

        if not dex_data or not (base_token := dex_data.get('baseToken')):

            logging.warning(f"No se encontraron datos en DexScreener para el nuevo CA: {ca}. Se ignora la notificación.")

            # Still record the mention, but don't notify if no data for the first time

            return

        

        await add_memecoin_to_db(ca, base_token.get('symbol'), base_token.get('name'))

        logging.info(f"Primera mención de {ca} ({base_token.get('symbol')}). Almacenado en DB.")

        # No notification on the first mention from standard channels by default, unless it's the 3rd overall.



    # Check if it's the 3rd (or more) mention

    if total_mentions >= 3:

        reason = f"Alcanzó la **{total_mentions}ª mención** (en {len(unique_channels_after_this)} canales distintos)."

        logging.info(f"¡ALERTA! Razón: {reason} para CA: {ca}")

            

        dexscreener_data = await get_dexscreener_data(ca)

        # Reload memecoin_data in case it was just added above

        updated_memecoin_data = await get_memecoin_from_db(ca)        

            

        message_to_send = format_standard_notification(

            ca, updated_memecoin_data, reason, total_mentions,

            list(unique_channels_after_this), dexscreener_data,

            genesis_info=updated_memecoin_data[3] # Fila 3 es genesis_mention_by

        )

        await send_notification_via_bot(message_to_send)

    else:

        logging.info(f"CA {ca} mencionado {total_mentions} veces. Se requiere la 3ª mención para notificar.")





# --- NUEVOS MANEJADORES DE COMANDOS ---



@client.on(events.NewMessage(pattern=r'/stats', from_users=NOTIFY_CHAT_ID))

async def stats_handler(event):

    """Muestra estadísticas de la base de datos."""

    async with aiosqlite.connect(DB_FILE) as db:

        async with db.execute("SELECT COUNT(*) FROM memecoins") as cursor:

            total_coins = (await cursor.fetchone())[0]

        async with db.execute("SELECT COUNT(*) FROM mentions") as cursor:

            total_mentions = (await cursor.fetchone())[0]



    message = "📊 *Estadísticas del Bot*\n\n"

    message += f"🪙 *Memecoins únicos monitoreados:* `{total_coins}`\n"

    

    await event.reply(message)



@client.on(events.NewMessage(pattern=r'/eliminar (.+)', from_users=NOTIFY_CHAT_ID))

async def delete_handler(event):

    """Elimina un memecoin de la base de datos."""

    ca_to_delete = event.pattern_match.group(1).strip()



    if not CA_PATTERN.match(ca_to_delete):

        await event.reply("❌ El formato del Contrato (CA) no parece válido.")

        return



    deleted = await delete_memecoin_from_db(ca_to_delete)



    if deleted:

        message = f"✅ Se eliminó el CA `{ca_to_delete}` y todas sus menciones de la base de datos."

        logging.info(message)

        await event.reply(message)

    else:

        message = f"🤷‍♂️ No se encontró el CA `{ca_to_delete}` en la base de datos."

        await event.reply(message)





# --- NUEVA FUNCIÓN: Monitoreo de Market Cap ---

async def market_cap_monitor():

    """

    Tarea en segundo plano que verifica periódicamente el market cap

    de los memecoins y elimina aquellos por debajo del umbral.

    """

    while True:

        logging.info(f"Iniciando verificación de market cap (cada {CHECK_INTERVAL_HOURS} horas)...")

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

                        # Changed to debug and removed bot notification for individual deletions

                        logging.debug(f"📉 Memecoin eliminado: {symbol} ({name}) con CA `{ca_address}`. Market Cap (${market_cap:,.2f}) por debajo de ${MARKET_CAP_THRESHOLD:,.2f}.")

            else:

                logging.warning(f"No se pudieron obtener datos de DexScreener para CA `{ca_address}` durante el monitoreo de market cap. Se mantendrá por ahora.")

        

        if deleted_count > 0:

            logging.info(f"Monitoreo de Market Cap completado: Se eliminaron {deleted_count} memecoins.")

        else:

            logging.info("Monitoreo de Market Cap completado: No se encontraron memecoins para eliminar.")

        

        await asyncio.sleep(CHECK_INTERVAL_HOURS * 3600) # Esperar el intervalo antes de la siguiente verificación

        

        

# --- FUNCIÓN PRINCIPAL ---



async def main():

    """Función principal para iniciar el cliente y la DB."""

    await init_db() # Inicializa la base de datos al arrancar

    

    # Inicia el cliente de Telegram y el monitor de market cap concurrentemente

    await client.start(bot_token=BOT_TOKEN) # Asegúrate de que el bot_token se pase aquí para iniciar como bot

    

    # Crea una tarea en segundo plano para el monitoreo de market cap

    asyncio.create_task(market_cap_monitor())



    logging.info("Bot iniciado con persistencia de datos (SQLite).")

    logging.info(f"Monitoreando {len(MONITORED_CHANNELS)} canales/grupos.")

    logging.info(f"Los comandos /stats y /eliminar están activos para el usuario {NOTIFY_CHAT_ID}.")

    logging.info("El bot ahora notificará a partir de la 3ª mención de un CA (incluyendo la mención actual).")

    logging.info(f"El monitor de Market Cap se ejecutará cada {CHECK_INTERVAL_HOURS} horas y eliminará CAs con MC < ${MARKET_CAP_THRESHOLD}.")

    

    await client.run_until_disconnected()



if __name__ == '__main__':

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print("Bot detenido manualmente.")

    except Exception as e:

        logging.critical(f"Error fatal en el bot: {e}", exc_info=True)
