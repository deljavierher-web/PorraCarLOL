"""
PorraCarLOL — Configuración de la Aplicación
Carga variables de entorno y define configuraciones para desarrollo y producción.
"""
import os
from dotenv import load_dotenv

# Cargar .env desde la raíz del proyecto
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(basedir, ".env"))


class Config:
    """Configuración base compartida."""

    # Flask
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")

    # SQLAlchemy — corrige postgres:// → postgresql:// (requerido por SQLAlchemy 1.4+)
    _db_url = os.environ.get("DATABASE_URL", "sqlite:///porra.db")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = 604800  # 7 días en segundos
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # Admin por defecto
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # APIs externas
    ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
    FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY", "")

    # Liga / Torneo
    SPORT_KEY = os.environ.get("SPORT_KEY", "soccer_fifa_world_cup")
    FOOTBALL_LEAGUE_ID = int(os.environ.get("FOOTBALL_LEAGUE_ID", "1"))
    FOOTBALL_SEASON = int(os.environ.get("FOOTBALL_SEASON", "2026"))

    # Configuración de Comodín Dinámico
    COMODIN_MIN_MULTIPLIER = float(os.environ.get("COMODIN_MIN_MULTIPLIER", "2.0"))
    COMODIN_MAX_MULTIPLIER = float(os.environ.get("COMODIN_MAX_MULTIPLIER", "5.0"))

    # Telegram (recordatorio de cierre de pronósticos)
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

    # Multiplicadores por fase del torneo
    # Cada jornada tiene un multiplicador que escala los puntos base (cuota × 10)
    PHASE_MULTIPLIERS = {
        1: 1,    # Fase de Grupos (J1)
        2: 1,    # Fase de Grupos (J2)
        3: 1,    # Fase de Grupos (J3)
        4: 2,    # Dieciseisavos de Final (R32)
        5: 3,    # Octavos de Final (R16)
        6: 5,    # Cuartos de Final
        7: 6,    # Semifinales
        8: 6,    # Tercer Puesto
        9: 10,   # Final
    }

    PHASE_NAMES = {
        1: "Fase de Grupos (J1)",
        2: "Fase de Grupos (J2)",
        3: "Fase de Grupos (J3)",
        4: "Dieciseisavos (R32)",
        5: "Octavos de Final",
        6: "Cuartos de Final",
        7: "Semifinales",
        8: "Tercer Puesto",
        9: "Final",
    }
