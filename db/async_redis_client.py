import json
import urllib.parse

from redis import asyncio as aioredis


from typing import List, Any, Optional, Awaitable, Union

from settings import settings


class AsyncRedisClient:
    def __init__(self, config=settings) -> None:
        self.config = config
        self.client: aioredis.Redis = None  # Initialize client as None

    @classmethod
    async def create(cls, config=settings) -> "AsyncRedisClient":
        instance = cls(config)
        instance.client = await aioredis.from_url(url=instance._get_connection_url())
        return instance

    def _get_connection_url(self) -> str:
        password = urllib.parse.quote(self.config.REDIS_PASSWORD)
        return f"redis://:{password}@{self.config.REDIS_HOSTNAME}:{self.config.REDIS_PORT}/{self.config.REDIS_DB}"

    async def get(self, key: str) -> Awaitable[str | bytes]:
        value = self.client.get(key)
        return value

    async def set(
        self, key: str, value: str, ttl: Optional[int] = None
    ) -> Awaitable[bool]:
        is_added: Awaitable = self.client.set(key, value)
        if ttl:
            await is_added
            return self.set_expiration(key, ttl)
        return is_added

    async def set_expiration(self, key: str, seconds: int) -> Any:
        return await self.client.expire(key, seconds)
