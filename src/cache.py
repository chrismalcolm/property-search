import json
import redis


class Cache:
    """
        A simple Redis cache implementation.
    """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: str = None) -> None:
        self.redis_host = host
        self.redis_port = port
        self.redis_db = db
        self.redis_password = password
        self.redis_client = redis.StrictRedis(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            password=self.redis_password,
            decode_responses=True
        )

    def get(self, key: str) -> str|None:
        """
            Get a value from the cache.

            If the key does not exist, return None.
        """
        result = self.redis_client.get(key)
        if result is None:
            return None
        return json.loads(result)

    def set(self, key: str, value: str, expiry: int) -> None:
        """
            Sets a key-value pair in the cache.
        """
        self.redis_client.set(key, value, ex=expiry)
