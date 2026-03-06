"""Application configuration and constants."""

import os

# Azure Speech Service
SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "westeurope")
SPEECH_ENDPOINT = f"https://{SPEECH_REGION}.api.cognitive.microsoft.com"
API_VERSION = "2024-08-01"

# Azure Storage
STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "podcast-videos")

# Azure OpenAI (optional)
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

# API Key authentication (optional)
API_KEY = os.getenv("API_KEY", "")

# Default avatar settings
DEFAULT_AVATAR_CHARACTER = os.getenv("AVATAR_CHARACTER", "lisa")
DEFAULT_AVATAR_STYLE = os.getenv("AVATAR_STYLE", "casual-sitting")
DEFAULT_VOICE = os.getenv("TTS_VOICE", "it-IT-ElsaNeural")
DEFAULT_LANGUAGE = os.getenv("TTS_LANGUAGE", "it-IT")

# SAS URL expiry in hours
SAS_EXPIRY_HOURS = int(os.getenv("SAS_EXPIRY_HOURS", "48"))

# Rate limiting
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Text validation
MIN_TEXT_LENGTH = 10
MAX_TEXT_LENGTH = 50000
MAX_VIDEO_DURATION_SECONDS = 1200  # 20 minutes

# Available standard avatars
STANDARD_AVATARS: dict[str, list[str]] = {
    "lisa": ["casual-sitting", "graceful-sitting", "graceful-standing", "technical-sitting", "technical-standing"],
    "harry": ["business", "casual", "youthful"],
    "jeff": ["business", "casual", "formal"],
    "max": ["business", "casual", "formal"],
    "lori": ["casual", "formal", "graceful"],
}

# Available voices for Italian
ITALIAN_VOICES: list[str] = [
    "it-IT-ElsaNeural",
    "it-IT-IsabellaNeural",
    "it-IT-DiegoNeural",
    "it-IT-GiuseppeNeural",
    "it-IT-BenignoNeural",
    "it-IT-CalimeroNeural",
    "it-IT-CataldoNeural",
    "it-IT-FabiolaNeural",
    "it-IT-FiammaNeural",
    "it-IT-GianniNeural",
    "it-IT-ImeldaNeural",
    "it-IT-IrmaNeural",
    "it-IT-LisandroNeural",
    "it-IT-PalmiraNeural",
    "it-IT-PierinaNeural",
    "it-IT-RinaldoNeural",
]
