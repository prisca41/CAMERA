import sys
import io

# Correction du crash UnicodeEncodeError (surrogates not allowed) sur Render/Linux
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='surrogateescape')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='surrogateescape')

import asyncio
import json
import logging
import os
import base64
import websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8533927172:AAH4kdIu5Sq8wpySaSVo674URpm_xKVN7fQ")
PORT = int(os.getenv("PORT", 10000))

IMAGE_ACCUEIL_URL = "https://images.unsplash.com/photo-1514533450685-4493e01d1fdc?q=80&w=1000"

SUITS = [("♠️ Pique", "Pique"), ("♥️ Cœur", "Cœur"), ("♣️ Trèfle", "Trèfle"), ("♦️ Carreau", "Carreau")]
VALUES = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

CONNECTED_CLIENTS = set()
MAGICIAN_CHAT_ID = None
SELECTED_CARD_GLOBAL = "10 de Cœur"

async def broadcast(message):
    if CONNECTED_CLIENTS:
        message_str = json.dumps(message)
        await asyncio.gather(*[client.send(message_str) for client in CONNECTED_CLIENTS if client.open])

async def ws_handler(websocket):
    CONNECTED_CLIENTS.add(websocket)
    logger.info("📱 Client (Serveur Node.js / App HTML) connecté au Bot WebSocket.")
    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get("action")

            # Réception de la photo modifiée envoyée par l'application ou le serveur
            if action in ["send_telegram_photo", "photo_processed"]:
                b64_img = data.get("imageBase64")
                card_label = data.get("cardLabel", SELECTED_CARD_GLOBAL)

                if MAGICIAN_CHAT_ID and telegram_app and b64_img:
                    try:
                        header, encoded = b64_img.split(",", 1) if "," in b64_img else ("", b64_img)
                        img_bytes = base64.b64decode(encoded)
                        photo_file = io.BytesIO(img_bytes)
                        photo_file.name = "magic_result.jpg"

                        await telegram_app.bot.send_photo(
                            chat_id=MAGICIAN_CHAT_ID,
                            photo=photo_file,
                            caption=f"🪄 *Photo truquée générée !*\n🎴 Carte imprimée : *{card_label}*\n⏱️ _Délai de révulsion d'1 minute en cours sur le téléphone..._",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Erreur lors de l'envoi de la photo sur Telegram : {e}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CONNECTED_CLIENTS.remove(websocket)

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎴 Choisir une Carte", callback_data="menu_suits")],
        [InlineKeyboardButton("📳 Vibro ON", callback_data="vibe_true"), InlineKeyboardButton("🔕 Vibro OFF", callback_data="vibe_false")]
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAGICIAN_CHAT_ID
    if update.message:
        MAGICIAN_CHAT_ID = update.message.chat_id
        await update.message.reply_photo(
            photo=IMAGE_ACCUEIL_URL,
            caption=f"🪄 *Télécommande Magic Camera Pro*\nCarte actuellement forcée : *{SELECTED_CARD_GLOBAL}*\n\nSélectionnez une nouvelle carte à forcer :",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SELECTED_CARD_GLOBAL
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_suits":
        keyboard = [[InlineKeyboardButton(n, callback_data=f"suit_{c}") for n, c in SUITS[i:i+2]] for i in range(0, len(SUITS), 2)]
        keyboard.append([InlineKeyboardButton("⬅️ Retour Menu", callback_data="main_menu")])
        await query.edit_message_caption(caption="Choisissez la couleur de la carte :", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("suit_"):
        suit_name = data.split("_")[1]
        keyboard = [[InlineKeyboardButton(v, callback_data=f"card_{v}_{suit_name}") for v in VALUES[i:i+4]] for i in range(0, len(VALUES), 4)]
        keyboard.append([InlineKeyboardButton("⬅️ Retour Couleurs", callback_data="menu_suits")])
        await query.edit_message_caption(caption=f"Couleur sélectionnée : *{suit_name}*\nChoisissez la valeur :", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("card_"):
        parts = data.split("_")
        val, suit_name = parts[1], parts[2]
        card_label = f"{val} de {suit_name}"
        SELECTED_CARD_GLOBAL = card_label

        # Diffusion vers l'application HTML et le serveur Node.js
        await broadcast({"action": "select_card", "cardLabel": card_label})

        await query.edit_message_caption(
            caption=f"✅ *{card_label}* a été définie comme carte forcée !",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎴 Changer de carte", callback_data="menu_suits")],
                [InlineKeyboardButton("⬅️ Menu principal", callback_data="main_menu")]
            ])
        )

    elif data.startswith("vibe_"):
        status = (data == "vibe_true")
        await broadcast({"action": "toggle_vibration", "status": status})
        await query.edit_message_caption(
            caption=f"✅ Vibration {'ACTIVÉE 📳' if status else 'DÉSACTIVÉE 🔕'}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu principal", callback_data="main_menu")]])
        )

    elif data == "main_menu":
        await query.edit_message_caption(
            caption=f"🪄 *Télécommande Magic Camera Pro*\nCarte actuellement forcée : *{SELECTED_CARD_GLOBAL}*",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

telegram_app = None

async def main():
    global telegram_app
    server = await websockets.serve(ws_handler, "0.0.0.0", PORT)
    logger.info(f"🚀 Serveur WebSocket Telegram démarré sur le port {PORT}")

    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback_query))

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
