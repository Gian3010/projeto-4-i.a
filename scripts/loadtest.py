"""Teste de carga simples (asyncio + httpx): mede vazão e latência reais de uma instância.

Exemplo:
  RATE_LIMIT_PER_MIN=10000000 API_KEYS=k uvicorn app.main:app --workers 2 &
  python scripts/loadtest.py --url http://127.0.0.1:8000 --key k --concurrency 32 --duration 15
  python scripts/loadtest.py --url http://127.0.0.1:8000 --key k --mode batch --batch-size 50

ATENÇÃO: números dependem da máquina; meça no ambiente que você vai usar (ex.: instância do Render).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.evalset import EVAL_SET  # noqa: E402

TEXTS = [t for t, _, _ in EVAL_SET]


def pct(sorted_vals: list[float], p: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, int(p / 100 * len(sorted_vals)))]


async def worker(client: httpx.AsyncClient, args, deadline: float, lat: list[float], codes: dict) -> None:
    rng = random.Random()
    while time.perf_counter() < deadline:
        if args.mode == "single":
            path, body = "/v1/analyze", {"text": rng.choice(TEXTS)}
        else:
            path = "/v1/analyze/batch"
            body = {"items": [{"id": str(i), "text": rng.choice(TEXTS)} for i in range(args.batch_size)]}
        t0 = time.perf_counter()
        try:
            r = await client.post(path, json=body)
            code = r.status_code
        except httpx.HTTPError:
            code = 0
        lat.append((time.perf_counter() - t0) * 1000)
        codes[code] = codes.get(code, 0) + 1


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--key", required=True)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--duration", type=float, default=15)
    ap.add_argument("--mode", choices=["single", "batch"], default="single")
    ap.add_argument("--batch-size", type=int, default=50)
    args = ap.parse_args()

    lat: list[float] = []
    codes: dict[int, int] = {}
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(base_url=args.url, headers={"X-API-Key": args.key}, limits=limits,
                                 timeout=30) as client:
        await client.post("/v1/analyze", json={"text": "aquecimento"})  # aquece conexões
        start = time.perf_counter()
        deadline = start + args.duration
        await asyncio.gather(*[worker(client, args, deadline, lat, codes) for _ in range(args.concurrency)])
        elapsed = time.perf_counter() - start

    lat.sort()
    ok = codes.get(200, 0)
    per_req = args.batch_size if args.mode == "batch" else 1
    print(json.dumps({
        "mode": args.mode, "batch_size": per_req, "concurrency": args.concurrency,
        "duration_s": round(elapsed, 1), "requests": len(lat), "status_codes": codes,
        "error_rate": round(1 - ok / max(1, len(lat)), 4),
        "requests_per_s": round(len(lat) / elapsed, 1), "reviews_per_s": round(ok * per_req / elapsed, 1),
        "latency_ms": {"p50": round(pct(lat, 50), 1), "p95": round(pct(lat, 95), 1),
                       "p99": round(pct(lat, 99), 1), "mean": round(statistics.mean(lat), 1)},
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
