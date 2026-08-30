import asyncio
import json
import logging
import os
import io
import base64
from PIL import Image, ImageDraw, ImageFilter
import websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8533927172:AAH4kdIu5Sq8wpySaSVo674URpm_xKVN7fQ")
PORT = int(os.getenv("PORT", 10000))

IMAGE_ACCUEIL_URL = "https://images.unsplash.com/photo-1514533450685-4493e01d1fdc?q=80&w=1000"

SUITS = [
    ("♠️ Pique", "Pique"),
    ("♥️ Cœur", "Cœur"),
    ("♣️ Trèfle", "Trèfle"),
    ("♦️ Carreau", "Carreau")
]
VALUES = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Liste des connexions WebSocket actives (l'application mobile)
CONNECTED_CLIENTS = set()
SELECTED_CARD_GLOBAL = None

# --- GÉNÉRATION / DESSIN DE LA CARTE EN COMPOSITION PIL ---
def draw_card_image(card_label):
    parts = card_label.split(" de ")
    val = parts[0]
    suit_name = parts[1] if len(parts) > 1 else "Cœur"
    
    symbols = {"Pique": "♠", "Cœur": "♥", "Trèfle": "♣", "Carreau": "♦"}
    colors = {"Pique": (20, 20, 20), "Cœur": (210, 30, 30), "Trèfle": (20, 20, 20), "Carreau": (210, 30, 30)}
    
    sym = symbols.get(suit_name, "♥")
    col = colors.get(suit_name, (210, 30, 30))
    
    # Création carte HD
    card = Image.new("RGBA", (300, 420), (255, 255, 255, 255))
    draw = ImageDraw.Draw(card)
    
    # Bordure & Coins arrondis
    draw.rectangle([0, 0, 299, 419], outline=(200, 200, 200), width=3)
    
    # Dessin simplifié du symbole & valeur
    draw.text((20, 15), f"{val}\n{sym}", fill=col)
    draw.text((130, 180), sym, fill=col)
    return card

def process_image_composite(base64_data, card_label):
    try:
        header, encoded = base64_data.split(",", 1) if "," in base64_data else ("", base64_data)
        img_bytes = base64.b64decode(encoded)
        main_img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        
        # Générer la carte
        card_img = draw_card_image(card_label)
        
        # Redimensionnement & Rotation de la carte pour incrustation naturelle (en bas à droite / main)
        w, h = main_img.size
        card_w = int(w * 0.22)
        card_h = int(card_w * 1.4)
        card_resized = card_img.resize((card_w, card_h), Image.Resampling.LANCZOS).rotate(-12, expand=True)
        
        # Positionnement stratégique dans la photo (Zone bas-droite)
        pos_x = int(w * 0.65)
        pos_y = int(h * 0.55)
        
        # Ombres portées pour réalisme
        shadow = Image.new("RGBA", card_resized.size, (0, 0, 0, 120))
        main_img.paste(shadow, (pos_x + 8, pos_y + 12), shadow)
        main_img.paste(card_resized, (pos_x, pos_y), card_resized)
        
        # Conversion finale JPEG Base64
        buffered = io.BytesIO()
        main_img.convert("RGB").save(buffered, format="JPEG", quality=90)
        output_b64 = "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode("utf-8")
        return output_b64
    except Exception as e:
        logger.error(f"Erreur incrustation photo : {e}")
        return base64_data

# --- GESTION SERVEUR WEBSOCKET ---
async def broadcast(message):
    if CONNECTED_CLIENTS:
        await asyncio.gather(*[client.send(json.dumps(message)) for client in CONNECTED_CLIENTS])

async def ws_handler(websocket):
    CONNECTED_CLIENTS.add(websocket)
    logger.info("📱 Client Application Caméra connecté via WebSocket.")
    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get("action")
            
            if action == "process_photo":
                photo_id = data.get("photoId")
                card_label = data.get("cardLabel")
                b64_img = data.get("imageBase64")
                
                logger.info(f"⚡ Traitement photo {photo_id} avec la carte {card_label}...")
                
                # Traitement graphique
                modified_b64 = process_image_composite(b64_img, card_label)
                
                # Renvoi de la photo modifiée au client
                await websocket.send(json.dumps({
                    "action": "photo_processed",
                    "photoId": photo_id,
                    "imageBase64": modified_b64
                }))
                logger.info(f"✅ Photo {photo_id} modifiée avec succès et renvoyée !")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CONNECTED_CLIENTS.remove(websocket)

# --- TELEGRAM BOT HANDLERS ---
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
        suit_name = data.split("_")[1]
        keyboard = [[InlineKeyboardButton(v, callback_data=f"card_{v}_{suit_name}") for v in VALUES[i:i+4]] for i in range(0, len(VALUES), 4)]
        keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_suits")])
        await query.edit_message_caption(caption=f"Couleur : *{suit_name}*\nChoisissez la valeur :", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("card_"):
        parts = data.split("_")
        val, suit_name = parts[1], parts[2]
        card_label = f"{val} de {suit_name}"
        SELECTED_CARD_GLOBAL = card_label

        # Synchronisation instantanée WebSocket
        await broadcast({"action": "select_card", "cardLabel": card_label})

        # Notification de confirmation demandée au Bot
        await query.edit_message_caption(
            caption=f"✅ *{card_label}* a été choisi avec succès !",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎴 Choisir une autre carte", callback_data="menu_suits")]])
        )

    elif data.startswith("vibe_"):
        status = (data == "vibe_true")
        await broadcast({"action": "toggle_vibration", "status": status})
        await query.edit_message_caption(caption=f"✅ Vibration {'ACTIVÉE 📳' if status else 'DÉSACTIVÉE 🔕'}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data="main_menu")]]))

    elif data == "main_menu":
        await query.edit_message_caption(caption="🪄 *Télécommande Magic Camera Pro*", parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- DÉMARRAGE ASYNCHRONE DUAL (WEBSOCKET + TELEGRAM) ---
async def main():
    # 1. Démarrage du Serveur WebSocket sur le PORT de Render
    server = await websockets.serve(ws_handler, "0.0.0.0", PORT)
    logger.info(f"🚀 Serveur WebSocket démarré sur le port {PORT}")

    # 2. Démarrage du Bot Telegram
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Maintien du serveur actif
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
