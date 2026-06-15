"""
PorraCarLOL — Servicio de Puntuación
Motor de cálculo de puntos y generación de rankings.
"""
from sqlalchemy import func
from app.extensions import db
from app.models.partido import Partido
from app.models.prediccion import Prediccion
from app.models.usuario import Usuario


def get_ranking_at_jornada(max_jornada: int) -> list[dict]:
    """
    Devuelve el ranking general acumulado sumando solo puntos ganados en partidos
    de jornada <= max_jornada.
    """
    results = (
        db.session.query(
            Usuario.id,
            Usuario.username,
            func.coalesce(
                func.sum(
                    db.case(
                        (((Partido.jornada <= max_jornada) & (Prediccion.puntos_ganados != None)), Prediccion.puntos_ganados),
                        else_=0
                    )
                ),
                0
            ).label("total"),
            func.count(
                db.case(
                    (((Partido.jornada <= max_jornada) & (Prediccion.id != None)), Prediccion.id),
                    else_=None
                )
            ).label("num_pronosticos"),
        )
        .outerjoin(Prediccion, Usuario.id == Prediccion.usuario_id)
        .outerjoin(Partido, Prediccion.partido_id == Partido.id)
        .filter(Usuario.es_administrador == False)
        .group_by(Usuario.id, Usuario.username)
        .all()
    )

    ranking_data = []
    for row in results:
        ranking_data.append({
            "usuario_id": row.id,
            "username": row.username,
            "puntos_totales": round(float(row.total), 2),
            "num_pronosticos": row.num_pronosticos
        })

    ranking_data.sort(key=lambda x: x["puntos_totales"], reverse=True)

    for i, r in enumerate(ranking_data, 1):
        r["posicion"] = i

    return ranking_data


def calculate_wildcard_multipliers(ranking: list[dict]) -> dict[int, float]:
    """
    Calcula el multiplicador de comodín para cada usuario basado en un ranking dado.
    El líder recibe el multiplicador mínimo (2.0) y el último recibe el máximo (5.0).
    Los empates a puntos reciben exactamente el mismo rango y multiplicador.
    """
    from flask import current_app
    min_mult = current_app.config.get("COMODIN_MIN_MULTIPLIER", 2.0)
    max_mult = current_app.config.get("COMODIN_MAX_MULTIPLIER", 5.0)

    if not ranking:
        return {}

    n_players = len(ranking)
    if n_players <= 1:
        return {r["usuario_id"]: min_mult for r in ranking}

    sorted_ranking = sorted(ranking, key=lambda x: x["puntos_totales"], reverse=True)
    
    user_ranks = {}
    last_points = None
    last_rank = 1
    
    for idx, r in enumerate(sorted_ranking):
        points = r["puntos_totales"]
        if last_points is None:
            rank = 1
        elif points == last_points:
            rank = last_rank
        else:
            rank = idx + 1
            
        user_ranks[r["usuario_id"]] = rank
        last_points = points
        last_rank = rank

    multipliers = {}
    for user_id, rank in user_ranks.items():
        mult = min_mult + (rank - 1) * (max_mult - min_mult) / (n_players - 1)
        multipliers[user_id] = round(mult, 2)

    return multipliers


def get_wildcard_multipliers_for_jornada(jornada: int) -> dict[int, float]:
    """
    Calcula los multiplicadores del comodín para una jornada específica,
    basándose en el ranking consolidado al final de la jornada anterior (jornada - 1).
    Para la primera jornada, todos tienen el multiplicador base de 2.0.
    """
    from flask import current_app
    min_mult = current_app.config.get("COMODIN_MIN_MULTIPLIER", 2.0)
    
    if jornada <= 1:
        usuarios = Usuario.query.filter_by(es_administrador=False).all()
        return {u.id: min_mult for u in usuarios}
        
    ranking_previo = get_ranking_at_jornada(jornada - 1)
    return calculate_wildcard_multipliers(ranking_previo)


def get_current_jornada() -> int:
    """
    Retorna la primera jornada que no esté completamente finalizada,
    o la última jornada si todas están finalizadas.
    """
    jornadas = get_jornadas_disponibles()
    for j in jornadas:
        if not j["completada"]:
            return j["jornada"]
    return jornadas[-1]["jornada"] if jornadas else 1


def get_phase_multiplier(jornada: int) -> float:
    """
    Devuelve el multiplicador de fase para una jornada determinada.
    Las fases finales del torneo multiplican los puntos base para equilibrar
    la importancia entre la fase de grupos y las eliminatorias.
    """
    from flask import current_app
    multipliers = current_app.config.get("PHASE_MULTIPLIERS", {})
    return multipliers.get(jornada, 1)


