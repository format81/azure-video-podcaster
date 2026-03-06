# Azure Video Podcaster

Generate professional video podcasts from text using **Azure AI Speech Text-to-Speech Avatar** (Batch Synthesis API).

Input a script (or a topic) and get an MP4 video of a photorealistic avatar speaking your content with natural lip-sync, gestures, and embedded subtitles.

---

## Architecture

```
                                        +---------------------+
                                   +--->| Azure Speech Service|
                                   |    | TTS Avatar Batch API|
+-----------+    +--------------+  |    +---------------------+
|  Browser  |--->| Container App|--+
|  Frontend |<---| FastAPI      |--+    +---------------------+
+-----------+    +--------------+  +--->| Azure Blob Storage  |
                        |              | (persistent videos) |
                        |              +---------------------+
                        |
                        +--------->+---------------------+
                        (optional) | Azure OpenAI (GPT-4o)|
                                   | Script generation    |
                                   +---------------------+
```

**Services used:**
- **Azure AI Speech Service** (S0 tier) - TTS Avatar Batch Synthesis API
- **Azure Blob Storage** - Persistent video storage with SAS download URLs
- **Azure OpenAI** (optional) - Auto-generate scripts from topics
- **Azure Container Apps** - Serverless hosting (scale to zero)
- **Azure Container Registry** - Docker image storage
- **Azure Log Analytics** - Monitoring
- **Managed Identity** - Secure service-to-service auth

---

## Supported Regions

TTS Avatar is available **only** in these regions:
- `westeurope` (recommended for EU)
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
cd azure-video-podcaster
chmod +x scripts/deploy.sh

# Deploy everything (Speech Service, Storage, ACR, Container App)
RESOURCE_GROUP=rg-video-podcaster \
LOCATION=westeurope \
./scripts/deploy.sh
```

The script will:
1. Create a Resource Group
2. Deploy infrastructure via Bicep (Speech S0, Storage, ACR, Container Apps)
3. Build and push the Docker image
4. Output the live API URL

### 3. Local Development

```bash
cp .env.example .env
# Edit .env with your Azure Speech key and region

# Run locally
docker-compose up --build

# Or without Docker
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Web Frontend

Open `http://localhost:8000/static/index.html` for the built-in web interface.

---

## API Endpoints

### Core

| Method   | Endpoint                         | Description                              |
|----------|----------------------------------|------------------------------------------|
| `POST`   | `/podcast/generate`              | Generate video from script text          |
| `POST`   | `/podcast/generate-from-topic`   | Generate video from topic (Azure OpenAI) |
| `GET`    | `/podcast/{job_id}`              | Check job status                         |
| `GET`    | `/podcast/{job_id}/download`     | Get SAS download URL                     |
| `GET`    | `/podcast/{job_id}/subtitle`     | Get subtitle file URL                    |
| `GET`    | `/podcast`                       | List all jobs                            |
| `DELETE` | `/podcast/{job_id}`              | Delete a job                             |
| `POST`   | `/podcast/generate-script`       | Get script writing template              |

### Admin

| Method | Endpoint    | Description                        |
|--------|-------------|------------------------------------|
| `GET`  | `/`         | Service info                       |
| `GET`  | `/health`   | Health check                       |
| `GET`  | `/avatars`  | List avatars, styles, and voices   |

### Authentication

If `API_KEY` is set in the environment, all endpoints (except `/health`) require an `X-API-Key` header:

```bash
curl -H "X-API-Key: your-key" https://your-app.azurecontainerapps.io/avatars
```

### Rate Limiting

By default, 10 requests per 60 seconds per client IP. Configure via `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS` env vars. Set `RATE_LIMIT_REQUESTS=0` to disable.

---

## Usage Examples

### Generate a Podcast from Script

```bash
curl -X POST https://your-app.azurecontainerapps.io/podcast/generate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Benvenuti al nostro podcast settimanale...",
    "title": "Weekly Briefing - Episode 7",
    "voice": "it-IT-DiegoNeural",
    "avatar_character": "jeff",
    "avatar_style": "business",
    "subtitle": true
  }'
```

### Generate from Topic (requires Azure OpenAI)

```bash
curl -X POST https://your-app.azurecontainerapps.io/podcast/generate-from-topic \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Le principali minacce ransomware nel 2026 e come proteggersi",
    "title": "Ransomware Update Q1 2026"
  }'
```

### Check Status

```bash
curl https://your-app.azurecontainerapps.io/podcast/podcast-a1b2c3d4e5f6
```

### Download Video (SAS URL)

```bash
curl https://your-app.azurecontainerapps.io/podcast/podcast-a1b2c3d4e5f6/download
```

### Get Subtitles

