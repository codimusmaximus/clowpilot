"""Embeddings microservice.

Loads sentence-transformers once at startup and exposes a single POST /embed
endpoint. Keeps the heavy ML deps out of the main backend image.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


MODEL_NAME = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")
_model: SentenceTransformer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    _model = SentenceTransformer(MODEL_NAME)
    yield


app = FastAPI(lifespan=lifespan)


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    model: str
    dim: int


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok" if _model is not None else "loading",
        "model": MODEL_NAME,
        "dim": _model.get_sentence_embedding_dimension() if _model else None,
    }


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest) -> EmbedResponse:
    assert _model is not None, "model not loaded"
    vectors = _model.encode(req.texts, normalize_embeddings=True).tolist()
    return EmbedResponse(
        vectors=vectors,
        model=MODEL_NAME,
        dim=_model.get_sentence_embedding_dimension(),
    )