def calculate_points(partido_id: int) -> int:
    """
    Evalúa todas las predicciones de un partido finalizado y asigna puntos.

    Sistema de puntuación estilo Bet365 Porra del Mundial:
    - Acierto: cuota_acertada × 10 × multiplicador_fase puntos
      Ejemplos (Grupos x1): cuota 1.10 → 11 pts | cuota 3.50 → 35 pts
      Ejemplos (Cuartos x5): cuota 2.50 → 125 pts
      Ejemplos (Final x10): cuota 2.50 → 250 pts
    - Fallo: 0 puntos
    - Comodín + acierto: puntos × multiplicador dinámico (según ranking de jornada anterior)

    Returns:
        Número de predicciones evaluadas.
    """
    partido = Partido.query.get(partido_id)
    if not partido or not partido.finalizado or not partido.resultado_real:
        return 0

    predicciones = Prediccion.query.filter_by(partido_id=partido_id).all()
    cuotas = {"1": partido.cuota_1, "X": partido.cuota_x, "2": partido.cuota_2}

    # Obtener multiplicadores aplicables para esta jornada
    wildcard_multipliers = get_wildcard_multipliers_for_jornada(partido.jornada)
    phase_mult = get_phase_multiplier(partido.jornada)

    for pred in predicciones:
        cuota_pick = cuotas.get(pred.pronostico, 1.0)
        base = cuota_pick * 10 * phase_mult
        if pred.pronostico == partido.resultado_real:
            puntos = base
            if pred.es_doble_mitad:
                # Doble o mitad: acierto = base x2 (excluyente con comodín)
                puntos = base * 2
            elif pred.es_comodin:
                mult = wildcard_multipliers.get(pred.usuario_id, 2.0)
                puntos *= mult
            pred.puntos_ganados = round(puntos, 2)
        else:
            if pred.es_doble_mitad and cuota_pick > 1.0:
                # Penalización EV-neutra: -base/(cuota-1). Cuanto más favorito el
                # pick fallado, mayor el castigo. Hace que usarlo sea neutro de media.
                pred.puntos_ganados = round(-(base / (cuota_pick - 1)), 2)
            else:
                pred.puntos_ganados = 0.0

    db.session.commit()
    return len(predicciones)


def get_ranking_general() -> list[dict]:
    """
    Ranking general: suma histórica de puntos de cada usuario (partidos + especiales).
    Devuelve lista ordenada de mayor a menor.
    """
    from app.models.prediccion_especial import PrediccionEspecial

    # Puntos por partidos
    results = (
        db.session.query(
            Usuario.id,
            Usuario.username,
            func.coalesce(func.sum(Prediccion.puntos_ganados), 0).label("total"),
            func.count(Prediccion.id).label("num_pronosticos"),
        )
        .outerjoin(Prediccion, Usuario.id == Prediccion.usuario_id)
        .filter(Usuario.es_administrador == False)  # noqa: E712
        .group_by(Usuario.id, Usuario.username)
        .all()
    )

    # Puntos por predicciones especiales
    especial_results = (
        db.session.query(
            Usuario.id,
            func.coalesce(func.sum(PrediccionEspecial.puntos_ganados), 0).label("especial_total")
        )
        .outerjoin(PrediccionEspecial, Usuario.id == PrediccionEspecial.usuario_id)
        .filter(Usuario.es_administrador == False)  # noqa: E712
        .group_by(Usuario.id)
        .all()
    )

    especial_map = {row.id: float(row.especial_total) for row in especial_results}

    ranking = []
    for row in results:
        puntos_partidos = float(row.total)
        puntos_especiales = especial_map.get(row.id, 0.0)
        puntos_totales = puntos_partidos + puntos_especiales

        ranking.append(
            {
                "usuario_id": row.id,
                "username": row.username,
                "puntos_totales": round(puntos_totales, 2),
                "puntos_partidos": round(puntos_partidos, 2),
                "puntos_especiales": round(puntos_especiales, 2),
                "num_pronosticos": row.num_pronosticos,
            }
        )

    # Ordenar ranking por puntos totales
    ranking.sort(key=lambda x: x["puntos_totales"], reverse=True)

    # Asignar posición
    for i, item in enumerate(ranking, 1):
        item["posicion"] = i

    # Inyectar multiplicador de comodín para la jornada activa actual
    try:
        active_jornada = get_current_jornada()
        multipliers = get_wildcard_multipliers_for_jornada(active_jornada)
        for item in ranking:
            item["multiplicador_comodin"] = multipliers.get(item["usuario_id"], 2.0)
    except Exception as e:
        # Fallback de seguridad
        for item in ranking:
            item["multiplicador_comodin"] = 2.0

    return ranking


def get_ranking_jornada(jornada: int) -> list[dict]:
    """
    Ranking de una jornada específica: suma de puntos filtrada por jornada.
    """
    results = (
        db.session.query(
            Usuario.id,
            Usuario.username,
            func.coalesce(func.sum(Prediccion.puntos_ganados), 0).label("total"),
            func.count(Prediccion.id).label("num_pronosticos"),
        )
        .join(Prediccion, Usuario.id == Prediccion.usuario_id)
        .join(Partido, Prediccion.partido_id == Partido.id)
        .filter(Partido.jornada == jornada)
        .filter(Usuario.es_administrador == False)  # noqa: E712
        .group_by(Usuario.id, Usuario.username)
        .order_by(func.sum(Prediccion.puntos_ganados).desc())
        .all()
    )

    ranking = []
    for i, row in enumerate(results, 1):
        ranking.append(
            {
                "posicion": i,
                "usuario_id": row.id,
                "username": row.username,
                "puntos_totales": round(float(row.total), 2),
                "num_pronosticos": row.num_pronosticos,
            }
        )
    return ranking


