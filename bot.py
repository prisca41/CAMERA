import asyncio
import json
import logging
import os
import io
import base64
import urllib.request
from PIL import Image
import websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8533927172:AAH4kdIu5Sq8wpySaSVo674URpm_xKVN7fQ")
PORT = int(os.getenv("PORT", 10000))

IMAGE_ACCUEIL_URL = "https://images.unsplash.com/photo-1514533450685-4493e01d1fdc?q=80&w=1000"

SUITS = [("♠️ Pique", "spade"), ("♥️ Cœur", "heart"), ("♣️ Trèfle", "club"), ("♦️ Carreau", "diamond")]
VALUES = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

CONNECTED_CLIENTS = set()
SELECTED_CARD_GLOBAL = "10 de Cœur"

def get_card_image_url(card_label):
    parts = card_label.split(" de ")
    val = parts[0]
    suit_str = parts[1] if len(parts) > 1 else "Cœur"

    suit_map = {"Pique": "spade", "Cœur": "heart", "Trèfle": "club", "Carreau": "diamond", "spade": "spade", "heart": "heart", "club": "club", "diamond": "diamond"}
    suit_code = suit_map.get(suit_str, "heart")

    val_map = {'J': 'jack', 'Q': 'queen', 'K': 'king', 'A': 'ace'}
    val_code = val_map.get(val, val.lower())

    return f"https://cdn.jsdelivr.net/gh/selfthinker/SVG-cards@master/png/500px/{suit_code}_{val_code}.png"

def process_image_composite(base64_data, card_label, hand_x=None, hand_y=None):
    try:
        header, encoded = base64_data.split(",", 1) if "," in base64_data else ("", base64_data)
        img_bytes = base64.b64decode(encoded)
        main_img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        
        w, h = main_img.size

        # Télécharger la vraie image de carte HD
        card_url = get_card_image_url(card_label)
        req = urllib.request.Request(card_url, headers={'User-Agent': 'Mozilla/5.0'})
        card_data = urllib.request.urlopen(req).read()
        card_img = Image.open(io.BytesIO(card_data)).convert("RGBA")

        # Taille ajustée de la carte (28% de la largeur)
        card_w = int(w * 0.28)
        card_h = int(card_w * 1.45)
        card_resized = card_img.resize((card_w, card_h), Image.Resampling.LANCZOS)

        # Positionnement basé sur la main ou par défaut à droite
        if hand_x is not None and hand_y is not None:
            pos_x = int(hand_x * w - (card_w / 2))
            pos_y = int(hand_y * h - (card_h / 3))
        else:
            pos_x = int(w * 0.15)
            pos_y = int(h * 0.35)

        # Incrustation propre sans contour gris
        main_img.paste(card_resized, (pos_x, pos_y), card_resized)

        buffered = io.BytesIO()
        main_img.convert("RGB").save(buffered, format="JPEG", quality=95)
        return "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"Erreur traitement image : {e}")
        return base64_data

async def broadcast(message):
    if CONNECTED_CLIENTS:
        await asyncio.gather(*[client.send(json.dumps(message)) for client in CONNECTED_CLIENTS])

async def ws_handler(websocket):
    CONNECTED_CLIENTS.add(websocket)
    logger.info("📱 Client Application Caméra connecté via WebSocket.")
    try:
        async for message in websocket:
            data = json.loads(message)
            if data.get("action") == "process_photo":
                photo_id = data.get("photoId")
                card_label = data.get("cardLabel", "10 de Cœur")
                b64_img = data.get("imageBase64")
                hand_x = data.get("handX")
                hand_y = data.get("handY")

                modified_b64 = process_image_composite(b64_img, card_label, hand_x, hand_y)

                await websocket.send(json.dumps({
                    "action": "photo_processed",
                    "photoId": photo_id,
                    "imageBase64": modified_b64
                }))
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
    if update.message:
        await update.message.reply_photo(photo=IMAGE_ACCUEIL_URL, caption="🪄 *Télécommande Magic Camera Pro*\nSélectionnez la carte à forcer :", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SELECTED_CARD_GLOBAL
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_suits":
        keyboard = [[InlineKeyboardButton(n, callback_data=f"suit_{c}") for n, c in SUITS[i:i+2]] for i in range(0, len(SUITS), 2)]
        keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="main_menu")])
        await query.edit_message_caption(caption="Choisissez la couleur :", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("suit_"):
        suit_code = data.split("_")[1]
        suit_names = {"spade": "Pique", "heart": "Cœur", "club": "Trèfle", "diamond": "Carreau"}
        suit_name = suit_names.get(suit_code, "Cœur")
        keyboard = [[InlineKeyboardButton(v, callback_data=f"card_{v}_{suit_name}") for v in VALUES[i:i+4]] for i in range(0, len(VALUES), 4)]
        keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_suits")])
        await query.edit_message_caption(caption=f"Couleur : *{suit_name}*\nChoisissez la valeur :", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("card_"):
        parts = data.split("_")
        val, suit_name = parts[1], parts[2]
        card_label = f"{val} de {suit_name}"
        SELECTED_CARD_GLOBAL = card_label

        await broadcast({"action": "select_card", "cardLabel": card_label})
        await query.edit_message_caption(caption=f"✅ *{card_label}* a été choisi avec succès !", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎴 Choisir une autre carte", callback_data="menu_suits")]]))

    elif data.startswith("vibe_"):
        status = (data == "vibe_true")
        await broadcast({"action": "toggle_vibration", "status": status})
        await query.edit_message_caption(caption=f"✅ Vibration {'ACTIVÉE 📳' if status else 'DÉSACTIVÉE 🔕'}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data="main_menu")]]))

    elif data == "main_menu":
        await query.edit_message_caption(caption="🪄 *Télécommande Magic Camera Pro*", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def main():
    server = await websockets.serve(ws_handler, "0.0.0.0", PORT)
    logger.info(f"🚀 Serveur WebSocket démarré sur le port {PORT}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
