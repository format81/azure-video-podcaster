# 🎙️ Azure Video Podcaster

Generate professional 5-minute video podcasts from text using **Azure AI Speech Text-to-Speech Avatar** (Batch Synthesis API).

Input a script → Get an MP4 video of a photorealistic avatar speaking your content with natural lip-sync, gestures, and embedded subtitles.

---

## Architecture

```
┌─────────────┐      ┌──────────────────────┐      ┌─────────────────────────┐
│   Client     │─────▶│  Azure Container App │─────▶│  Azure Speech Service   │
│  (API call)  │◀─────│  (FastAPI + Python)  │◀─────│  TTS Avatar Batch API   │
└─────────────┘      └──────────────────────┘      └─────────────────────────┘
                              │                              │
                              │                              ▼
                              │                     ┌─────────────────┐
                              │                     │  Generated MP4  │
                              └────────────────────▶│  (download URL) │
                                                    └─────────────────┘
```

**Services used:**
- **Azure AI Speech Service** (S0 tier) — TTS Avatar Batch Synthesis API
- **Azure Container Apps** — Serverless hosting (scale to zero)
- **Azure Container Registry** — Docker image storage
- **Azure Log Analytics** — Monitoring

---

## Supported Regions

TTS Avatar is available **only** in these regions:
- `westeurope` ← recommended for EU
- `westus2`
- `southeastasia`

---

## Quick Start

### 1. Prerequisites

- Azure CLI (`az`) installed and logged in
- Docker (for local testing)
- An Azure subscription

### 2. Deploy to Azure (one command)

```bash
# Clone and deploy
cd azure-video-podcaster
chmod +x scripts/deploy.sh

# Deploy everything (creates Speech Service, ACR, Container App)
RESOURCE_GROUP=rg-video-podcaster \
LOCATION=westeurope \
./scripts/deploy.sh
```

The script will:
1. Create a Resource Group
2. Deploy infrastructure via Bicep (Speech Service S0, ACR, Container Apps)
3. Build and push the Docker image
4. Output the live API URL

### 3. Local Development

```bash
# Copy and fill environment variables
cp .env.example .env
# Edit .env with your Azure Speech key and region

# Run locally
docker-compose up --build

# Or without Docker
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

---

## API Usage

### Generate a Podcast

```bash
curl -X POST https://your-app.azurecontainerapps.io/podcast/generate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Benvenuti al nostro podcast settimanale sulla cybersecurity. Oggi analizzeremo le principali minacce rilevate questa settimana nel panorama europeo...",
    "title": "Weekly Threat Briefing - Episodio 7",
    "voice": "it-IT-DiegoNeural",
    "avatar_character": "jeff",
    "avatar_style": "business",
    "subtitle": true
  }'
```

**Response:**
```json
{
  "job_id": "podcast-a1b2c3d4e5f6",
  "status": "Submitted",
  "title": "Weekly Threat Briefing - Episodio 7"
}
```

### Check Status

```bash
curl https://your-app.azurecontainerapps.io/podcast/podcast-a1b2c3d4e5f6
```

**When completed:**
```json
{
  "job_id": "podcast-a1b2c3d4e5f6",
  "status": "Succeeded",
  "video_url": "https://...blob.core.windows.net/...mp4",
  "duration_ms": 302000,
  "size_bytes": 45000000
}
```

### List Available Avatars & Voices

```bash
curl https://your-app.azurecontainerapps.io/avatars
```

### Get Script Template

```bash
curl -X POST https://your-app.azurecontainerapps.io/podcast/generate-script
```

### Interactive API Docs

Open `https://your-app.azurecontainerapps.io/docs` for Swagger UI.

---

## Writing a 5-Minute Script

For a ~5 minute video podcast in Italian (~130 WPM):

| Section        | Duration | Word Count |
|----------------|----------|------------|
| Introduzione   | 30 sec   | ~65        |
| Contesto       | 1 min    | ~130       |
| Corpo          | 2.5 min  | ~325       |
| Implicazioni   | 45 sec   | ~100       |
| Conclusione    | 15 sec   | ~30        |
| **Totale**     | **5 min**| **~650**   |

### SSML Tips for Better Output

You can pass `"input_kind": "SSML"` and use SSML markup:

```xml
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="it-IT">
  <voice name="it-IT-DiegoNeural">
    <prosody rate="-5%">
      Benvenuti al nostro podcast settimanale.
      <break time="500ms"/>
      Oggi parliamo di <emphasis>ransomware</emphasis>.
    </prosody>
  </voice>
</speak>
```

---

## Available Avatars

| Character | Styles |
|-----------|--------|
| **lisa**  | casual-sitting, graceful-sitting, graceful-standing, technical-sitting, technical-standing |
| **harry** | business, casual, youthful |
| **jeff**  | business, casual, formal |
| **max**   | business, casual, formal |
| **lori**  | casual, formal, graceful |

> For the full updated list: [Standard Avatars docs](https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech-avatar/avatar-gestures-with-ssml)

---

## Project Structure

```
azure-video-podcaster/
├── app/
│   └── main.py              # FastAPI application
├── infra/
│   └── main.bicep            # Azure infrastructure (IaC)
├── scripts/
│   └── deploy.sh             # One-click deployment
├── Dockerfile                 # Container image
├── docker-compose.yml         # Local development
├── requirements.txt           # Python dependencies
├── .env.example               # Environment template
└── README.md
```

---

## Pricing Estimate

| Service | Cost |
|---------|------|
| Speech Service S0 (Avatar Batch) | ~$0.10/min of generated video |
| Container Apps | Pay-per-use (scale to zero) |
| Container Registry (Basic) | ~$5/month |
| Log Analytics | ~$2.76/GB ingested |

A 5-minute video costs approximately **$0.50** in Speech API charges.

> Check [Speech Service pricing](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/) for current rates.

---

## Extending the Project

**Ideas for enhancement:**
- Add Azure OpenAI to auto-generate podcast scripts from bullet points
- Integrate with Blob Storage for persistent video archival
- Add a web frontend for non-technical users
- Schedule weekly podcast generation via Azure Functions timer trigger
- Add background images/slides behind the avatar using SSML `<mstts:backgroundimage>` tags
- Connect to TI Mindmap HUB weekly briefings for automated CTI video podcasts

---

## License

MIT
