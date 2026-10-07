"""Shared FastAPI dependencies: DB session per request, storage, scorer, rate limits."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .scoring_client import Scorer
from .settings import Settings
from .storage import Storage


def get_session(request: Request) -> Iterator[Session]:
    """One session per request; commit on success, roll back on any error."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> Storage:
    storage = request.app.state.storage
    if storage is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "audio storage not configured")
    return storage


def get_scorer(request: Request) -> Scorer:
    scorer = request.app.state.scorer
    if scorer is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "scoring not configured")
    return scorer


DB = Annotated[Session, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
AudioStorage = Annotated[Storage, Depends(get_storage)]
ScoringService = Annotated[Scorer, Depends(get_scorer)]


class SlidingWindowLimiter:
    """Per-process limiter for cheap endpoints (signed upload URLs).

    Lambda runs many processes, so this only bounds bursts per instance; the
    real ceilings are API Gateway throttling and the DB-backed per-user scoring
    limit (attempts per hour), which holds across instances.
    """

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many requests")
            q.append(now)
