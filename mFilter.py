import asyncio
import re
import logging
import httpx
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
NOTIFY_CHAT_ID = 1048966581
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1384741523651952704/PTKZT4Rb9MjaWgl7MQ47D-OC_8ZzmZKeQ9mZVOdwQpxq3NVLf8ej9Q8sINfs02gdioS2'

# --- NUEVA CONFIGURACIÓN: GeNeSiS Lounge y Usuarios de Confianza ---
# ID del grupo GeNeSiS Lounge
GENESIS_LOUNGE_ID = 2124901271
# 🔴 IMPORTANTE: Añade aquí los IDs numéricos de los usuarios a monitorear en GeNeSiS_Lounge
# Para encontrar el ID de un usuario, puedes usar bots como @userinfobot
TRUSTED_USER_IDS = { 1282048314: "GENESIS_CHAI", 7207841877: "muktartt", 5056344791: "Altrealite",
}

# --- Canales a Monitorear ---
# {ID_del_canal: "Nombre para referencia"}
# Se ha añadido GeNeSiS_Lounge a la lista para que el bot pueda escuchar en él.
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

# --- Almacenamiento en Memoria ---
# <--- MODIFICADO: Se añade 'genesis_mention_by' para guardar el nombre del usuario de confianza.
# Estructura: { 'ca_address': {'mentions': [...], 'symbol': '..', 'name': '..', 'genesis_mention_by': 'NombreDelUsuario'} }
memecoin_mentions = {}

# --- Expresiones Regulares ---
# Regex para encontrar direcciones de Solana (32-44 caracteres alfanuméricos Base58)
CA_PATTERN = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

# Inicializa el cliente de Telethon
client = TelegramClient('bot_session', API_ID, API_HASH)

async def get_dexscreener_data(token_address):
    """
    Obtiene datos de un token desde la API de DexScreener usando la dirección del token.
    """
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('pairs'):
                    return data['pairs'][0]
            elif response.status_code == 404:
                logging.warning(f"Token {token_address} no encontrado en DexScreener (404).")
            else:
                logging.error(f"Error fetching from DexScreener for {token_address}: Status {response.status_code} - {response.text}")
    except httpx.RequestError as e:
        logging.error(f"Network error fetching from DexScreener for {token_address}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error fetching from DexScreener for {token_address}: {e}")
    return None

def format_dexscreener_info(dexscreener_data):
    """Formatea la sección de datos de DexScreener para reutilizarla en ambas notificaciones."""
    if not dexscreener_data:
        return "ℹ️ _No se pudieron obtener datos adicionales de DexScreener._"

    price_usd_str = dexscreener_data.get('priceUsd', '0')
    price_usd = float(price_usd_str) if price_usd_str else 0
    liquidity_usd = dexscreener_data.get('liquidity', {}).get('usd', 0)
    market_cap = dexscreener_data.get('fdv', 0)
    volume_24h = dexscreener_data.get('volume', {}).get('h24', 0)
    price_change_24h = dexscreener_data.get('priceChange', {}).get('h24', 0)

    message = "📊 **Datos de DexScreener:**\n"
    message += f"**Precio USD:** `${price_usd:,.8f}`\n"
    message += f"**Market Cap (FDV):** `${market_cap:,.2f}`\n"
    message += f"**Liquidez:** `${liquidity_usd:,.2f}`\n"
    message += f"**Volumen (24h):** `${volume_24h:,.2f}`\n"
    message += f"**Cambio Precio (24h):** `{price_change_24h:.2f}%`\n\n"
    
    message += "🔗 **Enlaces:**\n"
    message += f"[DexScreener]({dexscreener_data.get('url')}) | "
    
    websites = dexscreener_data.get('info', {}).get('websites', [])
    if websites and websites[0].get('url'):
        message += f"[Website]({websites[0]['url']}) | "
    
    socials = dexscreener_data.get('info', {}).get('socials', [])
    if socials:
        for social in socials:
            platform = social.get('platform')
            url = social.get('url')
            if platform and url:
                message += f"[{platform.capitalize()}]({url}) "
            
    return message.strip()

