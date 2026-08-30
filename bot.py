import os
import json
import asyncio
import logging
from websockets.server import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ET LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Remplacez par le jeton fourni par @BotFather et l'URL de l'image d'accueil souhaitée
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8533927172:AAH4kdIu5Sq8wpySaSVo674URpm_xKVN7fQ")
WELCOME_IMAGE_URL = "https://images.unsplash.com/photo-1514539079130-25950c84af65?auto=format&fit=crop&w=1000&q=80"
PORT = int(os.environ.get("PORT", 8765))

# --- ÉTAT PERMANENT ---
CONNECTED_CLIENTS = set()
APP_STATE = {
    "selected_card": None,
    "vibration_enabled": True
}

SUITS = [
    {"name": "Pique", "symbol": "♠", "prefix": "Pique"},
    {"name": "Cœur", "symbol": "♥", "prefix": "Cœur"},
    {"name": "Trèfle", "symbol": "♣", "prefix": "Trèfle"},
    {"name": "Carreau", "symbol": "♦", "prefix": "Carreau"}
]

VALUES = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

# --- GENERATEURS DE CLAVIERS TELEGRAM ---

def build_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎴 Choisir une Carte", callback_data="menu_cards")],
        [InlineKeyboardButton("⚙️ Réglages & Contrôles", callback_data="menu_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_suits_keyboard():
    keyboard = []
    for suit in SUITS:
        keyboard.append([InlineKeyboardButton(f"{suit['symbol']} {suit['name']}", callback_data=f"suit_{suit['name']}")])
    keyboard.append([InlineKeyboardButton("🔙 Retour Menu Principal", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)

def build_cards_keyboard(suit_name):
    suit = next((s for s in SUITS if s["name"] == suit_name), None)
    symbol = suit["symbol"] if suit else ""
    
    keyboard = []
    row = []
    for idx, val in enumerate(VALUES):
        label = f"{val}{symbol}"
        card_full_label = f"{val} de {suit_name}"
        row.append(InlineKeyboardButton(label, callback_data=f"card_{card_full_label}"))
        
        if len(row) == 4 or idx == len(VALUES) - 1:
            keyboard.append(row)
            row = []
            
    keyboard.append([InlineKeyboardButton("🔙 Choisir une autre couleur", callback_data="menu_cards")])
    keyboard.append([InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)

def build_settings_keyboard():
    vibe_status = "🟢 Activé" if APP_STATE["vibration_enabled"] else "🔴 Désactivé"
    keyboard = [
        [InlineKeyboardButton(f"📳 Vibro: {vibe_status}", callback_data="toggle_vibration")],
        [InlineKeyboardButton("🔄 Réinitialiser la Carte", callback_data="reset_card")],
        [InlineKeyboardButton("📡 Statut Connexion", callback_data="check_status")],
        [InlineKeyboardButton("🔙 Retour Menu Principal", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- COMMUNICATION WEBSOCKET ---

async def broadcast_to_web(message_dict):
    if CONNECTED_CLIENTS:
        payload = json.dumps(message_dict)
        await asyncio.gather(*[client.send(payload) for client in CONNECTED_CLIENTS if client.open])

async def websocket_handler(websocket):
    CONNECTED_CLIENTS.add(websocket)
    logger.info("Un téléphone (Application Web) s'est connecté.")
    
    # Synchronisation de l'état initial
    if APP_STATE["selected_card"]:
        await websocket.send(json.dumps({
            "action": "select_card",
            "cardLabel": APP_STATE["selected_card"]
        }))
        
    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "process_photo":
                # La photo à truquer est reçue depuis le téléphone
                logger.info(f"Photo reçue pour incrustation: {data.get('photoId')}")
                
                # Simulation du traitement d'incrustation IA (Renvoie l'image d'origine ou modifiée)
                processed_payload = {
                    "action": "photo_processed",
                    "photoId": data.get("photoId"),
                    "imageBase64": data.get("imageBase64")
                }
                await websocket.send(json.dumps(processed_payload))
                
            elif msg_type == "card_selected_locally":
                APP_STATE["selected_card"] = data.get("cardLabel")
                logger.info(f"Carte sélectionnée sur le téléphone : {APP_STATE['selected_card']}")
                
    except Exception as e:
        logger.error(f"Erreur WebSocket: {e}")
    finally:
        CONNECTED_CLIENTS.remove(websocket)
        logger.info("Téléphone déconnecté.")

# --- HANDLERS TELEGRAM ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_caption = (
        "🎩 **CAMERA PRO - TÉLÉCOMMANDE MAGIQUE** 🎩\n\n"
        "Bienvenue sur l'interface de contrôle à distance.\n"
        "Ce bot vous permet de piloter la caméra et de forcer la carte de votre choix à distance.\n\n"
        "Status de l'application : "
        f"{'🟢 Connectée' if CONNECTED_CLIENTS else '🔴 En attente de connexion'}\n"
        f"Carte sélectionnée : **{APP_STATE['selected_card'] or 'Aucune'}**\n\n"
        "Sélectionnez une option ci-dessous :"
    )
    
    await update.message.reply_photo(
        photo=WELCOME_IMAGE_URL,
        caption=welcome_caption,
        parse_mode="Markdown",
        reply_markup=build_main_keyboard()
    )

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_main":
        caption = (
            "📱 **PANNEAU DE CONTRÔLE PRINCIPAL**\n\n"
            f"Carte active : **{APP_STATE['selected_card'] or 'Aucune'}**\n"
            f"Vibration : **{'Activée' if APP_STATE['vibration_enabled'] else 'Désactivée'}**\n"
            f"Appareil connecté : **{'Oui' if CONNECTED_CLIENTS else 'Non'}**"
        )
        await query.edit_message_caption(caption=caption, parse_mode="Markdown", reply_markup=build_main_keyboard())

    elif data == "menu_cards":
        caption = "🎴 **SELECTION DE LA COULEUR**\n\nChoisissez la famille de cartes à envoyer :"
        await query.edit_message_caption(caption=caption, parse_mode="Markdown", reply_markup=build_suits_keyboard())

    elif data.startswith("suit_"):
        suit_name = data.split("_")[1]
        caption = f"🎯 **SELECTION DE LA CARTE ({suit_name.upper()})**\n\nCliquez sur une valeur pour la forcer :"
        await query.edit_message_caption(caption=caption, parse_mode="Markdown", reply_markup=build_cards_keyboard(suit_name))

    elif data.startswith("card_"):
        card_label = data.replace("card_", "")
        APP_STATE["selected_card"] = card_label
        
        # Envoie l'ordre au téléphone connecté via WebSocket
        await broadcast_to_web({
            "action": "select_card",
            "cardLabel": card_label
        })

        caption = (
            f"✅ **CARTE SELECTIONNÉE ET ENVOYÉE !**\n\n"
            f"La carte **{card_label}** a été configurée avec succès sur le téléphone."
        )
        await query.edit_message_caption(caption=caption, parse_mode="Markdown", reply_markup=build_main_keyboard())

    elif data == "menu_settings":
        caption = "⚙️ **RÉGLAGES ET STATUT DU SYSTÈME**"
        await query.edit_message_caption(caption=caption, parse_mode="Markdown", reply_markup=build_settings_keyboard())

    elif data == "toggle_vibration":
        APP_STATE["vibration_enabled"] = not APP_STATE["vibration_enabled"]
        await broadcast_to_web({
            "action": "toggle_vibration",
            "status": APP_STATE["vibration_enabled"]
        })
        caption = "⚙️ **RÉGLAGES ET STATUT DU SYSTÈME**"
        await query.edit_message_caption(caption=caption, parse_mode="Markdown", reply_markup=build_settings_keyboard())

    elif data == "reset_card":
        APP_STATE["selected_card"] = None
        caption = "🔄 **Carte réinitialisée.** Aucune carte n'est forcée pour le moment."
        await query.edit_message_caption(caption=caption, parse_mode="Markdown", reply_markup=build_main_keyboard())

    elif data == "check_status":
        status_text = (
            "📡 **DIAGNOSTIC DU SYSTÈME**\n\n"
            f"• Téléphones connectés : **{len(CONNECTED_CLIENTS)}**\n"
            f"• Carte active : **{APP_STATE['selected_card'] or 'Aucune'}**\n"
            f"• Mode vibreur : **{'Activé' if APP_STATE['vibration_enabled'] else 'Désactivé'}**"
        )
        await query.edit_message_caption(caption=status_text, parse_mode="Markdown", reply_markup=build_settings_keyboard())

# --- DÉMARRAGE CONJOINT TELEGRAM + WEBSOCKET ---

async def main():
    # Initialisation du Bot Telegram
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CallbackQueryHandler(button_callback_handler))

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()

    # Initialisation du serveur WebSocket
    async with serve(websocket_handler, "0.0.0.0", PORT):
        logger.info(f"Serveur WebSocket prêt et à l'écoute sur le port {PORT}")
        await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Arrêt du serveur.")
