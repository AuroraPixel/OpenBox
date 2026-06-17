"""Cache module with global instance management."""

_instance = None


def get_cache():
    """Get the global cache instance (RedisCache or MemoryCache), or None if not set."""
    return _instance


def set_cache(cache):
    """Set the global cache instance."""
    global _instance
    _instance = cache
