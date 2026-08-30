import asyncio
import json
import logging
import os
import websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ---
# Remplacez par votre Token BotFather ou configurez la variable d'environnement TELEGRAM_BOT_TOKEN
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8533927172:AAH4kdIu5Sq8wpySaSVo674URpm_xKVN7fQ")

# URL WebSocket du serveur Node.js (Render)
WEBSOCKET_URL = "wss://camera-2i7z.onrender.com"

# Image de bienvenue affichée au lancement du bot
IMAGE_ACCUEIL_URL = "https://images.unsplash.com/photo-1514533450685-4493e01d1fdc?q=80&w=1000"

# Cartes et Enseignes
SUITS = [
    ("♠️ Pique", "Pique"),
    ("♥️ Cœur", "Cœur"),
    ("♣️ Trèfle", "Trèfle"),
    ("♦️ Carreau", "Carreau")
]

VALUES = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ENVOI WEBSOCKET AU SERVEUR NODE.JS ---
async def send_ws_payload(payload):
    """Envoie un message JSON au serveur WebSocket."""
    try:
        async with websockets.connect(WEBSOCKET_URL, ping_interval=None) as ws:
            await ws.send(json.dumps(payload))
            logger.info(f"Payload envoyé au serveur : {payload}")
            return True
    except Exception as e:
        logger.error(f"Erreur de connexion WebSocket : {e}")
        return False

# --- MENU PRINCIPAL (BOUTONS) ---
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎴 Choisir une Carte", callback_data="menu_suits")],
        [
            InlineKeyboardButton("📳 Vibro ON", callback_data="vibe_true"),
            InlineKeyboardButton("🔕 Vibro OFF", callback_data="vibe_false")
        ]
    ])

# --- COMMANDE /START ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption_text = (
        "🪄 *Télécommande Magic Camera Pro*\n\n"
        "Bienvenue dans l'interface de contrôle à distance.\n"
        "Sélectionnez une action ci-dessous pour forcer une carte ou régler les vibrations."
    )

    if update.message:
        await update.message.reply_photo(
            photo=IMAGE_ACCUEIL_URL,
            caption=caption_text,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

# --- GESTION DES CLICS SUR LES BOUTONS ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # 1. Sélection de la Couleur (Enseigne)
    if data == "menu_suits":
        keyboard = []
        row = []
        for name, suit_code in SUITS:
            row.append(InlineKeyboardButton(name, callback_data=f"suit_{suit_code}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="main_menu")])

        await query.edit_message_caption(
            caption="Choisissez la couleur de la carte :",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # 2. Sélection de la Valeur
    elif data.startswith("suit_"):
        suit_name = data.split("_")[1]

        keyboard = []
        row = []
        for val in VALUES:
            row.append(InlineKeyboardButton(val, callback_data=f"card_{val}_{suit_name}"))
            if len(row) == 4:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅️ Retour aux Couleurs", callback_data="menu_suits")])

        await query.edit_message_caption(
            caption=f"Couleur sélectionnée : *{suit_name}*\nChoisissez la valeur :",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # 3. Validation de la Carte & Envoi de la Commande
    elif data.startswith("card_"):
        parts = data.split("_")
        val = parts[1]
        suit_name = parts[2]
        card_label = f"{val} de {suit_name}"

        # Payload envoyé au serveur pour l'app HTML
        payload = {
            "action": "select_card",
            "cardLabel": card_label
        }

        success = await send_ws_payload(payload)
        status_icon = "✅" if success else "❌"
        status_text = f"Carte envoyée à l'application : *{card_label}*" if success else "Erreur d'envoi au serveur."

        keyboard = [
            [InlineKeyboardButton("🎴 Choisir une autre carte", callback_data="menu_suits")],
            [InlineKeyboardButton("⬅️ Menu Principal", callback_data="main_menu")]
        ]

        await query.edit_message_caption(
            caption=f"{status_icon} {status_text}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # 4. Contrôle de la Vibration
    elif data.startswith("vibe_"):
        status = True if data == "vibe_true" else False
        payload = {
            "action": "toggle_vibration",
            "status": status
        }

        success = await send_ws_payload(payload)
        status_icon = "✅" if success else "❌"
        vibe_state = "ACTIVÉE 📳" if status else "DÉSACTIVÉE 🔕"

        keyboard = [[InlineKeyboardButton("⬅️ Menu Principal", callback_data="main_menu")]]

        await query.edit_message_caption(
            caption=f"{status_icon} Vibration {vibe_state} sur le téléphone.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # 5. Retour au Menu Principal
    elif data == "main_menu":
        await query.edit_message_caption(
            caption="🪄 *Télécommande Magic Camera Pro*\nSélectionnez une action ci-dessous :",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

# --- PROGRAMME PRINCIPAL ---
def main():
    if TELEGRAM_BOT_TOKEN == "VOTRE_TOKEN_BOTFATHER_ICI":
        logger.error("Veuillez renseigner votre TOKEN BotFather dans le script ou dans les variables d'environnement.")
        return

    # Initialisation de l'application Telegram Bot
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    logger.info("Bot Telegram Magic démarré avec succès...")
    app.run_polling()

if __name__ == '__main__':
    main()
