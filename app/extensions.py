"""
PorraCarLOL — Extensiones
Instancias singleton de extensiones Flask.
Se inicializan aquí para evitar imports circulares (Application Factory Pattern).
"""
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

# Base de datos
db = SQLAlchemy()

# Autenticación JWT
jwt = JWTManager()

# Hashing de contraseñas
bcrypt = Bcrypt()

# CORS
cors = CORS()

# Scheduler para tareas en segundo plano
# misfire_grace_time: si un job no se ejecutó a su hora (reinicio, suspensión breve),
#   aún se dispara si volvemos dentro de esta ventana (1h) en lugar de saltárselo.
# coalesce: si se acumularon varias ejecuciones perdidas, ejecuta solo una.
scheduler = BackgroundScheduler(
    daemon=True,
    job_defaults={
        "misfire_grace_time": 3600,
        "coalesce": True,
    },
)
