"""Treina os modelos (sentimento e tópico) e salva ``artifacts/model.joblib`` + ``metrics.json``.

Uso:  python -m ml.train            (também executado no build do deploy)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

from .data import generate
from .evalset import EVAL_SET

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts" / "model.joblib"


def make_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), strip_accents="unicode", lowercase=True,
                                  sublinear_tf=True, min_df=2)),
        ("clf", LogisticRegression(max_iter=1000, C=4.0, class_weight="balanced")),
    ])


def _scores(pipe: Pipeline, texts: list[str], labels: list[str]) -> dict:
    pred = pipe.predict(texts)
    return {"accuracy": round(float(accuracy_score(labels, pred)), 4),
            "macro_f1": round(float(f1_score(labels, pred, average="macro")), 4), "n": len(labels)}


def train(out_path: Path = DEFAULT_OUT, n_train: int = 6000, n_test: int = 1500, seed: int = 0) -> dict:
    train_rows, test_rows = generate(n_train, seed=seed), generate(n_test, seed=seed + 1)
    hand_texts = [t for t, _, _ in EVAL_SET]
    models, metrics = {}, {}
    for target, idx in (("sentiment", 1), ("topic", 2)):
        pipe = make_pipeline().fit([r["text"] for r in train_rows], [r[target] for r in train_rows])
        models[target] = pipe
        metrics[target] = {
            "synthetic_holdout": _scores(pipe, [r["text"] for r in test_rows], [r[target] for r in test_rows]),
            "handwritten": _scores(pipe, hand_texts, [e[idx] for e in EVAL_SET]),
        }
    digest = hashlib.sha256(json.dumps(metrics, sort_keys=True).encode()).hexdigest()[:8]
    meta = {
        "model_version": f"{datetime.now(timezone.utc):%Y.%m.%d}-{digest}",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__, "n_train": n_train,
        "labels": {t: list(models[t].classes_) for t in models},
        "metrics": metrics,
        "disclaimer": "Treinado em dados sintéticos; a métrica 'handwritten' (36 frases) é a mais realista.",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"models": models, "meta": meta}, out_path, compress=3)
    out_path.with_name("metrics.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    m = train(args.out)
    print(json.dumps(m["metrics"], indent=2))
    print("modelo:", m["model_version"], "->", args.out)
