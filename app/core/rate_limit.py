"""Limite de frequência de requisições (FAL-07 / INF-08).

Guarda os horários das últimas requisições de cada chave (e-mail, IP...) em
memória, numa janela deslizante. Suficiente para um único processo; com mais
de um processo ou servidor, cada um teria a própria contagem (ver INF-08).
"""
import math
import threading
import time
from collections import deque
from typing import Callable, Hashable

from fastapi import HTTPException


class RateLimiter:
    """Permite até `max_requests` registros por chave a cada `window_seconds`."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clock = clock
        self._hits: dict[Hashable, deque[float]] = {}
        # As rotas síncronas do FastAPI rodam em várias threads
        self._lock = threading.Lock()

    def _recent(self, key: Hashable, now: float) -> deque[float]:
        hits = self._hits.get(key)

        if hits is None:
            return deque()

        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()

        if not hits:
            del self._hits[key]

        return hits

    def retry_after(self, key: Hashable) -> int:
        """Segundos até a chave poder fazer outro registro (0 = pode agora)."""
        with self._lock:
            now = self.clock()
            hits = self._recent(key, now)

            if len(hits) < self.max_requests:
                return 0

            return max(1, math.ceil(hits[0] + self.window_seconds - now))

    def record(self, key: Hashable) -> None:
        with self._lock:
            self._hits.setdefault(key, deque()).append(self.clock())

    def hit(self, key: Hashable) -> int:
        """Confere e, se permitido, já registra. Devolve a espera (0 = permitido)."""
        with self._lock:
            now = self.clock()
            hits = self._recent(key, now)

            if len(hits) >= self.max_requests:
                return max(1, math.ceil(hits[0] + self.window_seconds - now))

            self._hits.setdefault(key, deque()).append(now)
            return 0

    def forget(self, key: Hashable) -> None:
        """Esquece os registros de uma chave (ex.: login certo zera as falhas)."""
        with self._lock:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def too_many_requests(wait_seconds: int, detail: str) -> HTTPException:
    """Resposta 429 com o tempo de espera no cabeçalho Retry-After."""
    return HTTPException(
        status_code=429,
        detail=detail,
        headers={"Retry-After": str(wait_seconds)},
    )


def format_wait(seconds: int) -> str:
    """'45 segundos', '1 minuto', '12 minutos'."""
    if seconds < 60:
        return f"{seconds} segundo{'s' if seconds != 1 else ''}"

    minutes = math.ceil(seconds / 60)
    return f"{minutes} minuto{'s' if minutes != 1 else ''}"
