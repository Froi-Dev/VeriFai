"""Small JSON result cache with Redis sharing and a bounded local fallback."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import weakref
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.Global.config import settings

logger = logging.getLogger(__name__)


def cache_key(namespace: str, value: str | bytes, *, version: str = "v1") -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    digest = hashlib.sha256(raw).hexdigest()
    return f"verifai:{version}:{namespace}:{digest}"


class ResultCache:
    def __init__(self, redis_url: str | None, *, max_entries: int = 1_000) -> None:
        self._redis = (
            Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )
            if redis_url
            else None
        )
        self._max_entries = max_entries
        self._memory: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    async def get(self, key: str) -> dict[str, Any] | None:
        payload: str | None = None
        if self._redis is not None:
            try:
                payload = await self._redis.get(key)
            except RedisError:
                logger.warning("Redis result-cache read failed; using local fallback")
        if payload is None:
            entry = self._memory.get(key)
            if entry is not None:
                expires_at, payload = entry
                if expires_at <= time.monotonic():
                    self._memory.pop(key, None)
                    payload = None
                else:
                    self._memory.move_to_end(key)
        if payload is None:
            return None
        try:
            value = json.loads(payload)
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if self._redis is not None:
            try:
                await self._redis.set(key, payload, ex=ttl_seconds)
            except RedisError:
                logger.warning("Redis result-cache write failed; using local fallback")
        self._memory[key] = (time.monotonic() + ttl_seconds, payload)
        self._memory.move_to_end(key)
        while len(self._memory) > self._max_entries:
            self._memory.popitem(last=False)

    async def get_or_compute(
        self,
        key: str,
        ttl_seconds: int,
        producer: Callable[[], Awaitable[dict[str, Any]]],
        *,
        cache_when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        cached = await self.get(key)
        if cached is not None:
            return cached, True
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = await self.get(key)
            if cached is not None:
                return cached, True
            value = await producer()
            if cache_when is None or cache_when(value):
                await self.set(key, value, ttl_seconds)
            return value, False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()


result_cache = ResultCache(
    settings.effective_result_cache_url,
    max_entries=settings.result_cache_max_entries,
)
