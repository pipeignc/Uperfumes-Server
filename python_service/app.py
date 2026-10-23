"""Adaptador HTTP; la lógica de los tres paradigmas vive en módulos separados."""

from contextlib import asynccontextmanager
from decimal import Decimal
import logging
import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .chatbot import PerfumeChatbot
from .functional import compare_perfumes
from .imperative import DEFAULT_MODEL, load_bundle, recommend
from .schema import CLIMATES, GENDERS, OCCASIONS

Rate = Annotated[Decimal, Field(gt=0, le=100000, max_digits=12, decimal_places=4)]
Budget = Annotated[int, Field(gt=0, le=100000000, strict=True)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RecommendationRequest(RequestModel):
    age: int = Field(ge=1, le=120, strict=True)
    climate: str
    occasion: str
    gender: str
    budget_clp: Budget
    rate: Rate
    top_n: int = Field(default=3, ge=1, le=10, strict=True)

    @field_validator("climate", "occasion", "gender")
    @classmethod
    def validate_category(cls, value, info):
        choices = {"climate": CLIMATES, "occasion": OCCASIONS, "gender": GENDERS}[info.field_name]
        if value not in choices:
            raise ValueError("Selecciona una opción válida: " + ", ".join(choices))
        return value


class CompareRequest(RequestModel):
    budget_clp: Budget
    rate: Rate
    query: str = Field(default="", max_length=120)
    limit: int = Field(default=12, ge=1, le=50, strict=True)


class ChatMessage(RequestModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1500)


class ChatRequest(RequestModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=8)
    rate: Rate | None = None


def create_app(model_path=None):
    path = Path(model_path or os.environ.get("PERFUME_MODEL_PATH", DEFAULT_MODEL))

    @asynccontextmanager
    async def lifespan(app):
        app.state.bundle = None
        app.state.model_status = "missing"
        if path.is_file():
            try:
                app.state.bundle = load_bundle(path)
                app.state.model_status = "ready"
            except Exception:
                logging.getLogger(__name__).exception("No se pudo cargar el modelo local; vuelve a entrenarlo.")
                app.state.model_status = "invalid"
        catalog = app.state.bundle["catalog"] if app.state.bundle else ()
        app.state.chatbot = PerfumeChatbot.from_catalog(catalog)
        yield

    app = FastAPI(title="UPerfumes · Asesor en Python", version="1.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    def get_bundle():
        if app.state.bundle is None:
            raise HTTPException(503, "El modelo no está disponible. Entrena con el dataset y reinicia el servicio.")
        return app.state.bundle

    @app.get("/api/health")
    def health():
        bundle = app.state.bundle
        return {"ok": True, "model_status": app.state.model_status, "chatbot": "local_retrieval",
                "perfume_count": len(bundle["catalog"]) if bundle else 0}

    @app.get("/api/options")
    def options():
        return {"climates": list(CLIMATES), "occasions": list(OCCASIONS), "genders": list(GENDERS)}

    @app.post("/api/recommendations")
    def recommendations(data: RecommendationRequest):
        bundle = get_bundle()
        items = recommend(bundle, **data.model_dump())
        return {"items": items, "rate": str(data.rate), "currency": "CLP",
                "price_source": bundle["price_source"],
                "notice": "Precios referenciales; disponibilidad no verificada. El puntaje no garantiza preferencia."}

    @app.post("/api/compare")
    def compare(data: CompareRequest):
        result = compare_perfumes(get_bundle()["catalog"], **data.model_dump())
        return {**result, "rate": str(data.rate), "currency": "CLP", "price_type": "reference"}

    @app.post("/api/chat")
    def chat(data: ChatRequest):
        return app.state.chatbot.reply(data.message, [item.model_dump() for item in data.history], data.rate)

    static = Path(__file__).parent / "static"

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static / "index.html")

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app


app = create_app()
