import asyncio
import json
import base64
import io
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import websockets

# Jeton du bot Telegram (utilisez une variable d'environnement ou collez directement votre token)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8533927172:AAH4kdIu5Sq8wpySaSVo674URpm_xKVN7fQ")

# Port d'écoute pour les WebSockets ( Render ou Railway attribuent un PORT dynamique )
PORT = int(os.environ.get("PORT", 8765))

# Variables d'état globales
connected_websockets = set()
selected_card = "Aucune"
vibration_enabled = True
last_generated_image_base64 = None

# -------------------------------------------------------------
# SERVEUR WEBSOCKET (COMMUNICATION TEMPS RÉEL AVEC LA CAMÉRA)
# -------------------------------------------------------------
async def websocket_handler(websocket):
    global selected_card, vibration_enabled, last_generated_image_base64
    connected_websockets.add(websocket)
    print("📱 Nouvelle connexion WebSocket établie !")
    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "photo_ready":
                # Réception de la photo retouchée par la caméra
                last_generated_image_base64 = data.get("imageBase64")
            elif msg_type == "vibration_status":
                vibration_enabled = data.get("status")
            elif msg_type == "card_selected_locally":
                selected_card = data.get("cardLabel")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_websockets.remove(websocket)
        print("❌ Connexion WebSocket fermée.")

async def broadcast_ws(data):
    """Envoie une instruction à toutes les instances de l'application ouvertes"""
    if connected_websockets:
        message = json.dumps(data)
        await asyncio.gather(*[ws.send(message) for ws in connected_websockets])

# -------------------------------------------------------------
# COMMANDES DU BOT TELEGRAM
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "✨ **Magic Camera Pro - Assistant Telegram** ✨\n\n"
        "Contrôle à distance synchronisé avec l'application caméra.\n"
        "Choisissez une option ci-dessous :"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎴 Sélectionner une carte", callback_data="cmd_select")],
        [InlineKeyboardButton(f"📳 Vibration: {'ON (50ms)' if vibration_enabled else 'OFF'}", callback_data="cmd_toggle_vibe")],
        [InlineKeyboardButton("🖼️ Voir la photo modifiée", callback_data="cmd_get_photo")]
    ]
    
    # Image d'illustration d'accueil
    welcome_img_url = "https://images.unsplash.com/photo-1511193311914-0346f16efe90?w=800"
    
    await update.message.reply_photo(
        photo=welcome_img_url,
        caption=welcome_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global vibration_enabled
    query = update.callback_query
    await query.answer()

    if query.data == "cmd_select":
        await query.edit_message_caption(
            caption="✍️ **Tapez le nom de la carte à sélectionner à distance** :\n\n*(Exemple : 10 de Cœur, As de Pique, Dame de Carreau, 3 de Trèfle)*",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_card_input"] = True

    elif query.data == "cmd_toggle_vibe":
        vibration_enabled = not vibration_enabled
        # Signalement immédiat à la caméra web
        await broadcast_ws({"action": "toggle_vibration", "status": vibration_enabled})
        
        status_str = "ON (50ms)" if vibration_enabled else "OFF"
        keyboard = [
            [InlineKeyboardButton("🎴 Sélectionner une carte", callback_data="cmd_select")],
            [InlineKeyboardButton(f"📳 Vibration: {status_str}", callback_data="cmd_toggle_vibe")],
            [InlineKeyboardButton("🖼️ Voir la photo modifiée", callback_data="cmd_get_photo")]
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "cmd_get_photo":
        if last_generated_image_base64:
            # Conversion de l'image Base64 en fichier pour Telegram
            base64_data = last_generated_image_base64.split(",")[1] if "," in last_generated_image_base64 else last_generated_image_base64
            image_bytes = base64.b64decode(base64_data)
            photo_file = InputFile(io.BytesIO(image_bytes), filename="magic_result.jpg")
            
            await query.message.reply_photo(photo=photo_file, caption="📸 **Voici la photo modifiée en direct !**", parse_mode="Markdown")
        else:
            await query.message.reply_text("⚠️ **Aucune photo retouchée n'est disponible pour le moment.**")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global selected_card
    if context.user_data.get("awaiting_card_input"):
        card_text = update.message.text.strip()
        selected_card = card_text
        context.user_data["awaiting_card_input"] = False

        # Transmission en 0.0s à l'application web via WebSocket
        await broadcast_ws({"action": "select_card", "cardLabel": selected_card})

        confirmation_text = f"🎉 **Félicitations !**\n\nLa carte **{selected_card}** a été sélectionnée avec succès et transmise à la caméra !"
        
        keyboard = [
            [InlineKeyboardButton("🎴 Sélectionner une autre carte", callback_data="cmd_select")],
            [InlineKeyboardButton("🖼️ Voir la photo modifiée", callback_data="cmd_get_photo")]
        ]

        await update.message.reply_text(
            text=confirmation_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# -------------------------------------------------------------
# DÉMARRAGE DU BOT ET DU SERVEUR WEBSOCKET
# -------------------------------------------------------------
async def main():
    # Initialisation de l'application Telegram
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Démarrage du serveur WebSocket
    ws_server = await websockets.serve(websocket_handler, "0.0.0.0", PORT)
    print(f"🚀 Serveur WebSocket en écoute sur le port {PORT}")

    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # Maintien de la boucle d'exécution infinie
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
