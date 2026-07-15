
import os
import sys
import oracledb

from superset.config import CeleryConfig as DefaultCeleryConfig

# Força o Superset/SQLAlchemy a aceitar o oracledb fingindo ser o cx_Oracle
oracledb.version = "8.3.0"

sys.modules['cx_Oracle'] = oracledb

FEATURE_FLAGS = {
    "ENABLE_AI_INTEGRATION": os.getenv(
        "ENABLE_AI_INTEGRATION",
        "false",
    ).lower()
    in {"1", "true", "yes", "on"},
}

# Pending AI actions must survive the request that creates them so the user can
# explicitly approve them in a subsequent request. Redis is shared by the
# Superset web processes and is already provided by docker-compose.
CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 600,
    "CACHE_KEY_PREFIX": "superset_ai_",
    "CACHE_REDIS_HOST": os.getenv("REDIS_HOST", "redis"),
    "CACHE_REDIS_PORT": os.getenv("REDIS_PORT", "6379"),
    "CACHE_REDIS_DB": os.getenv("REDIS_RESULTS_DB", "1"),
}


class CeleryConfig(DefaultCeleryConfig):
    """Use Redis so Celery workers support health checks and remote control."""

    _redis_host = os.getenv("REDIS_HOST", "redis")
    _redis_port = os.getenv("REDIS_PORT", "6379")
    broker_url = (
        f"redis://{_redis_host}:{_redis_port}/"
        f"{os.getenv('REDIS_CELERY_DB', '0')}"
    )
    result_backend = (
        f"redis://{_redis_host}:{_redis_port}/"
        f"{os.getenv('REDIS_RESULTS_DB', '1')}"
    )


CELERY_CONFIG = CeleryConfig