```bash
curl https://your-app.azurecontainerapps.io/podcast/podcast-a1b2c3d4e5f6/subtitle
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

---

## Available Avatars

| Character | Styles |
|-----------|--------|
| **lisa**  | casual-sitting, graceful-sitting, graceful-standing, technical-sitting, technical-standing |
| **harry** | business, casual, youthful |
| **jeff**  | business, casual, formal |
| **max**   | business, casual, formal |
| **lori**  | casual, formal, graceful |

---

## Project Structure

```
azure-video-podcaster/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── config.py                # Configuration and constants
│   ├── models.py                # Pydantic request/response models
│   ├── middleware.py             # Auth and rate limiting
│   ├── routes/
│   │   ├── podcast.py           # Podcast CRUD endpoints
│   │   └── admin.py             # Health, avatars, root
│   ├── services/
│   │   ├── speech.py            # Azure Speech TTS Avatar client
│   │   ├── storage.py           # Azure Blob Storage client
│   │   └── openai.py            # Azure OpenAI script generation
│   └── static/
│       └── index.html           # Web frontend
├── tests/
│   ├── conftest.py              # Shared fixtures
│   ├── test_routes.py           # Route tests
│   └── test_services.py         # Service tests
├── infra/
│   └── main.bicep               # Azure IaC (Speech + Storage + OpenAI + Container App)
├── scripts/
│   └── deploy.sh                # One-click deployment
├── .github/workflows/
│   └── deploy.yml               # CI/CD pipeline
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

## Environment Variables

| Variable                          | Required | Description                                  |
|-----------------------------------|----------|----------------------------------------------|
| `AZURE_SPEECH_KEY`                | Yes      | Azure Speech Service API key                 |
| `AZURE_SPEECH_REGION`             | Yes      | Region (westeurope, westus2, southeastasia)   |
| `AZURE_STORAGE_CONNECTION_STRING` | No       | Blob Storage connection string               |
| `AZURE_STORAGE_CONTAINER`         | No       | Blob container name (default: podcast-videos) |
| `AZURE_OPENAI_ENDPOINT`          | No       | Azure OpenAI endpoint URL                    |
| `AZURE_OPENAI_KEY`               | No       | Azure OpenAI API key                         |
| `AZURE_OPENAI_DEPLOYMENT`        | No       | OpenAI deployment name (default: gpt-4o)     |
| `API_KEY`                        | No       | API key for X-API-Key auth                   |
| `SAS_EXPIRY_HOURS`               | No       | SAS URL expiry in hours (default: 48)        |
| `RATE_LIMIT_REQUESTS`            | No       | Max requests per window (default: 10, 0=off) |
| `RATE_LIMIT_WINDOW_SECONDS`      | No       | Rate limit window (default: 60)              |

---

## Troubleshooting

**"AZURE_SPEECH_KEY not configured"**
Set the `AZURE_SPEECH_KEY` environment variable. Get it from Azure Portal > Speech Service > Keys and Endpoint.

**Avatar synthesis returns 400/403**
- Ensure you are using the **S0** tier (not Free F0)
- Ensure your region is one of: `westeurope`, `westus2`, `southeastasia`
- Check that the avatar character and style combination is valid (use `/avatars` endpoint)

**Video generation takes too long**
Azure Avatar batch synthesis typically takes 2-5 minutes for a 5-minute video. The system polls every 10 seconds for up to 20 minutes.

**"Azure OpenAI is not configured"**
Set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, and `AZURE_OPENAI_DEPLOYMENT` to use the `/podcast/generate-from-topic` endpoint.

**Storage / Download not working**
Set `AZURE_STORAGE_CONNECTION_STRING` for persistent video storage. Without it, videos are only available via Azure Speech's temporary URLs (expire in 48 hours).

---

## Azure Configuration Notes

### Setting up Azure OpenAI (optional)

1. Create an Azure OpenAI resource in the Azure Portal
2. Deploy a `gpt-4o` model in Azure OpenAI Studio
3. Copy the endpoint, key, and deployment name to your `.env`

### Setting up Blob Storage (optional)

The Bicep template creates the Storage Account automatically. To configure manually:
1. Create a Storage Account in the Azure Portal
2. Create a container named `podcast-videos`
3. Copy the connection string to `AZURE_STORAGE_CONNECTION_STRING`

---

## CI/CD

GitHub Actions workflow (`.github/workflows/deploy.yml`) runs on push/PR to `main`:

1. **Test job**: Installs dependencies, runs pytest
2. **Deploy job** (on merge to main): Deploys infrastructure via Bicep, builds Docker image, updates Container App

Required GitHub Secrets:
- `AZURE_CREDENTIALS`: Service principal JSON for Azure login

---

## Pricing Estimate

| Service | Cost |
|---------|------|
| Speech Service S0 (Avatar Batch) | ~$0.10/min of generated video |
| Container Apps | Pay-per-use (scale to zero) |
| Container Registry (Basic) | ~$5/month |
| Storage Account | ~$0.02/GB/month |
| Log Analytics | ~$2.76/GB ingested |
| Azure OpenAI (GPT-4o) | ~$0.01 per script generation |

A 5-minute video costs approximately **$0.50** in Speech API charges.

---

## License

MIT
