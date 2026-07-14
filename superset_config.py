
import sys
import oracledb

# Força o Superset/SQLAlchemy a aceitar o oracledb fingindo ser o cx_Oracle
oracledb.version = "8.3.0" 

sys.modules['cx_Oracle'] = oracledb