
import os
import sys
import oracledb

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
