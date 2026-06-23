import time


class InMemoryTTLCache:
    def __init__(self, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self._store: dict[tuple, dict] = {}

    def get(self, key):
        item = self._store.get(key)
        if not item:
            return None
            
        # Timeframe-specific TTL to optimize API load
        ttl = self.ttl_seconds
        if isinstance(key, tuple) and len(key) == 2:
            timeframe = key[1]
            if timeframe == "1":
                ttl = 15
            elif timeframe == "5":
                ttl = 30
            elif timeframe == "15":
                ttl = 60
            elif timeframe == "30":
                ttl = 120
            elif timeframe == "60":
                ttl = 300
            elif timeframe == "240":
                ttl = 600
            elif timeframe == "D":
                ttl = 1800
                
        if time.time() - item["stored_at"] > ttl:
            self._store.pop(key, None)
            return None
        return item["value"]

    def set(self, key, value):
        self._store[key] = {
            "stored_at": time.time(),
            "value": value,
        }
