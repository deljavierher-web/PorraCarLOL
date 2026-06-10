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
scheduler = BackgroundScheduler(daemon=True)
