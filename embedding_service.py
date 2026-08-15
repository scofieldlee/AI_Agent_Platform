"""
Embedding microservice: provides vector embeddings via HTTP.

Runs on Python 3.9 (because torch doesn't support Python 3.13 yet).
Main application (Python 3.13) calls this service via HTTP.

Usage:
    .venv-embedding/bin/python embedding_service.py
    # Serves on http://localhost:8001

Endpoints:
    GET  /health       — Health check
    POST /embed        — Generate embeddings
        Request:  {"texts": ["hello", "world"]}
        Response: {"embeddings": [[0.1, ...], [0.2, ...]], "dimension": 512}
"""

import os
# Use HuggingFace mirror for China (avoid huggingface.co timeout)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import logging
from typing import List

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Config ---
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DEVICE = "cpu"  # Intel Mac: CPU only
PORT = 8001

# --- Model (lazy load) ---
_model: SentenceTransformer = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME, device=DEVICE)
        dim = _model.get_sentence_embedding_dimension()
        logger.info(f"Model loaded: {MODEL_NAME} (dim={dim})")
    return _model


# --- App ---
app = FastAPI(title="Embedding Service", version="1.0.0")


class EmbedRequest(BaseModel):
    texts: List[str]


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    dimension: int


@app.get("/health")
async def health():
    return {"status": "healthy", "model": MODEL_NAME}


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    model = get_model()
    embeddings = model.encode(
        req.texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    dim = model.get_sentence_embedding_dimension()
    return EmbedResponse(
        embeddings=[emb.tolist() for emb in embeddings],
        dimension=dim,
    )


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting embedding service on port {PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