async def send_to_discord(message: str):
    """
    Envía un mensaje formateado (en Markdown) al canal de Discord a través del webhook.
    """
    if not DISCORD_WEBHOOK_URL:
        logging.warning("No se ha configurado DISCORD_WEBHOOK_URL.")
        return

    payload = {
        "content": message,
        "allowed_mentions": {"parse": []}
    }

    headers = {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(DISCORD_WEBHOOK_URL, json=payload, headers=headers)
            if response.status_code != 204:
                logging.error(f"Error al enviar a Discord: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Excepción al enviar a Discord: {e}")


def format_genesis_notification(ca, sender, dexscreener_data, existing_mentions):
    """Formatea la notificación para un CA compartido en GeNeSiS_Lounge por un usuario de confianza."""
    sender_name = sender.first_name
    if sender.username:
        sender_name = f"@{sender.username}"
        
    message = f"🚨 **Alerta de CA en GeNeSiS Lounge** 🚨\n\n"
    message += f"👤 **Compartido por:** **{sender_name}**\n"
    message += f"**Contrato (CA):** `{ca}`\n\n"
    
    # Historial de menciones
    message += "📜 **Historial en otros canales:**\n"
    if existing_mentions and 'mentions' in existing_mentions:
        mention_list = existing_mentions['mentions']
        unique_channels = {m['channel_name'] for m in mention_list}
        message += f"❗️ Este CA **ya ha sido mencionado** {len(mention_list)} veces en {len(unique_channels)} canales.\n"
        message += f"**Canales:** `{'`, `'.join(unique_channels)}`\n\n"
    else:
        message += "✅ ¡Este CA parece ser **nuevo**! No se encontraron menciones previas en los canales monitoreados.\n\n"
        
    # Info de DexScreener
    message += format_dexscreener_info(dexscreener_data)
    
    return message

# <--- MODIFICADO: Añadido el parámetro 'genesis_info' para incluir el dato adicional.
def format_standard_notification(ca, token_data, reason, total_mentions, channel_list, dexscreener_data, genesis_info=None):
    """Formatea la notificación estándar para los canales monitoreados."""
    symbol = token_data.get('symbol', f'Token({ca[:5]}..)')
    name = token_data.get('name', 'N/A')

    message = f"🚨 **Alerta de Memecoin: {symbol} ({name})** 🚨\n\n"
    message += f"**Motivo:** {reason}\n"
    message += f"**Menciones Totales:** {total_mentions} en {len(channel_list)} canales distintos.\n"
    message += f"**Canales:** `{'`, `'.join(channel_list)}`\n"
    message += f"**Contrato (CA):** `{ca}`\n\n"
    
    # <--- NUEVO: Si hay información de una mención en Genesis, se añade aquí.
    if genesis_info:
        message += f"💡 **Dato Adicional:** Este CA fue compartido en GeNeSiS Lounge por **{genesis_info}**.\n\n"

    message += format_dexscreener_info(dexscreener_data)

    return message.strip()


async def find_ca_in_message_chain(message):
    """Busca un CA en el mensaje actual o en la cadena de respuestas."""
    ca = None
    current_msg = message
    # Limitar la búsqueda a 5 respuestas para evitar bucles infinitos
    for _ in range(5):
        if not current_msg:
            break
        if current_msg.text:
            ca_match = CA_PATTERN.search(current_msg.text)
            if ca_match:
                ca = ca_match.group(0)
                return ca
        # Avanza al mensaje respondido
        if hasattr(current_msg, 'get_reply_message') and current_msg.is_reply:
            current_msg = await current_msg.get_reply_message()
        else:
            break
    return None


@client.on(events.NewMessage(chats=list(MONITORED_CHANNELS.keys())))
async def new_message_handler(event):
    """Manejador principal que se activa con cada nuevo mensaje en los canales monitoreados."""
    
    if event.message.fwd_from:
        return

    message = event.message
    chat_id = event.chat_id
    # Normalizar ID del canal/grupo si es negativo
    normalized_chat_id = int(str(chat_id)[4:]) if chat_id < 0 else chat_id
    
    channel_name = MONITORED_CHANNELS.get(normalized_chat_id, f"ID:{normalized_chat_id}")

    # Buscar el CA en el mensaje actual o en los mensajes a los que responde
    ca = await find_ca_in_message_chain(message)
    if not ca:
        return
        
    logging.info(f"CA Detectado: {ca} (en '{channel_name}')")

    # --- LÓGICA PARA GeNeSiS_Lounge ---
    if normalized_chat_id == GENESIS_LOUNGE_ID:
        sender = await message.get_sender()
        if not isinstance(sender, User) or sender.id not in TRUSTED_USER_IDS:
            logging.info(f"CA en GeNeSiS Lounge ignorado (autor no está en la lista de confianza). Sender ID: {sender.id}")
            return
            
        logging.info(f"¡ALERTA! CA de usuario de confianza ({sender.first_name}) en GeNeSiS Lounge.")
        
        sender_name = sender.first_name
        if sender.username:
            sender_name = f"@{sender.username}"

        # <--- NUEVO: Lógica para registrar la mención de Genesis.
        # Se asegura de que el CA exista en la base de datos y luego añade la información.
        if ca not in memecoin_mentions:
            # Si el CA es completamente nuevo, obtenemos sus datos básicos primero.
            dexscreener_data_for_init = await get_dexscreener_data(ca)
            if dexscreener_data_for_init:
                base_token = dexscreener_data_for_init.get('baseToken', {})
                memecoin_mentions[ca] = {
                    'mentions': [], # Aún no tiene menciones de canales estándar.
                    'symbol': base_token.get('symbol'),
                    'name': base_token.get('name'),
                    'genesis_mention_by': None # Inicializar
                }
        
        # Ahora que nos aseguramos de que el CA existe en el dict, guardamos el nombre del usuario.
        if ca in memecoin_mentions:
             memecoin_mentions[ca]['genesis_mention_by'] = sender_name
             logging.info(f"Se ha registrado la mención de '{sender_name}' para el CA {ca}.")

        # Obtener datos y verificar menciones previas en OTROS canales
        dexscreener_data = await get_dexscreener_data(ca)
        existing_mentions = memecoin_mentions.get(ca)
        
        notification = format_genesis_notification(ca, sender, dexscreener_data, existing_mentions)
        await client.send_message(NOTIFY_CHAT_ID, notification, parse_mode='md', link_preview=False)
        await send_to_discord(notification)
        return # Terminar ejecución para este evento

    # --- LÓGICA PARA CANALES DE MONITOREO ESTÁNDAR ---
    if ca not in memecoin_mentions:
        dexscreener_data = await get_dexscreener_data(ca)
        if not dexscreener_data:
            logging.warning(f"No se encontraron datos en DexScreener para el nuevo CA: {ca}. Se ignora.")
            return

        base_token = dexscreener_data.get('baseToken', {})
        memecoin_mentions[ca] = {
            'mentions': [{'channel_id': normalized_chat_id, 'channel_name': channel_name}],
            'symbol': base_token.get('symbol'),
            'name': base_token.get('name'),
            'genesis_mention_by': None # <--- NUEVO: Inicializar la clave como nula.
        }
        logging.info(f"Primera mención de {ca} ({memecoin_mentions[ca]['symbol']}). Almacenado.")
        return

    # Lógica para menciones subsecuentes en canales estándar
    mention_data = memecoin_mentions[ca]
    
    mentions_in_current_channel = sum(1 for m in mention_data['mentions'] if m['channel_id'] == normalized_chat_id)
    unique_channels_before_this = {m['channel_name'] for m in mention_data['mentions']}
    
    mention_data['mentions'].append({'channel_id': normalized_chat_id, 'channel_name': channel_name})
    
    total_mentions = len(mention_data['mentions'])
    unique_channels_after_this = {m['channel_name'] for m in mention_data['mentions']}
    
    notification_reason = None
    
    is_new_channel = len(unique_channels_after_this) > len(unique_channels_before_this)
    if is_new_channel:
        notification_reason = f"Mencionado en un nuevo canal: **{channel_name}** ({len(unique_channels_after_this)} canales en total)."
    elif mentions_in_current_channel == 1: # Es la segunda mención en el mismo canal
        notification_reason = f"Segunda mención en el canal **{channel_name}**."
    elif mentions_in_current_channel == 2: # Es la tercera mención
        notification_reason = f"Tercera mención en el canal **{channel_name}**."
        
    if notification_reason:
        logging.info(f"¡ALERTA! Razón: {notification_reason} para CA: {ca}")
        
        dexscreener_data = await get_dexscreener_data(ca)
        
        # <--- MODIFICADO: Obtenemos la información de la mención en Genesis para pasarla al formateador.
        genesis_info = mention_data.get('genesis_mention_by')

        message_to_send = format_standard_notification(
            ca,
            mention_data,
            notification_reason,
            total_mentions,
            list(unique_channels_after_this),
            dexscreener_data,
            genesis_info=genesis_info # <--- MODIFICADO: Pasamos el dato extra.
        )
        
        await client.send_message(NOTIFY_CHAT_ID, message_to_send, parse_mode='md', link_preview=False)
        await send_to_discord(message_to_send)


async def main():
    """Función principal para iniciar el cliente."""
    await client.start()
    # Imprimir un mensaje de confirmación con los IDs de confianza cargados
    loaded_users = len(TRUSTED_USER_IDS)
    logging.info("Bot de monitoreo (v5 - GeNeSiS Memory) iniciado.")
    logging.info(f"Monitoreando {len(MONITORED_CHANNELS)} canales/grupos.")
    logging.info(f"Cargados {loaded_users} usuarios de confianza para GeNeSiS Lounge.")
    if loaded_users == 0:
        logging.warning("La lista de usuarios de confianza está vacía. Las alertas de GeNeSiS Lounge no se activarán.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot detenido manualmente.")