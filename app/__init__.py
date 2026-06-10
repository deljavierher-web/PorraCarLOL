"""
PorraCarLOL — Application Factory
Crea e inicializa la aplicación Flask con todas sus extensiones y blueprints.
"""
import logging
from flask import Flask, send_from_directory

from app.config import Config
from app.extensions import db, jwt, bcrypt, cors, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Application Factory: crea y configura la app Flask."""
    app = Flask(
        __name__,
        static_folder="../static",
        static_url_path="/static",
        template_folder="templates",
    )
    app.config.from_object(Config)

    # ── Inicializar extensiones ──
    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    cors.init_app(app)

    # ── JWT: verificar blocklist ──
    from app.routes.auth import BLOCKLIST

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        return jwt_payload["jti"] in BLOCKLIST

    # ── Registrar Blueprints ──
    from app.routes.auth import auth_bp
    from app.routes.api import api_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)

    # ── Rutas de Frontend (sirve templates como páginas) ──
    from flask import render_template

    @app.route("/")
    def index():
        return render_template("login.html")

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/pronosticos")
    def pronosticos():
        return render_template("pronosticos.html")

    @app.route("/cuadro")
    def cuadro():
        return render_template("cuadro.html")

    @app.route("/admin")
    def admin_panel():
        return render_template("admin.html")

    # ── Crear tablas y usuario admin por defecto ──
    with app.app_context():
        from app.models import Usuario, Partido, Prediccion  # noqa: F401

        db.create_all()
        _create_default_admin(app)
        _create_default_spectator(app)
        _seed_initial_matches(app)

    # ── Iniciar Scheduler ──
    _setup_scheduler(app)

    logger.info("⚽ PorraCarLOL — Porra del Mundial 2026 iniciada correctamente.")
    if not app.config.get("ODDS_API_KEY") and not app.config.get("FOOTBALL_API_KEY"):
        logger.info("📋 Modo manual activo: crea partidos desde el Panel Admin (/admin).")
        logger.info("💡 Para automatizar cuotas y resultados, configura las API keys en .env")
    return app


def _create_default_admin(app: Flask) -> None:
    """Crea el usuario administrador por defecto si no existe."""
    from app.models.usuario import Usuario

    admin_username = app.config["ADMIN_USERNAME"]
    admin_password = app.config["ADMIN_PASSWORD"]

    if not Usuario.query.filter_by(username=admin_username).first():
        admin = Usuario(username=admin_username, es_administrador=True)
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        logger.info(f"Usuario admin '{admin_username}' creado.")


def _create_default_spectator(app: Flask) -> None:
    """Crea el usuario espectador/invitado de solo lectura si no existe."""
    from app.models.usuario import Usuario

    guest_username = "invitado"
    guest_password = "Invitado2026!"

    if not Usuario.query.filter_by(username=guest_username).first():
        guest = Usuario(username=guest_username, es_administrador=False)
        guest.set_password(guest_password)
        db.session.add(guest)
        db.session.commit()
        logger.info(f"Usuario invitado de solo lectura '{guest_username}' creado.")


def _seed_initial_matches(app: Flask) -> None:
    """Crea los partidos del Mundial 2026 desde la API pública si la base de datos está vacía."""
    from app.models.partido import Partido
    from app.services.worldcup_sync_service import sync_worldcup_data

    if Partido.query.count() == 0:
        logger.info("Sembrando todos los partidos del Mundial 2026 desde API pública...")
        try:
            res = sync_worldcup_data()
            logger.info(f"Sembrado completado: {res.get('created', 0)} partidos creados.")
        except Exception as e:
            logger.error(f"Error sembrando partidos: {e}")


def _setup_scheduler(app: Flask) -> None:
    """Configura tareas periódicas con APScheduler."""
    from app.services.odds_service import fetch_upcoming_odds
    from app.services.results_service import check_finished_matches
    from app.services.worldcup_sync_service import sync_worldcup_data

    def sync_cuotas_job():
        with app.app_context():
            logger.info("⏰ Ejecutando sync de cuotas programado...")
            fetch_upcoming_odds(
                api_key=app.config["ODDS_API_KEY"],
                sport_key=app.config["SPORT_KEY"],
            )

    def check_resultados_job():
        with app.app_context():
            logger.info("⏰ Ejecutando check de resultados programado...")
            check_finished_matches(
                api_key=app.config["FOOTBALL_API_KEY"],
                league_id=app.config["FOOTBALL_LEAGUE_ID"],
                season=app.config["FOOTBALL_SEASON"],
            )

    def keyless_worldcup_sync_job():
        with app.app_context():
            logger.info("⏰ Sincronizando partidos y resultados del Mundial 2026 (Keyless)...")
            try:
                sync_worldcup_data()
            except Exception as e:
                logger.error(f"Error en keyless_worldcup_sync_job: {e}")

    # Sincronización pública y automática (Mundial 2026) cada 10 minutos
    scheduler.add_job(
        keyless_worldcup_sync_job,
        "interval",
        minutes=10,
        id="keyless_worldcup_sync",
        replace_existing=True,
    )
    logger.info("📅 Job programado: keyless_worldcup_sync cada 10 minutos.")

    if app.config.get("ODDS_API_KEY"):
        scheduler.add_job(
            sync_cuotas_job,
            "interval",
            hours=6,
            id="sync_cuotas",
            replace_existing=True,
        )
        logger.info("📅 Job programado: sync_cuotas cada 6 horas.")

    if app.config.get("FOOTBALL_API_KEY"):
        scheduler.add_job(
            check_resultados_job,
            "interval",
            minutes=15,
            id="check_resultados",
            replace_existing=True,
        )
        logger.info("📅 Job programado: check_resultados cada 15 minutos.")

    # Arrancar scheduler
    if not scheduler.running:
        scheduler.start()
