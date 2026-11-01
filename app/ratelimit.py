"""Rate limit por cliente (janela deslizante, em memória, thread-safe).

Limitação deliberada: o estado vive no processo. Com N réplicas/workers o limite efetivo vira
N x limite; para limite global use Redis (INCR + EXPIRE) ou o gateway (Cloudflare, API Gateway).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float = 60.0):
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, client: str, now: float | None = None) -> tuple[bool, int, float]:
        """Registra uma tentativa. Devolve (permitido, restantes, segundos_até_liberar)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[client]
            while q and now - q[0] >= self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False, 0, max(0.0, self.window_s - (now - q[0]))
            q.append(now)
            return True, self.limit - len(q), 0.0
