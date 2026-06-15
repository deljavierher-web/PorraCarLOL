"""
PorraCarLOL — Lógica de los jobs automáticos de WhatsApp
Cada función se llama desde APScheduler (ya tiene app_context inyectado).
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Evita enviar el mismo aviso "empieza en X min" dos veces (dedup en memoria;
# los resultados usan la marca persistente Partido.resultado_notificado)
_notified_partidos: set[int] = set()


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
    from app.services.scoring_service import get_ranking_general
    from app.services.whatsapp_service import notify_ranking_diario

    try:
        ranking = get_ranking_general()
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
    """
    Notifica el resultado de partidos finalizados que aún no se han avisado.
    Usa la marca persistente `resultado_notificado` (no una ventana de tiempo),
    así que funciona aunque el partido se finalice horas después del inicio
    y sobrevive a reinicios del servidor.
    """
    from app.models.partido import Partido
    from app.models.prediccion import Prediccion
    from app.models.usuario import Usuario
    from app.services.whatsapp_service import notify_resultado
    from app.extensions import db

    pendientes = (
        Partido.query.filter(
            Partido.finalizado == True,
            Partido.resultado_notificado == False,
            Partido.resultado_real.isnot(None),
        )
        .order_by(Partido.fecha_partido.asc())
        .all()
    )

    for p in pendientes:
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

        # Rachas tras este partido (jugadores con 3+ aciertos seguidos)
        rachas = _calcular_rachas(minimo=3)

        enviado = notify_resultado(
            p.equipo_local, p.equipo_visitante, p.resultado_real,
            acertaron, fallaron, rachas=rachas,
        )

        # Marca persistente solo si el envío fue OK (si el bridge está caído,
        # se reintentará en la siguiente pasada)
        if enviado:
            p.resultado_notificado = True
            db.session.commit()


def _calcular_rachas(minimo: int = 3) -> list[tuple[str, int]]:
    """
    Devuelve [(username, longitud_racha), ...] de jugadores que llevan
    `minimo` o más aciertos consecutivos en sus últimos partidos finalizados.
    Ordenado de racha más larga a más corta.
    """
    from app.models.partido import Partido
    from app.models.prediccion import Prediccion
    from app.models.usuario import Usuario

    # Partidos finalizados en orden cronológico (más reciente primero)
    finalizados = (
        Partido.query.filter(
            Partido.finalizado == True,
            Partido.resultado_real.isnot(None),
        )
        .order_by(Partido.fecha_partido.desc())
        .all()
    )

    rachas = []
    for u in Usuario.query.filter_by(es_administrador=False, aprobado=True).all():
        racha = 0
        for p in finalizados:
            pred = Prediccion.query.filter_by(usuario_id=u.id, partido_id=p.id).first()
            if not pred:
                continue  # no apostó ese partido: no rompe la racha, lo salta
            if pred.pronostico == p.resultado_real:
                racha += 1
            else:
                break  # falló: racha actual cortada
        if racha >= minimo:
            rachas.append((u.username, racha))

    rachas.sort(key=lambda x: x[1], reverse=True)
    return rachas
