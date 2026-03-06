"""Azure Video Podcaster - FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routes.admin import router as admin_router
from app.routes.podcast import router as podcast_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Azure Video Podcaster",
    description="Generate avatar video podcasts from text using Azure AI Speech TTS Avatar",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(podcast_router)

# Serve static frontend files
app.mount("/static", StaticFiles(directory="app/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
