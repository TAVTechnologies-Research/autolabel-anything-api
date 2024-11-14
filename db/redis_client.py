import json
import redis


from typing import List, Any, Optional, Awaitable, Union, Literal, Tuple

import redis.typing

from settings import settings


class RedisClient:
    def __init__(self, config=settings) -> None:
        self.config = config
        self.client = redis.Redis(
            host=config.REDIS_HOSTNAME,
            port=int(config.REDIS_PORT),
            password=config.REDIS_PASSWORD,
            db=int(config.REDIS_DB),
        )
        
    def get_keys_with_pattern(self, pattern: str) -> List[str]:
        keys = self.client.keys(pattern)
        return [key.decode("utf-8") for key in keys] # type: ignore
    
    def get_values_with_pattern(self, pattern: str) -> List[str]:
        keys = self.get_keys_with_pattern(pattern)
        values = self.client.mget(keys)
        return [value.decode("utf-8") for value in values] # type: ignore


    def set(
        self, key: str, value: Union[str, int, float], ttl: Optional[int] = None
    ) -> bool:
        is_added = self.client.set(key, value)
        if ttl and is_added:
            self.set_expiration(key, ttl)
        return is_added  # type: ignore

    def get(self, key: str) -> Optional[str]:
        value = self.client.get(key)
        return value.decode("utf-8") if value else None  # type: ignore

    def get_lock(self, lock_name):
        return self.client.lock(lock_name)

    def add_set(self, key: str, values: List[str]) -> Any:
        return self.client.sadd(key, *values)

    def get_set(self, key: str) -> Any:
        return self.client.smembers(key)

    def remove_set(self, key: str, values: List[str]) -> Any:
        return self.client.srem(key, *values)

    def add_json(self, key: str, value: dict, ttl: Optional[int] = None) -> bool:
        is_added = self.client.json().set(key, "$", value)
        if ttl and is_added:
            self.set_expiration(key, ttl)
        return is_added

    def get_json(self, key: str) -> Optional[dict]:
        """
        Get json object from redis
        :param key: key to get json object
        :return: json object -> if key exists, None -> if key does not exist

        """

        return self.client.json().get(key)

    def remove_json(self, key: str) -> Any:
        return self.client.delete(key)

    def get_all_keys(self) -> List[bytes]:
        return self.client.keys()

    def get_all_values(self) -> List[str]:
        return self.client.mget(self.get_all_keys())

    def get_all_json(self) -> List[List[dict]]:
        return self.client.json().mget([k.decode() for k in self.get_all_keys()], "$")

    def set_expiration(self, key: str, seconds: int) -> Any:
        return self.client.expire(key, seconds)

    def get_expiration(self, key: str) -> Any:
        return self.client.ttl(key)

    def queue(self, queue_name: str, value: str) -> Optional[Awaitable[int] | int]:
        try:
            response = self.client.lpush(queue_name, value)
            if response:
                return response
        except Exception as e:
            print(f"Error: {e}")
            return None

    def dequeue(
        self, queue_name: str, timeout: Optional[int] = None, count: int = 1
    ) -> Optional[Awaitable[Any] | Any]:
        """Dequeue a value from a queue
        if timeout is None, it behives like non-blocking

        Args:
            queue_name (str): queue name to be dequeued
            timeout (Optional[int], optional): timeout in seconds. Defaults to None.

        Returns:
            Optional[Awaitable[Any] | Any]: Dequeued value if exists, None otherwise
        """
        try:
            if timeout is None:
                response = self.client.rpop(queue_name, count)
            else:
                if count > 1:
                    raise RuntimeWarning("Count is not supported with blocking pop")
                response = self.client.brpop([queue_name], timeout)

            if response:
                return response

        except Exception as e:
            print(f"Error: {e}")
            return None

    def validate_cache(self, key: str) -> bool:
        return self.client.exists(key)

    def stream_add(self, stream_name: str, data: dict) -> bool:
        pub_idx = self.client.xadd(stream_name, data)
        return True if pub_idx else False

    def stream_consume(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        count: int = 1,
        block: int = 0,
        strategy: Literal["latest", "unprocessed"] = "unprocessed",
    ) -> List[str]:
        """
        Consume messages from a stream
        :param stream_name:
        :param group_name:
        :param consumer_name:
        :param count:
        :param block:
        :param strategy:
        :return: List[dict]
        """
        response = self.client.xreadgroup(
            groupname=group_name,
            consumername=consumer_name,
            streams={stream_name: ">" if strategy == "unprocessed" else "$"},
            count=count,
            block=block,
        )
        out = []
        for s_name, msg in response:
            for msg_id, data in msg:
                try:
                    out.append(data[b"data"].decode("utf-8"))
                    self.stream_acknowledge(stream_name, group_name, msg_id)
                except:
                    raise RuntimeWarning(f"Error in decoding message: {data}")
        return out

    def stream_acknowledge(
        self, stream_name: str, group_name: str, message_id: str
    ) -> bool:
        return self.client.xack(stream_name, group_name, message_id)

    def stream_group_create(self, stream_name: str, group_name: str) -> bool:
        if self.stream_check_group(stream_name, group_name):
            return True
        else:
            try:
                self.client.xgroup_create(
                    stream_name, group_name, id="$", mkstream=True
                )
                return True
            except Exception as e:
                print(f"Error: {e}")
                return False

    def stream_check_group(self, stream_name: str, group_name: str) -> bool:
        try:
            groups = self.client.xinfo_groups(stream_name)
        except Exception as e:
            # No stream exists
            print(f"Error: {e}")
            return False
        return group_name in [g["name"].decode("utf-8") for g in groups]

    def stream_consume_range(
        self, stream_name: str, start: str, end: str, return_idx: bool = False
    ) -> Union[List[str], List[Tuple[str, str]]]:
        response = self.client.xrange(stream_name, start, end)
        out = []
        for msg_id, data in response:
            if return_idx:
                out.append((msg_id.decode("utf-8"), data[b"data"].decode("utf-8")))
            else:
                out.append(data[b"data"].decode("utf-8"))
        return out


def get_redis_client() -> Optional[RedisClient]:
    try:
        return RedisClient()
    except Exception as e:
        print(f"Error connecting to redis: {e}")
        return None