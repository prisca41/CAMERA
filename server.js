const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');
const { OpenAI } = require('openai');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Initialisation d'OpenAI avec la clé API
const openai = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY || "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"
});

const UPLOADS_DIR = path.join(__dirname, 'uploads');
if (!fs.existsSync(UPLOADS_DIR)) {
    fs.mkdirSync(UPLOADS_DIR, { recursive: true });
}

app.use(express.json({ limit: '50mb' }));
app.use(express.static(path.join(__dirname, 'public')));
app.use('/uploads', express.static(UPLOADS_DIR));

// ROUTE : Récupérer toutes les photos sauvegardées sur le serveur
app.get('/api/photos', (req, res) => {
    fs.readdir(UPLOADS_DIR, (err, files) => {
        if (err) return res.status(500).json([]);
        const photos = files
            .filter(file => file.endsWith('.jpg') || file.endsWith('.png'))
            .map(file => `/uploads/${file}`);
        res.json(photos.reverse());
    });
});

// ROUTE : Upload et sauvegarde permanente d'une photo
app.post('/api/upload', (req, res) => {
    const { image } = req.body;
    if (!image) return res.status(400).send('Aucune image fournie');

    const base64Data = image.replace(/^data:image\/\w+;base64,/, "");
    const fileName = `photo_${Date.now()}.jpg`;
    const filePath = path.join(UPLOADS_DIR, fileName);

    fs.writeFile(filePath, base64Data, 'base64', (err) => {
        if (err) return res.status(500).send('Erreur lors de la sauvegarde');
        res.json({ success: true, url: `/uploads/${fileName}` });
    });
});

// GESTION DES WEBSOCKETS EN TEMPS RÉEL
wss.on('connection', (ws) => {
    console.log('📱 Nouveau client connecté');

    ws.on('message', async (message) => {
        try {
            const data = JSON.parse(message);

            // Action 1: Forçage de carte depuis Telegram
            if (data.action === "select_card") {
                broadcast({
                    action: "select_card",
                    cardLabel: data.cardLabel
                });
            }

            // Action 2: Traitement de la photo par OpenAI
            if (data.action === "process_photo_chatgpt") {
                const { photoId, cardLabel, imageBase64, handBoundingBox } = data;

                // Appel asynchrone à OpenAI
                processImageWithOpenAI(imageBase64, cardLabel, handBoundingBox)
                    .then((processedImageBase64) => {
                        // Réponse envoyée au client pour déclencher le compte à rebours de 60s
                        broadcast({
                            action: "photo_processed",
                            photoId: photoId,
                            imageBase64: processedImageBase64
                        });
                    })
                    .catch((err) => {
                        console.error("Erreur OpenAI:", err);
                        // En cas d'erreur API, on renvoie la photo originale après délai
                        broadcast({
                            action: "photo_processed",
                            photoId: photoId,
                            imageBase64: imageBase64
                        });
                    });
            }
        } catch (e) {
            console.error("Erreur message WS:", e);
        }
    });
});

function broadcast(data) {
    wss.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify(data));
        }
    });
}

// TRAITEMENT PAR L'API CHATGPT / DALL-E / VISION
async function processImageWithOpenAI(imageBase64, cardLabel, handBoundingBox) {
    try {
        const response = await openai.chat.completions.create({
            model: "gpt-4o-mini",
            messages: [
                {
                    role: "user",
                    content: [
                        { 
                            type: "text", 
                            text: `Modifie uniquement la main repérée dans la zone X:${handBoundingBox.x}, Y:${handBoundingBox.y}. Fais en sorte que la personne tienne naturellement une carte de jeu Bicycle "${cardLabel}" entre ses doigts. Conserve intact tout le reste de la photo (visage, arrière-plan, vêtements). Renvoie l'image modifiée.` 
                        },
                        {
                            type: "image_url",
                            image_url: { url: imageBase64 }
                        }
                    ]
                }
            ],
            max_tokens: 1000
        });

        // Si l'API renvoie un lien ou une image encodée :
        if (response.choices && response.choices[0].message.content) {
            const content = response.choices[0].message.content;
            if (content.startsWith('data:image')) return content;
        }
        
        return imageBase64;
    } catch (error) {
        console.error("Erreur lors de l'appel OpenAI:", error);
        return imageBase64;
    }
}

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`🚀 Serveur magique démarré sur le port ${PORT}`);
});
