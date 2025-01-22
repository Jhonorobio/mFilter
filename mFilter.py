from telethon import TelegramClient, events
import requests
from flask import Flask
import threading

# Credenciales de Telegram
api_id = '20491337'
api_hash = '72f87102bdc7c1044b2fa298dee9dca5'

# Token del bot receptor y chat_id del bot
bot_token = '7493720743:AAEzWFNGly-FZjGDLToRvOdUIuyTFvhgLh4'  # Token del bot creado en @BotFather
chat_id = '1048966581'  # Chat ID del bot receptor

# Lista de grupos o canales específicos
chats_especificos = [-1002124901271,]  # Cambia estos por los IDs de tus grupos o canales
palabras_clave = ['pump', 'palabra2', 'palabra3']  # Cambia estas palabras

# Inicializar cliente de Telethon
client = TelegramClient('session_name', api_id, api_hash)

@client.on(events.NewMessage(chats=chats_especificos))
async def handler(event):
    # Obtener información del mensaje
    sender = await event.get_sender()
    nombre_usuario = sender.username or sender.first_name or "Usuario desconocido"

    # Verificar si el mensaje contiene alguna palabra clave
    mensaje_contiene_palabras = any(palabra.lower() in event.message.message.lower() for palabra in palabras_clave)

    # Si el mensaje contiene palabras clave, enviarlo al bot receptor
    if mensaje_contiene_palabras:
        mensaje_filtrado = (
            f"{event.message.text}\n"
            f"👤 **Enviado por:** {nombre_usuario}\n"
        )

        # Enviar el mensaje al bot receptor usando su API
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        data = {'chat_id': chat_id, 'text': mensaje_filtrado, 'parse_mode': 'Markdown'}
        requests.post(url, data=data)

print("Bot ejecutándose...")

# Crear un servidor HTTP básico
app = Flask(__name__)

@app.route("/")
def home():
    return "El bot está funcionando correctamente."

# Ejecutar el servidor HTTP en un hilo separado
def start_flask():
    app.run(host="0.0.0.0", port=8080)

# Iniciar el bot y el servidor Flask
if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.start()
    client.start()
    client.run_until_disconnected()
