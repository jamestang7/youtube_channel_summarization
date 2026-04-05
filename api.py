"""Minimal HTTP API server — run with: uvicorn api:app --port 8000 --reload"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from youtube_rag.core import config
from youtube_rag.rag.search_engine import ask_question

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

app = FastAPI(title="YouTube RAG API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class HealthResponse(BaseModel):
    status: str
    ollama_model: str
    llm_provider: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ollama_model=config.OLLAMA_MODEL,
        llm_provider=config.LLM_PROVIDER,
    )


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    try:
        return ask_question(req.query, top_k=req.top_k)
    except Exception as exc:
        logging.exception("ask_question failed for query=%r", req.query)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
