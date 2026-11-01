"""Aplicação FastAPI: Review Insight API.

Rodar localmente:  uvicorn app.main:app --reload     (docs interativas em /docs)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from . import __version__
from .config import Settings
from .metrics import Metrics
from .model import ModelService
from .ratelimit import SlidingWindowLimiter
from .schemas import (AnalyzeRequest, AnalyzeResponse, BatchRequest, BatchResponse, ErrorResponse,
                      ModelInfo)
from .security import require_api_key

log = logging.getLogger("api")

DESCRIPTION = """
Classifica **sentimento** (negativo, neutro, positivo) e **tópico** (entrega, produto, atendimento, preço)
de avaliações de clientes escritas em português, e devolve um **risco de negatividade** para priorizar filas
de suporte.

**Autenticação:** envie sua chave no header `X-API-Key` (botão *Authorize* abaixo).
**Limites:** `RATE_LIMIT_PER_MIN` requisições por minuto por chave; lotes de até `MAX_BATCH_SIZE` itens.
**Honestidade do modelo:** treinado com dados sintéticos; veja `GET /v1/model` para as métricas e ressalvas.
O campo `needs_human_review` marca predições de baixa confiança.
"""
TAGS = [
    {"name": "análise", "description": "Inferência de sentimento e tópico."},
    {"name": "operação", "description": "Saúde, prontidão, métricas e metadados do modelo."},
]
ERRORS = {401: {"model": ErrorResponse, "description": "API key ausente ou inválida."},
          422: {"model": ErrorResponse, "description": "Entrada inválida."},
          429: {"model": ErrorResponse, "description": "Limite de requisições excedido (veja `Retry-After`)."}}


_ERR_NAMES = {401: "unauthorized", 404: "not_found", 405: "method_not_allowed", 422: "validation_error",
              429: "rate_limited", 503: "unavailable"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
                   "logger": record.name, "msg": record.getMessage()}
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.handlers = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True  # o middleware já registra o acesso


def create_app(settings: Optional[Settings] = None, model: Optional[ModelService] = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.model = model or ModelService(settings.model_path, settings.review_threshold)
        log.info("modelo carregado", extra={"extra_fields": {"model_version": app.state.model.version}})
        yield

    app = FastAPI(title="Review Insight API", version=__version__, description=DESCRIPTION,
                  openapi_tags=TAGS, lifespan=lifespan, contact={"name": "Gianlucca Vidotto"},
                  license_info={"name": "MIT"})
    app.state.settings = settings
    app.state.metrics = Metrics()
    app.state.limiter = SlidingWindowLimiter(settings.rate_limit_per_min)
    if model is not None:  # injeção em testes: disponível mesmo sem executar o lifespan
        app.state.model = model
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_methods=["GET", "POST"], allow_headers=["X-API-Key", "Content-Type"])

    # ------------------------------------------------------------------ middleware
    @app.middleware("http")
    async def observability(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        t0 = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:  # noqa: BLE001 - registrado e convertido em 500 genérico
            log.exception("erro não tratado", extra={"extra_fields": {"request_id": rid}})
            response = JSONResponse(ErrorResponse(error="internal_error", request_id=rid).model_dump(),
                                    status_code=500)
        elapsed = time.perf_counter() - t0
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")  # template da rota: evita cardinalidade alta
        request.app.state.metrics.observe(request.method, path, status_code, elapsed)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Process-Time-Ms"] = f"{elapsed * 1000:.1f}"
        log.info("request", extra={"extra_fields": {
            "request_id": rid, "method": request.method, "path": path, "status": status_code,
            "ms": round(elapsed * 1000, 1), "client": getattr(request.state, "client_id", None)}})
        return response

    # ------------------------------------------------------------------ erros
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        body = ErrorResponse(error=_ERR_NAMES.get(exc.status_code, "error"), detail=str(exc.detail),
                             request_id=getattr(request.state, "request_id", None))
        return JSONResponse(body.model_dump(), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"] if p != "body")
        body = ErrorResponse(error="validation_error", detail=f"{loc}: {first['msg']}",
                             request_id=getattr(request.state, "request_id", None))
        return JSONResponse(body.model_dump(), status_code=422)

    # ------------------------------------------------------------------ dependência: auth + rate limit
    def guard(request: Request, response: Response, cid: str = Depends(require_api_key)) -> str:
        limiter: SlidingWindowLimiter = request.app.state.limiter
        allowed, remaining, retry = limiter.check(cid)
        response.headers["X-RateLimit-Limit"] = str(limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        if not allowed:
            raise HTTPException(429, "Limite de requisições excedido.",
                                headers={"Retry-After": str(int(retry) + 1),
                                         "X-RateLimit-Limit": str(limiter.limit), "X-RateLimit-Remaining": "0"})
        return cid

    def check_text(text: str) -> None:
        if len(text) > settings.max_text_chars:
            raise HTTPException(422, f"text: excede {settings.max_text_chars} caracteres.")

    # ------------------------------------------------------------------ rotas de análise
    @app.post("/v1/analyze", response_model=AnalyzeResponse, tags=["análise"], responses=ERRORS,
              summary="Analisa uma avaliação")
    def analyze(body: AnalyzeRequest, request: Request, _: str = Depends(guard)):
        check_text(body.text)
        res = request.app.state.model.predict([body.text])[0]
        request.app.state.metrics.count_predictions([res["sentiment"]], int(res["needs_human_review"]))
        return {"request_id": request.state.request_id, "model_version": request.app.state.model.version,
                "result": res}

    @app.post("/v1/analyze/batch", response_model=BatchResponse, tags=["análise"], responses=ERRORS,
              summary="Analisa várias avaliações de uma vez (inferência vetorizada)")
    def analyze_batch(body: BatchRequest, request: Request, _: str = Depends(guard)):
        if len(body.items) > settings.max_batch_size:
            raise HTTPException(422, f"items: máximo de {settings.max_batch_size} por requisição.")
        for it in body.items:
            check_text(it.text)
        preds = request.app.state.model.predict([it.text for it in body.items])
        request.app.state.metrics.count_predictions([p["sentiment"] for p in preds],
                                                    sum(p["needs_human_review"] for p in preds))
        results = [{"id": it.id, **p} for it, p in zip(body.items, preds)]
        return {"request_id": request.state.request_id, "model_version": request.app.state.model.version,
                "count": len(results), "results": results}

    @app.get("/v1/model", response_model=ModelInfo, tags=["operação"], responses={401: ERRORS[401]},
             summary="Versão, rótulos e métricas do modelo")
    def model_info(request: Request, _: str = Depends(require_api_key)):
        meta = request.app.state.model.meta
        return {k: meta[k] for k in ModelInfo.model_fields}

    # ------------------------------------------------------------------ operação (sem autenticação)
    @app.get("/health", tags=["operação"], summary="Liveness: o processo está de pé")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/ready", tags=["operação"], summary="Readiness: o modelo está carregado")
    def ready(request: Request):
        model = getattr(request.app.state, "model", None)
        if model is None:
            raise HTTPException(503, "Modelo ainda não carregado.")
        return {"status": "ready", "model_version": model.version}

    @app.get("/metrics", tags=["operação"], response_class=PlainTextResponse,
             summary="Métricas no formato Prometheus")
    def metrics(request: Request):
        return PlainTextResponse(request.app.state.metrics.render(request.app.state.model.version))

    return app


app = create_app()  # instância usada pelo uvicorn: `uvicorn app.main:app`
