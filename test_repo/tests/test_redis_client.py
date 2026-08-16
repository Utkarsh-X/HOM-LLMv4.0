"""Hidden test: pickle cache hits must be counted as hits, not misses.

The RedisClient.get() pickle path increments self._misses on a successful
pickle retrieval. This test asserts the stats counters are correct.
"""
import pytest

from cache.redis_client import RedisClient


class _FakeRedisClient:
    """Minimal stand-in for redis.Redis backed by an in-memory dict."""

    def __init__(self):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value, ex=None):
        self._store[key] = value

    def delete(self, key):
        self._store.pop(key, None)


@pytest.fixture
def client():
    RedisClient._instance = None
    c = RedisClient()
    c.client = _FakeRedisClient()
    c._hits = 0
    c._misses = 0
    yield c
    RedisClient._instance = None


def test_pickle_hit_counts_as_hit(client):
    client.set("doc:1", {"title": "alpha", "tags": ["a", "b"]}, serializer="pickle")

    value = client.get("doc:1", deserializer="pickle")

    assert value == {"title": "alpha", "tags": ["a", "b"]}
    stats = client.get_stats()
    assert stats["hits"] == 1, f"pickle hit must count as hit, got {stats}"
    assert stats["misses"] == 0, f"pickle hit must not count as miss, got {stats}"


def test_json_hit_counts_as_hit(client):
    client.set("doc:2", {"count": 3}, serializer="json")

    value = client.get("doc:2", deserializer="json")

    assert value == {"count": 3}
    stats = client.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 0


def test_miss_counts_as_miss(client):
    value = client.get("missing-key")

    assert value is None
    stats = client.get_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 1
