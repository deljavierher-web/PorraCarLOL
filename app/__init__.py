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

    @app.route("/especiales")
    def especiales():
        return render_template("especiales.html")

    @app.route("/admin")
    def admin_panel():
        return render_template("admin.html")

    @app.route("/sw.js")
    def service_worker():
        # Servido desde la raíz para que el scope del SW cubra toda la app
        return send_from_directory("../static", "sw.js", mimetype="application/javascript")

    # ── Crear tablas y usuario admin por defecto ──
    with app.app_context():
        from app.models import Usuario, Partido, Prediccion, PrediccionEspecial  # noqa: F401

        db.create_all()
        _create_default_admin(app)
        # _create_default_spectator(app)  # Desactivado para eliminar usuario invitado
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
        admin = Usuario(username=admin_username, es_administrador=True, aprobado=True)
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

    # Recordatorio de Telegram (cierre de pronósticos) cada hora
    if app.config.get("TELEGRAM_BOT_TOKEN") and app.config.get("TELEGRAM_CHAT_ID"):
        from app.services.notify_service import check_and_send_deadline_reminders

        def telegram_reminder_job():
            with app.app_context():
                try:
                    check_and_send_deadline_reminders()
                except Exception as e:
                    logger.error(f"Error en telegram_reminder_job: {e}")

        scheduler.add_job(
            telegram_reminder_job,
            "interval",
            hours=1,
            id="telegram_reminder",
            replace_existing=True,
        )
        logger.info("📅 Job programado: telegram_reminder cada hora.")
    else:
        logger.info("📵 Recordatorio de Telegram desactivado (configura TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env).")

    if app.config.get("ODDS_API_KEY"):
        scheduler.add_job(
            sync_cuotas_job,
            "interval",
            hours=12,
            id="sync_cuotas",
            replace_existing=True,
        )
        logger.info("📅 Job programado: sync_cuotas cada 12 horas.")

    if app.config.get("FOOTBALL_API_KEY"):
        scheduler.add_job(
            check_resultados_job,
            "interval",
            minutes=15,
            id="check_resultados",
            replace_existing=True,
        )
        logger.info("📅 Job programado: check_resultados cada 15 minutos.")

    # ── Jobs de WhatsApp ──────────────────────────────────────────────────────
    if app.config.get("WHATSAPP_GROUP_JID"):

        def whatsapp_recordatorio_job():
            """Cada hora: avisa a quien no ha entregado pronósticos de la jornada abierta."""
            with app.app_context():
                try:
                    from app.services.whatsapp_jobs import check_and_notify_pendientes
                    check_and_notify_pendientes()
                except Exception as e:
                    logger.error(f"Error en whatsapp_recordatorio_job: {e}")

        def whatsapp_ranking_manana_job():
            """Cada mañana a las 9:00 manda el ranking."""
            with app.app_context():
                try:
                    from app.services.whatsapp_jobs import send_ranking_diario
                    send_ranking_diario()
                except Exception as e:
                    logger.error(f"Error en whatsapp_ranking_job: {e}")

        def whatsapp_partidos_proximos_job():
            """Cada 15 min: avisa si algún partido empieza en <35 min."""
            with app.app_context():
                try:
                    from app.services.whatsapp_jobs import notify_partidos_proximos
                    notify_partidos_proximos()
                except Exception as e:
                    logger.error(f"Error en whatsapp_partidos_proximos_job: {e}")

        def whatsapp_resultados_job():
            """Cada 10 min: notifica resultados de partidos recién finalizados."""
            with app.app_context():
                try:
                    from app.services.whatsapp_jobs import notify_resultados_recientes
                    notify_resultados_recientes()
                except Exception as e:
                    logger.error(f"Error en whatsapp_resultados_job: {e}")

        scheduler.add_job(whatsapp_recordatorio_job, "interval", hours=1,
                          id="wa_recordatorio", replace_existing=True)
        scheduler.add_job(whatsapp_ranking_manana_job, "cron", hour=9, minute=0,
                          id="wa_ranking", replace_existing=True)
        scheduler.add_job(whatsapp_partidos_proximos_job, "interval", minutes=15,
                          id="wa_partidos_proximos", replace_existing=True)
        scheduler.add_job(whatsapp_resultados_job, "interval", minutes=10,
                          id="wa_resultados", replace_existing=True)
        logger.info("📱 Jobs de WhatsApp programados (group_jid configurado).")
    else:
        logger.info("📵 WhatsApp desactivado — configura WHATSAPP_GROUP_JID en .env")

    # Arrancar scheduler
    if not scheduler.running:
        scheduler.start()
