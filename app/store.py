"""
Redis store — thin async wrapper around aioredis.
All keys are namespaced: snip:{code}:url  |  snip:{code}:clicks:*
"""

import json
import os
from typing import Optional

import redis.asyncio as aioredis


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class RedisStore:
    def __init__(self):
        self._client: Optional[aioredis.Redis] = None

    async def client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = await aioredis.from_url(REDIS_URL, decode_responses=True)
        return self._client

    # ── URL storage ──────────────────────────────────────────────────────────

    async def save(self, code: str, url: str, ttl_days: Optional[int] = None):
        r = await self.client()
        key = f"snip:{code}:url"
        if ttl_days:
            await r.setex(key, ttl_days * 86400, url)
        else:
            await r.set(key, url)

    async def get(self, code: str) -> Optional[str]:
        r = await self.client()
        return await r.get(f"snip:{code}:url")

    async def delete(self, code: str):
        r = await self.client()
        async for key in r.scan_iter(f"snip:{code}:*"):
            await r.delete(key)

    # ── Click storage ─────────────────────────────────────────────────────────

    async def push_click(self, code: str, event: dict):
        """Push a click event JSON blob into a Redis list (most-recent first)."""
        r = await self.client()
        await r.lpush(f"snip:{code}:clicks", json.dumps(event))

    async def get_clicks(self, code: str, limit: int = 50_000) -> list[dict]:
        r = await self.client()
        raw = await r.lrange(f"snip:{code}:clicks", 0, limit - 1)
        return [json.loads(x) for x in raw]

    async def incr_unique(self, code: str, ip_hash: str) -> bool:
        """Returns True if this IP is new for this code (HyperLogLog)."""
        r = await self.client()
        before = await r.pfcount(f"snip:{code}:hll")
        await r.pfadd(f"snip:{code}:hll", ip_hash)
        after = await r.pfcount(f"snip:{code}:hll")
        return after > before

    async def get_unique_count(self, code: str) -> int:
        r = await self.client()
        return await r.pfcount(f"snip:{code}:hll")
