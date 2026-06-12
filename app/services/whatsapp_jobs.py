"""
PorraCarLOL — Lógica de los jobs automáticos de WhatsApp
Cada función se llama desde APScheduler (ya tiene app_context inyectado).
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Evita enviar el mismo aviso dos veces en la misma ventana de tiempo
_notified_partidos: set[int] = set()   # IDs de partidos ya notificados (empieza en X min)
_notified_resultados: set[int] = set() # IDs de partidos cuyo resultado ya se notificó


def check_and_notify_pendientes():
    """
    Si hay una jornada abierta para apostar, busca quién no ha entregado
    y manda aviso si quedan 6h, 2h o 30min.
    """
    from app.models.partido import Partido
    from app.models.usuario import Usuario
    from app.models.prediccion import Prediccion
    from app.services.whatsapp_service import notify_recordatorio_jornada
    from app.extensions import db

    now = datetime.now(timezone.utc)

    # Busca el primer partido NO finalizado más próximo
    primer_partido = (
        Partido.query.filter(
            Partido.finalizado == False,
            Partido.fecha_partido > now
        )
        .order_by(Partido.fecha_partido.asc())
        .first()
    )

    if not primer_partido:
        return

    jornada = primer_partido.jornada
    fecha_cierre = primer_partido.fecha_partido.replace(tzinfo=timezone.utc)
    minutos_restantes = int((fecha_cierre - now).total_seconds() / 60)

    # Solo avisa en ventanas concretas (±10 min de margen)
    ventanas = [360, 120, 30]  # 6h, 2h, 30min
    en_ventana = any(abs(minutos_restantes - v) <= 10 for v in ventanas)
    if not en_ventana:
        return

    # Usuarios aprobados no-admin
    usuarios = Usuario.query.filter_by(aprobado=True, es_administrador=False).all()

    # Quién NO ha entregado ningún pronóstico de esta jornada
    partidos_jornada = Partido.query.filter_by(jornada=jornada).all()
    ids_jornada = {p.id for p in partidos_jornada}

    pendientes = []
    for u in usuarios:
        tiene = Prediccion.query.filter(
            Prediccion.usuario_id == u.id,
            Prediccion.partido_id.in_(ids_jornada)
        ).first()
        if not tiene:
            pendientes.append(u.username)

    if pendientes:
        notify_recordatorio_jornada(jornada, pendientes, minutos_restantes)


def send_ranking_diario():
    """Manda el ranking completo cada mañana a las 9:00."""
    from app.services.scoring_service import get_ranking
    from app.services.whatsapp_service import notify_ranking_diario

    try:
        ranking = get_ranking()
        if ranking:
            notify_ranking_diario(ranking)
    except Exception as e:
        logger.error(f"Error obteniendo ranking: {e}")


def notify_partidos_proximos():
    """Avisa si algún partido empieza en los próximos 30 minutos (una sola vez por partido)."""
    from app.models.partido import Partido
    from app.services.whatsapp_service import notify_partido_empieza

    now = datetime.now(timezone.utc)
    ventana_fin = now + timedelta(minutes=35)
    ventana_inicio = now + timedelta(minutes=25)

    proximos = Partido.query.filter(
        Partido.finalizado == False,
        Partido.fecha_partido >= ventana_inicio,
        Partido.fecha_partido <= ventana_fin,
    ).all()

    for p in proximos:
        if p.id not in _notified_partidos:
            _notified_partidos.add(p.id)
            fecha = p.fecha_partido.replace(tzinfo=timezone.utc)
            minutos = int((fecha - now).total_seconds() / 60)
            notify_partido_empieza(p.equipo_local, p.equipo_visitante, minutos)


def notify_resultados_recientes():
    """Notifica resultados de partidos finalizados en los últimos 20 minutos."""
    from app.models.partido import Partido
    from app.models.prediccion import Prediccion
    from app.models.usuario import Usuario
    from app.services.whatsapp_service import notify_resultado

    # No tenemos timestamp de cuándo se finalizó, así que buscamos partidos
    # cuya fecha_partido fue hace menos de 2h y están finalizados.
    now = datetime.now(timezone.utc)
    hace_dos_horas = now - timedelta(hours=2)

    recientes = Partido.query.filter(
        Partido.finalizado == True,
        Partido.fecha_partido >= hace_dos_horas,
        Partido.fecha_partido <= now,
    ).all()

    for p in recientes:
        if p.id in _notified_resultados:
            continue
        _notified_resultados.add(p.id)

        # Quién acertó y quién falló
        preds = Prediccion.query.filter_by(partido_id=p.id).all()
        acertaron, fallaron = [], []
        for pred in preds:
            u = Usuario.query.get(pred.usuario_id)
            if not u or u.es_administrador:
                continue
            if pred.pronostico == p.resultado_real:
                acertaron.append(u.username)
            else:
                fallaron.append(u.username)

        notify_resultado(p.equipo_local, p.equipo_visitante, p.resultado_real,
                         acertaron, fallaron)
