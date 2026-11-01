"""Contratos da API (Pydantic v2). Os exemplos aparecem no Swagger (/docs)."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Sentiment = Literal["negativo", "neutro", "positivo"]
Topic = Literal["entrega", "produto", "atendimento", "preco"]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"text": "O pedido chegou com 10 dias de atraso e ninguém no suporte responde."}]})

    text: Annotated[str, Field(min_length=3, description="Texto da avaliação (3 a 2000 caracteres).")]

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("O texto precisa ter ao menos 3 caracteres não vazios.")
        return v


class BatchRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [
        {"id": "a1", "text": "Chegou rápido e bem embalado, adorei!"},
        {"id": "a2", "text": "Paguei caro e o produto veio quebrado."}]}]})

    items: Annotated[list["BatchItem"], Field(min_length=1, description="Lista de avaliações.")]


class BatchItem(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=64, description="Identificador do cliente (devolvido na resposta).")]
    text: Annotated[str, Field(min_length=3)]


class Analysis(BaseModel):
    sentiment: Sentiment
    sentiment_confidence: float = Field(ge=0, le=1, description="Probabilidade da classe prevista.")
    sentiment_probabilities: dict[str, float]
    topic: Topic
    topic_confidence: float = Field(ge=0, le=1)
    negative_risk: float = Field(ge=0, le=1, description="P(sentimento = negativo); use para priorizar fila.")
    needs_human_review: bool = Field(description="True se a confiança em sentimento ou tópico estiver abaixo do limiar.")


class AnalyzeResponse(BaseModel):
    request_id: str
    model_version: str
    result: Analysis


class BatchResult(Analysis):
    id: str


class BatchResponse(BaseModel):
    request_id: str
    model_version: str
    count: int
    results: list[BatchResult]


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str | None = None


class ModelInfo(BaseModel):
    model_version: str
    trained_at: str
    sklearn_version: str
    labels: dict[str, list[str]]
    metrics: dict
    disclaimer: str
