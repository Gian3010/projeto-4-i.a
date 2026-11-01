"""Configuração via variáveis de ambiente (12-factor)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _keys_from_env() -> tuple[str, ...]:
    raw = os.getenv("API_KEYS", "")
    return tuple(k.strip() for k in raw.split(",") if k.strip())


@dataclass(frozen=True)
class Settings:
    api_keys: tuple[str, ...] = field(default_factory=_keys_from_env)
    rate_limit_per_min: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MIN", "120")))
    max_batch_size: int = field(default_factory=lambda: int(os.getenv("MAX_BATCH_SIZE", "100")))
    max_text_chars: int = field(default_factory=lambda: int(os.getenv("MAX_TEXT_CHARS", "2000")))
    review_threshold: float = field(default_factory=lambda: float(os.getenv("REVIEW_THRESHOLD", "0.60")))
    model_path: Path = field(default_factory=lambda: Path(os.getenv(
        "MODEL_PATH", str(Path(__file__).resolve().parents[1] / "artifacts" / "model.joblib"))))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    cors_origins: tuple[str, ...] = field(default_factory=lambda: tuple(
        o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()))
