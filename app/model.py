"""Carregamento e inferência do modelo (um único objeto compartilhado entre requisições)."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np


class ModelService:
    def __init__(self, path: Path, review_threshold: float = 0.60):
        bundle = joblib.load(path)
        self._sent, self._topic = bundle["models"]["sentiment"], bundle["models"]["topic"]
        self.meta: dict = bundle["meta"]
        self.version: str = self.meta["model_version"]
        self.review_threshold = review_threshold
        self._warmup()

    def _warmup(self) -> None:
        self.predict(["aquecimento do modelo"])

    def predict(self, texts: list[str]) -> list[dict]:
        """Inferência em lote (vetorizada): uma chamada ao modelo para todos os textos."""
        p_sent = self._sent.predict_proba(texts)
        p_topic = self._topic.predict_proba(texts)
        s_cls, t_cls = list(self._sent.classes_), list(self._topic.classes_)
        neg_idx = s_cls.index("negativo")
        out = []
        for ps, pt in zip(p_sent, p_topic):
            si, ti = int(np.argmax(ps)), int(np.argmax(pt))
            out.append({
                "sentiment": s_cls[si], "sentiment_confidence": round(float(ps[si]), 4),
                "sentiment_probabilities": {c: round(float(p), 4) for c, p in zip(s_cls, ps)},
                "topic": t_cls[ti], "topic_confidence": round(float(pt[ti]), 4),
                "negative_risk": round(float(ps[neg_idx]), 4),
                "needs_human_review": bool(ps[si] < self.review_threshold or pt[ti] < self.review_threshold),
            })
        return out
