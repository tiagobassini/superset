from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

#SECRET_KEY = "O20PKpo6s2V9qFZVsdx5M0sQTcpF96ipwDT1hfoB"

ENABLE_PROXY_FIX = True


# Define o caminho base da aplicação Flask
SUPERSET_APP_ROOT = "/dados"
APPLICATION_ROOT = "/dados"
STATIC_ASSETS_PREFIX = "/dados"

# URL base para garantir que os redirecionamentos funcionem
SUPERSET_WEBSERVER_BASE_URL = "https://sistemas.cb.es.gov.br"


#PREFERRED_URL_SCHEME = "https"


#WTF_CSRF_ENABLED = True


#def FLASK_APP_MUTATOR(app: Flask):
#    app.wsgi_app = ProxyFix(
#        app.wsgi_app,
#        x_for=1,
#        x_proto=1,
#        x_host=1,
#    )
#    return app



#import oracledb

#oracledb.init_oracle_client()

# Alias oracledb as cx_Oracle to prevent connection errors
#sys.modules['cx_Oracle'] = oracledb
#import cx_Oracle

import sys
import oracledb

# Força o Superset/SQLAlchemy a aceitar o oracledb fingindo ser o cx_Oracle
oracledb.version = "8.3.0" 

sys.modules['cx_Oracle'] = oracledb