"""Métricas no formato texto do Prometheus, sem dependências externas."""
from __future__ import annotations

import threading
from collections import defaultdict

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self.buckets: dict[str, list[int]] = defaultdict(lambda: [0] * (len(BUCKETS) + 1))
        self.sums: dict[str, float] = defaultdict(float)
        self.counts: dict[str, int] = defaultdict(int)
        self.predictions: dict[str, int] = defaultdict(int)
        self.reviews_flagged = 0

    def observe(self, method: str, path: str, status: int, seconds: float) -> None:
        with self._lock:
            self.requests[(method, path, status)] += 1
            self.sums[path] += seconds
            self.counts[path] += 1
            row = self.buckets[path]
            for i, b in enumerate(BUCKETS):
                if seconds <= b:
                    row[i] += 1
            row[-1] += 1  # +Inf

    def count_predictions(self, sentiments: list[str], flagged: int) -> None:
        with self._lock:
            for s in sentiments:
                self.predictions[s] += 1
            self.reviews_flagged += flagged

    def render(self, model_version: str) -> str:
        lines = ["# HELP http_requests_total Total de requisições.", "# TYPE http_requests_total counter"]
        with self._lock:
            for (m, p, s), n in sorted(self.requests.items()):
                lines.append(f'http_requests_total{{method="{m}",path="{p}",status="{s}"}} {n}')
            lines += ["# HELP http_request_duration_seconds Latência das requisições.",
                      "# TYPE http_request_duration_seconds histogram"]
            for p, row in sorted(self.buckets.items()):
                for b, n in zip(BUCKETS, row):
                    lines.append(f'http_request_duration_seconds_bucket{{path="{p}",le="{b}"}} {n}')
                lines.append(f'http_request_duration_seconds_bucket{{path="{p}",le="+Inf"}} {row[-1]}')
                lines.append(f'http_request_duration_seconds_sum{{path="{p}"}} {self.sums[p]:.6f}')
                lines.append(f'http_request_duration_seconds_count{{path="{p}"}} {self.counts[p]}')
            lines += ["# HELP predictions_total Predições por sentimento.", "# TYPE predictions_total counter"]
            for s, n in sorted(self.predictions.items()):
                lines.append(f'predictions_total{{sentiment="{s}"}} {n}')
            lines += ["# TYPE reviews_flagged_total counter", f"reviews_flagged_total {self.reviews_flagged}",
                      "# TYPE model_info gauge", f'model_info{{version="{model_version}"}} 1']
        return "\n".join(lines) + "\n"
