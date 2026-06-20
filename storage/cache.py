import time


class InMemoryTTLCache:
    def __init__(self, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self._store: dict[tuple, dict] = {}

    def get(self, key):
        item = self._store.get(key)
        if not item:
            return None
        if time.time() - item["stored_at"] > self.ttl_seconds:
            self._store.pop(key, None)
            return None
        return item["value"]

    def set(self, key, value):
        self._store[key] = {
            "stored_at": time.time(),
            "value": value,
        }