def get_ranking_evolucion() -> dict:
    """
    Evolución acumulada de puntos por usuario a lo largo de los partidos finalizados.
    Devuelve labels (días con partidos finalizados) y una serie acumulada por usuario.
    """
    usuarios = Usuario.query.filter_by(es_administrador=False).order_by(Usuario.username).all()
    usuarios = [u for u in usuarios if u.username != "invitado"]

    # Predicciones de partidos finalizados, ordenadas por fecha del partido
    rows = (
        db.session.query(Prediccion.usuario_id, Prediccion.puntos_ganados, Partido.fecha_partido)
        .join(Partido, Prediccion.partido_id == Partido.id)
        .filter(Partido.finalizado == True)  # noqa: E712
        .order_by(Partido.fecha_partido.asc())
        .all()
    )

    # Agrupar por día
    dias = []
    puntos_por_dia: dict[str, dict[int, float]] = {}
    for usuario_id, puntos, fecha in rows:
        dia = fecha.strftime("%d/%m")
        if dia not in puntos_por_dia:
            puntos_por_dia[dia] = {}
            dias.append(dia)
        puntos_por_dia[dia][usuario_id] = puntos_por_dia[dia].get(usuario_id, 0.0) + (puntos or 0.0)

    series = []
    for u in usuarios:
        acumulado = 0.0
        data = []
        for dia in dias:
            acumulado += puntos_por_dia[dia].get(u.id, 0.0)
            data.append(round(acumulado, 2))
        series.append({"usuario_id": u.id, "username": u.username, "data": data})

    return {"labels": dias, "series": series}


def get_insignias() -> dict:
    """
    Calcula insignias por usuario:
    - racha_actual: aciertos consecutivos contando desde el último partido finalizado hacia atrás.
    - mejor_racha: mayor racha histórica de aciertos consecutivos.
    - plenos: nº de fases completadas donde acertó todos los partidos (habiéndolos pronosticado todos).
    """
    usuarios = Usuario.query.filter_by(es_administrador=False).all()
    usuarios = [u for u in usuarios if u.username != "invitado"]

    # Partidos por jornada (solo los finalizados cuentan para plenos)
    jornadas = get_jornadas_disponibles()
    completadas = {j["jornada"]: j["total_partidos"] for j in jornadas if j["completada"]}

    resultado = {}
    for u in usuarios:
        rows = (
            db.session.query(Prediccion.pronostico, Partido.resultado_real, Partido.jornada)
            .join(Partido, Prediccion.partido_id == Partido.id)
            .filter(
                Prediccion.usuario_id == u.id,
                Partido.finalizado == True,  # noqa: E712
            )
            .order_by(Partido.fecha_partido.asc())
            .all()
        )

        # Rachas
        racha_actual = 0
        mejor_racha = 0
        racha = 0
        for pronostico, real, _ in rows:
            if pronostico == real:
                racha += 1
                mejor_racha = max(mejor_racha, racha)
            else:
                racha = 0
        # racha_actual: desde el final hacia atrás
        for pronostico, real, _ in reversed(rows):
            if pronostico == real:
                racha_actual += 1
            else:
                break

        # Plenos por fase completada
        plenos = []
        aciertos_por_jornada: dict[int, int] = {}
        pred_por_jornada: dict[int, int] = {}
        for pronostico, real, jornada in rows:
            pred_por_jornada[jornada] = pred_por_jornada.get(jornada, 0) + 1
            if pronostico == real:
                aciertos_por_jornada[jornada] = aciertos_por_jornada.get(jornada, 0) + 1
        for jornada, total in completadas.items():
            if (
                pred_por_jornada.get(jornada, 0) == total
                and aciertos_por_jornada.get(jornada, 0) == total
            ):
                plenos.append(jornada)

        resultado[u.id] = {
            "racha_actual": racha_actual,
            "mejor_racha": mejor_racha,
            "plenos": plenos,
        }

    return resultado


def get_jornadas_disponibles() -> list[dict]:
    """
    Devuelve la lista de jornadas con su estado (partidos totales / finalizados).
    """
    results = (
        db.session.query(
            Partido.jornada,
            func.count(Partido.id).label("total_partidos"),
            func.sum(db.case((Partido.finalizado == True, 1), else_=0)).label(  # noqa: E712
                "finalizados"
            ),
            func.min(Partido.fecha_partido).label("fecha_inicio"),
        )
        .group_by(Partido.jornada)
        .order_by(Partido.jornada.asc())
        .all()
    )

    jornadas = []
    for row in results:
        jornadas.append(
            {
                "jornada": row.jornada,
                "total_partidos": row.total_partidos,
                "finalizados": int(row.finalizados),
                "fecha_inicio": row.fecha_inicio.isoformat()
                if row.fecha_inicio
                else None,
                "completada": int(row.finalizados) == row.total_partidos,
            }
        )
    return jornadas
