"""
PorraCarLOL — Rutas de API Pública
Rankings, pronósticos y datos de partidos.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import func

from app.extensions import db
from app.models.partido import Partido
from app.models.prediccion import Prediccion
from app.services.scoring_service import (
    get_ranking_general,
    get_ranking_jornada,
    get_jornadas_disponibles,
    get_ranking_evolucion,
    get_insignias,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ──────────────────────────────────────────────
# Jornadas y Partidos
# ──────────────────────────────────────────────


@api_bp.route("/jornadas", methods=["GET"])
def listar_jornadas():
    """Lista todas las jornadas disponibles con su estado."""
    jornadas = get_jornadas_disponibles()
    return jsonify({"jornadas": jornadas}), 200


def check_prev_jornadas_started(jornada: int) -> bool:
    """Verifica si todas las jornadas anteriores a la dada ya han comenzado."""
    for j in range(1, jornada):
        primer_partido = (
            Partido.query.filter_by(jornada=j)
            .order_by(Partido.fecha_partido.asc())
            .first()
        )
        if primer_partido and not primer_partido.ha_comenzado:
            return False
    return True


@api_bp.route("/partidos", methods=["GET"])
def listar_partidos():
    """Lista partidos, opcionalmente filtrados por jornada."""
    jornada = request.args.get("jornada", type=int)
    query = Partido.query

    if jornada is not None:
        query = query.filter_by(jornada=jornada)

    partidos = query.order_by(Partido.fecha_partido.asc()).all()

    # Calcular si esta jornada está abierta para predicciones
    abierta = True
    if jornada is not None:
        if jornada >= 4:
            abierta = False
        else:
            abierta = check_prev_jornadas_started(jornada)

    return jsonify({
        "partidos": [p.to_dict() for p in partidos],
        "abierta": abierta
    }), 200


# ──────────────────────────────────────────────
# Rankings
# ──────────────────────────────────────────────


@api_bp.route("/ranking/general", methods=["GET"])
def ranking_general():
    """Ranking general acumulado de todos los usuarios."""
    ranking = get_ranking_general()
    return jsonify({"ranking": ranking}), 200


@api_bp.route("/ranking/jornada/<int:jornada>", methods=["GET"])
def ranking_jornada(jornada: int):
    """Ranking de una jornada específica."""
    ranking = get_ranking_jornada(jornada)
    return jsonify({"ranking": ranking, "jornada": jornada}), 200


@api_bp.route("/ranking/evolucion", methods=["GET"])
@jwt_required()
def ranking_evolucion():
    """Evolución acumulada de puntos por usuario (para la gráfica del dashboard)."""
    return jsonify(get_ranking_evolucion()), 200


@api_bp.route("/insignias", methods=["GET"])
@jwt_required()
def insignias():
    """Insignias por usuario: rachas de aciertos y plenos de fase."""
    return jsonify({"insignias": get_insignias()}), 200


@api_bp.route("/mis-estadisticas", methods=["GET"])
@jwt_required()
def mis_estadisticas():
    """Obtiene las estadísticas de rendimiento del usuario logueado."""
    user_id = int(get_jwt_identity())
    
    # Obtener ranking general para posición y puntos totales
    ranking = get_ranking_general()
    user_rank_info = next((r for r in ranking if r["usuario_id"] == user_id), None)
    
    puntos_totales = user_rank_info["puntos_totales"] if user_rank_info else 0.0
    posicion = user_rank_info["posicion"] if user_rank_info else None
    
    # Calcular porcentaje de aciertos
    total_finalizados = (
        db.session.query(func.count(Prediccion.id))
        .join(Partido, Prediccion.partido_id == Partido.id)
        .filter(Prediccion.usuario_id == user_id, Partido.finalizado == True)
        .scalar()
        or 0
    )
    
    aciertos = (
        db.session.query(func.count(Prediccion.id))
        .join(Partido, Prediccion.partido_id == Partido.id)
        .filter(
            Prediccion.usuario_id == user_id,
            Partido.finalizado == True,
            Prediccion.pronostico == Partido.resultado_real,
        )
        .scalar()
        or 0
    )
    
    tasa_acierto = (aciertos / total_finalizados * 100) if total_finalizados > 0 else 0.0
    
    # Obtener mejor apuesta (mayor ganancia de puntos en partido finalizado)
    mejor_apuesta = (
        db.session.query(Prediccion, Partido)
        .join(Partido, Prediccion.partido_id == Partido.id)
        .filter(Prediccion.usuario_id == user_id, Partido.finalizado == True)
        .order_by(Prediccion.puntos_ganados.desc(), Partido.fecha_partido.desc())
        .first()
    )
    
    mejor_apuesta_data = None
    if mejor_apuesta:
        pred, partido = mejor_apuesta
        if pred.puntos_ganados > 0:
            mejor_apuesta_data = {
                "equipo_local": partido.equipo_local,
                "equipo_visitante": partido.equipo_visitante,
                "pronostico": pred.pronostico,
                "puntos_ganados": pred.puntos_ganados,
                "es_comodin": pred.es_comodin,
            }
            
    # Total de pronósticos bloqueados
    total_enviados = (
        db.session.query(func.count(Prediccion.id))
        .filter(Prediccion.usuario_id == user_id, Prediccion.enviado == True)
        .scalar()
        or 0
    )
    
    multiplicador_comodin = user_rank_info["multiplicador_comodin"] if user_rank_info else 2.0
    
    return jsonify({
        "puntos_totales": puntos_totales,
        "posicion": posicion,
        "total_finalizados": total_finalizados,
        "aciertos": aciertos,
        "tasa_acierto": round(tasa_acierto, 1),
        "mejor_apuesta": mejor_apuesta_data,
        "total_enviados": total_enviados,
        "multiplicador_comodin": multiplicador_comodin
    }), 200


@api_bp.route("/usuarios/<int:usuario_id>/pronosticos", methods=["GET"])
@jwt_required()
def pronosticos_usuario(usuario_id: int):
    """
    Obtiene los pronósticos de un usuario específico para una jornada.
    Solo revela la predicción si el partido ya comenzó.
    """
    jornada = request.args.get("jornada", type=int)
    if not jornada:
        return jsonify({"error": "El parámetro 'jornada' (fase) es obligatorio."}), 400

    from app.models.usuario import Usuario
    user = Usuario.query.get(usuario_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado."}), 404

    claims = get_jwt()
    es_admin = claims.get("es_admin", False)

    # Obtener todas las predicciones del usuario para esa jornada
    query = (
        db.session.query(Prediccion, Partido)
        .join(Partido, Prediccion.partido_id == Partido.id)
        .filter(Prediccion.usuario_id == usuario_id, Partido.jornada == jornada)
        .order_by(Partido.fecha_partido.asc())
    )
    results = query.all()

    current_user_id = int(get_jwt_identity())
    puede_ver = (current_user_id == usuario_id) or es_admin

    pronosticos = []
    for pred, partido in results:
        item = {
            "id": pred.id,
            "partido_id": pred.partido_id,
            "es_comodin": pred.es_comodin,
            "puntos_ganados": pred.puntos_ganados,
            "partido": partido.to_dict()
        }
        if partido.ha_comenzado or puede_ver:
            item["pronostico"] = pred.pronostico
        else:
            item["pronostico"] = "?"
        pronosticos.append(item)

    return jsonify({
        "username": user.username,
        "pronosticos": pronosticos
    }), 200


# ──────────────────────────────────────────────
# Pronósticos del Usuario
# ──────────────────────────────────────────────


@api_bp.route("/mis-pronosticos", methods=["GET"])
@jwt_required()
def mis_pronosticos():
    """
    Lista los pronósticos del usuario autenticado.
    Opcionalmente filtrados por jornada.
    """
    user_id = int(get_jwt_identity())
    jornada = request.args.get("jornada", type=int)

    query = (
        db.session.query(Prediccion, Partido)
        .join(Partido, Prediccion.partido_id == Partido.id)
        .filter(Prediccion.usuario_id == user_id)
    )

    if jornada is not None:
        query = query.filter(Partido.jornada == jornada)

    query = query.order_by(Partido.fecha_partido.asc())
    results = query.all()

    pronosticos = []
    for pred, partido in results:
        item = pred.to_dict()
        item["partido"] = partido.to_dict()
        pronosticos.append(item)

    from app.services.scoring_service import get_wildcard_multipliers_for_jornada, get_current_jornada
    jornada_calc = jornada if jornada is not None else get_current_jornada()
    multipliers = get_wildcard_multipliers_for_jornada(jornada_calc)
    user_multiplier = multipliers.get(user_id, 2.0)

    return jsonify({
        "pronosticos": pronosticos,
        "multiplicador_comodin": user_multiplier
    }), 200


@api_bp.route("/pronostico", methods=["POST"])
@jwt_required()
def crear_pronostico():
    """
    Crear o actualizar un pronóstico.
    Body: { partido_id, pronostico ("1"|"X"|"2") }
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    if claims.get("username") == "invitado":
        return jsonify({"error": "Acceso de invitado de solo lectura. No puedes modificar nada."}), 403

    data = request.get_json() or {}

    partido_id = data.get("partido_id")
    pronostico = data.get("pronostico", "").upper()

    # Validaciones
    if not partido_id or pronostico not in ("1", "X", "2"):
        return jsonify({"error": "partido_id y pronostico (1/X/2) son obligatorios."}), 400

    partido = Partido.query.get(partido_id)
    if not partido:
        return jsonify({"error": "Partido no encontrado."}), 404

    claims = get_jwt()
    es_admin = claims.get("es_admin", False)

    # Bloquear eliminatorias
    if partido.jornada >= 4 and not es_admin:
        return jsonify({"error": "Las eliminatorias (Fase 4 en adelante) están bloqueadas temporalmente."}), 403

    # Bloquear fases secuenciales si no ha comenzado la anterior
    if not check_prev_jornadas_started(partido.jornada) and not es_admin:
        return jsonify({"error": f"La Fase {partido.jornada} no está abierta. Debes esperar a que comience la Fase {partido.jornada - 1}."}), 403

    if partido.ha_comenzado:
        return jsonify({"error": "El partido ya ha comenzado. No puedes pronosticar."}), 403

    if partido.finalizado:
        return jsonify({"error": "El partido ya ha finalizado."}), 403

    # Crear o actualizar
    pred = Prediccion.query.filter_by(
        usuario_id=user_id, partido_id=partido_id
    ).first()

    if pred:
        if pred.enviado:
            return jsonify({"error": "Este pronóstico ya ha sido enviado y bloqueado. No puedes modificarlo."}), 403
        pred.pronostico = pronostico
        message = "Pronóstico actualizado."
    else:
        pred = Prediccion(
            usuario_id=user_id,
            partido_id=partido_id,
            pronostico=pronostico,
        )
        db.session.add(pred)
        message = "Pronóstico creado."

    db.session.commit()

    return jsonify({"message": message, "pronostico": pred.to_dict()}), 200


@api_bp.route("/pronosticos/enviar", methods=["POST"])
@jwt_required()
def enviar_pronosticos():
    """
    Bloquea y envía todos los pronósticos realizados para una jornada/fase.
    Body: { "jornada": N }
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    if claims.get("username") == "invitado":
        return jsonify({"error": "Acceso de invitado de solo lectura. No puedes modificar nada."}), 403

    data = request.get_json() or {}
    jornada = data.get("jornada")

    if not jornada:
        return jsonify({"error": "El parámetro 'jornada' (fase) es obligatorio."}), 400

    claims = get_jwt()
    es_admin = claims.get("es_admin", False)

    # Bloquear eliminatorias
    if jornada >= 4 and not es_admin:
        return jsonify({"error": "Las eliminatorias (Fase 4 en adelante) están bloqueadas temporalmente."}), 403

    # Bloquear fases secuenciales si no ha comenzado la anterior
    if not check_prev_jornadas_started(jornada) and not es_admin:
        return jsonify({"error": f"La Fase {jornada} no está abierta. Debes esperar a que comience la Fase {jornada - 1}."}), 403

    # Obtener todas las predicciones del usuario para los partidos de esa jornada
    predicciones = (
        db.session.query(Prediccion)
        .join(Partido, Prediccion.partido_id == Partido.id)
        .filter(
            Prediccion.usuario_id == user_id,
            Partido.jornada == jornada,
            Partido.finalizado == False,  # noqa: E712
        )
        .all()
    )

    if not predicciones:
        return jsonify({"error": "No tienes pronósticos guardados para enviar en esta fase."}), 400

    # Verificar si alguno ya está comenzado
    for pred in predicciones:
        partido = Partido.query.get(pred.partido_id)
        if partido and partido.ha_comenzado:
            return jsonify({"error": f"El partido {partido.equipo_local} vs {partido.equipo_visitante} ya ha comenzado. No puedes enviar pronósticos."}), 403

    # Marcar todos como enviados
    for pred in predicciones:
        pred.enviado = True

    db.session.commit()

    return jsonify({"message": "Tus pronósticos para esta fase han sido enviados y bloqueados con éxito."}), 200


@api_bp.route("/pronostico/<int:pred_id>/comodin", methods=["PUT"])
@jwt_required()
def toggle_comodin(pred_id: int):
    """
    Asignar/quitar comodín a un pronóstico.
    Solo 1 comodín por jornada por usuario.
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    if claims.get("username") == "invitado":
        return jsonify({"error": "Acceso de invitado de solo lectura. No puedes modificar nada."}), 403

    pred = Prediccion.query.get(pred_id)
    if not pred or pred.usuario_id != user_id:
        return jsonify({"error": "Pronóstico no encontrado."}), 404

    if pred.enviado:
        return jsonify({"error": "Este pronóstico ya ha sido enviado y bloqueado. No puedes cambiar el comodín."}), 403

    partido = Partido.query.get(pred.partido_id)
    if not partido:
        return jsonify({"error": "Partido asociado no encontrado."}), 404

    claims = get_jwt()
    es_admin = claims.get("es_admin", False)

    # Bloquear eliminatorias
    if partido.jornada >= 4 and not es_admin:
        return jsonify({"error": "Las eliminatorias (Fase 4 en adelante) están bloqueadas temporalmente."}), 403

    # Bloquear fases secuenciales si no ha comenzado la anterior
    if not check_prev_jornadas_started(partido.jornada) and not es_admin:
        return jsonify({"error": f"La Fase {partido.jornada} no está abierta. Debes esperar a que comience la Fase {partido.jornada - 1}."}), 403

    if partido.ha_comenzado:
        return jsonify({"error": "El partido ya ha comenzado. No puedes cambiar el comodín."}), 403

    jornada = partido.jornada

    if pred.es_comodin:
        # Quitar comodín
        pred.es_comodin = False
    else:
        # Quitar comodín anterior de la misma jornada (si existe)
        comodines_jornada = (
            db.session.query(Prediccion)
            .join(Partido, Prediccion.partido_id == Partido.id)
            .filter(
                Prediccion.usuario_id == user_id,
                Partido.jornada == jornada,
                Prediccion.es_comodin == True,  # noqa: E712
            )
            .all()
        )
        for c in comodines_jornada:
            c.es_comodin = False

        # Asignar nuevo comodín
        pred.es_comodin = True

    db.session.commit()

    return jsonify({
        "message": "Comodín " + ("asignado" if pred.es_comodin else "quitado") + ".",
        "pronostico": pred.to_dict(),
    }), 200


@api_bp.route("/pronosticos-partido/<int:partido_id>", methods=["GET"])
@jwt_required()
def pronosticos_partido(partido_id: int):
    """
    Ver pronósticos de todos los usuarios para un partido.
    Solo visible si el partido ya ha comenzado (para no revelar antes).
    """
    partido = Partido.query.get(partido_id)
    if not partido:
        return jsonify({"error": "Partido no encontrado."}), 404

    claims = get_jwt()
    es_admin = claims.get("es_admin", False)

    if not partido.ha_comenzado and not es_admin:
        return jsonify({"error": "Los pronósticos se revelan cuando empieza el partido."}), 403

    predicciones = Prediccion.query.filter_by(partido_id=partido_id).all()
    from app.models.usuario import Usuario

    result = []
    for pred in predicciones:
        user = Usuario.query.get(pred.usuario_id)
        item = pred.to_dict()
        item["username"] = user.username if user else "Desconocido"
        result.append(item)

    return jsonify({"pronosticos": result, "partido": partido.to_dict()}), 200


@api_bp.route("/equipos", methods=["GET"])
def listar_equipos():
    """Obtiene la lista única de equipos reales cargados en el sistema."""
    locals_q = db.session.query(Partido.equipo_local).distinct()
    aways_q = db.session.query(Partido.equipo_visitante).distinct()
    raw_equipos = list(set([r[0] for r in locals_q.all() + aways_q.all()]))
    
    keywords = ["Group", "Match", "Runner-up", "Winner", "3rd", "4th", "Pendiente"]
    equipos = sorted([e for e in raw_equipos if not any(k in e for k in keywords)])
    
    return jsonify({"equipos": equipos}), 200


def get_specials_time_window():
    from app.models.partido import Partido
    first_j1 = Partido.query.filter_by(jornada=1).order_by(Partido.fecha_partido.asc()).first()
    first_j2 = Partido.query.filter_by(jornada=2).order_by(Partido.fecha_partido.asc()).first()
    
    import datetime
    from datetime import timezone
    
    world_cup_start = first_j1.fecha_partido.replace(tzinfo=timezone.utc) if first_j1 else datetime.datetime(2026, 6, 11, 16, 0, 0, tzinfo=timezone.utc)
    jornada_2_start = first_j2.fecha_partido.replace(tzinfo=timezone.utc) if first_j2 else datetime.datetime(2026, 6, 18, 14, 0, 0, tzinfo=timezone.utc)
    return world_cup_start, jornada_2_start


@api_bp.route("/predicciones-especiales", methods=["GET"])
@jwt_required()
def obtener_predicciones_especiales():
    """Obtiene las predicciones especiales del usuario logueado."""
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    es_admin = claims.get("es_admin", False)

    from app.models.prediccion_especial import PrediccionEspecial
    preds = PrediccionEspecial.query.filter_by(usuario_id=user_id).all()
    preds_dict = {p.categoria: p.valor_pronosticado for p in preds}

    # Time window evaluation
    world_cup_start, j2_start = get_specials_time_window()
    import datetime
    from datetime import timezone
    now = datetime.datetime.now(timezone.utc)

    if now < world_cup_start:
        state = "locked"
    elif now < j2_start:
        state = "open"
    else:
        state = "closed"

    return jsonify({
        "predicciones": preds_dict,
        "state": state,
        "world_cup_start": world_cup_start.isoformat(),
        "jornada_2_start": j2_start.isoformat(),
        "now": now.isoformat()
    }), 200


@api_bp.route("/predicciones-especiales", methods=["POST"])
@jwt_required()
def guardar_predicciones_especiales():
    """Guarda o actualiza las predicciones especiales del usuario logueado."""
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    es_admin = claims.get("es_admin", False)

    # Time window evaluation for non-admins
    if not es_admin:
        world_cup_start, j2_start = get_specials_time_window()
        import datetime
        from datetime import timezone
        now = datetime.datetime.now(timezone.utc)

        if now < world_cup_start:
            return jsonify({"error": "La votación de pronósticos especiales aún está bloqueada."}), 403
        elif now >= j2_start:
            return jsonify({"error": "La votación de pronósticos especiales ya se ha cerrado."}), 403

    data = request.get_json() or {}
    
    # Validaciones de consistencia lógica
    campeon = data.get("campeon", "").strip()
    subcampeon = data.get("subcampeon", "").strip()
    semi1 = data.get("semifinalista_1", "").strip()
    semi2 = data.get("semifinalista_2", "").strip()
    semi3 = data.get("semifinalista_3", "").strip()
    semi4 = data.get("semifinalista_4", "").strip()

    if campeon and subcampeon and campeon == subcampeon:
        return jsonify({"error": "El campeón y el subcampeón no pueden ser el mismo equipo."}), 400
    if campeon and semi1 and campeon != semi1:
        return jsonify({"error": "El Semifinalista 1 debe ser el campeón seleccionado."}), 400
    if subcampeon and semi2 and subcampeon != semi2:
        return jsonify({"error": "El Semifinalista 2 debe ser el subcampeón seleccionado."}), 400
        
    semis_provided = [s for s in [semi1, semi2, semi3, semi4] if s]
    if len(semis_provided) != len(set(semis_provided)):
        return jsonify({"error": "No puede haber equipos duplicados entre los semifinalistas."}), 400

    if semi3:
        if campeon and semi3 == campeon:
            return jsonify({"error": "El Semifinalista 3 no puede ser el campeón."}), 400
        if subcampeon and semi3 == subcampeon:
            return jsonify({"error": "El Semifinalista 3 no puede ser el subcampeón."}), 400
    if semi4:
        if campeon and semi4 == campeon:
            return jsonify({"error": "El Semifinalista 4 no puede ser el campeón."}), 400
        if subcampeon and semi4 == subcampeon:
            return jsonify({"error": "El Semifinalista 4 no puede ser el subcampeón."}), 400

    from app.models.prediccion_especial import PrediccionEspecial

    valid_categories = [
        "campeon", "subcampeon", 
        "semifinalista_1", "semifinalista_2", "semifinalista_3", "semifinalista_4",
        "maximo_goleador", "equipo_mas_goleador"
    ]

    for cat in valid_categories:
        if cat in data:
            val = str(data[cat]).strip()
            if val:
                pred = PrediccionEspecial.query.filter_by(usuario_id=user_id, categoria=cat).first()
                if pred:
                    if not pred.evaluado:
                        pred.valor_pronosticado = val
                else:
                    pred = PrediccionEspecial(
                        usuario_id=user_id,
                        categoria=cat,
                        valor_pronosticado=val
                    )
                    db.session.add(pred)

    db.session.commit()
    return jsonify({"message": "Pronósticos especiales guardados correctamente."}), 200


# ──────────────────────────────────────────────
# Multiplicadores por Fase
# ──────────────────────────────────────────────


@api_bp.route("/multiplicadores", methods=["GET"])
def listar_multiplicadores():
    """Devuelve los multiplicadores de fase del torneo y sus nombres."""
    from flask import current_app
    multipliers = current_app.config.get("PHASE_MULTIPLIERS", {})
    names = current_app.config.get("PHASE_NAMES", {})

    phases = []
    for jornada in sorted(multipliers.keys()):
        phases.append({
            "jornada": jornada,
            "nombre": names.get(jornada, f"Jornada {jornada}"),
            "multiplicador": multipliers[jornada],
        })

    return jsonify({"fases": phases}), 200


# ──────────────────────────────────────────────
# Estadísticas Comunitarias de Especiales
# ──────────────────────────────────────────────


@api_bp.route("/predicciones-especiales/comunidad", methods=["GET"])
@jwt_required()
def obtener_especiales_comunidad():
    """
    Devuelve las predicciones especiales de todos los jugadores y estadísticas
    de qué opción ha sido la más votada por categoría.
    Solo accesible cuando el estado de especiales es 'closed' o para admins.
    """
    claims = get_jwt()
    es_admin = claims.get("es_admin", False)

    # Time window evaluation
    world_cup_start, j2_start = get_specials_time_window()
    import datetime
    from datetime import timezone
    now = datetime.datetime.now(timezone.utc)

    if now < j2_start and not es_admin:
        return jsonify({"error": "Las predicciones de la comunidad estarán disponibles cuando cierre el plazo de votación."}), 403

    from app.models.prediccion_especial import PrediccionEspecial
    from app.models.usuario import Usuario

    # Get all non-admin users who have predictions
    usuarios = Usuario.query.filter_by(es_administrador=False).all()
    user_map = {u.id: u.username for u in usuarios}

    preds = PrediccionEspecial.query.filter(
        PrediccionEspecial.usuario_id.in_(list(user_map.keys()))
    ).all()

    # Build per-user predictions
    user_predictions = {}
    for p in preds:
        uid = p.usuario_id
        if uid not in user_predictions:
            user_predictions[uid] = {
                "usuario_id": uid,
                "username": user_map.get(uid, "Desconocido"),
            }
        user_predictions[uid][p.categoria] = p.valor_pronosticado

    jugadores = sorted(user_predictions.values(), key=lambda x: x["username"].lower())

    # Build statistics: count votes per category
    categorias = [
        "campeon", "subcampeon",
        "semifinalista_1", "semifinalista_2", "semifinalista_3", "semifinalista_4",
        "maximo_goleador", "equipo_mas_goleador"
    ]

    # For semifinalistas, aggregate all 4 into one combined category for stats
    stats = {}
    for cat in ["campeon", "subcampeon", "maximo_goleador", "equipo_mas_goleador"]:
        vote_counts = {}
        for p in preds:
            if p.categoria == cat:
                val = p.valor_pronosticado.strip()
                vote_counts[val] = vote_counts.get(val, 0) + 1

        total_votes = sum(vote_counts.values())
        ranked = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        stats[cat] = {
            "total_votos": total_votes,
            "ranking": [
                {"valor": v, "votos": c, "porcentaje": round(c / total_votes * 100, 1) if total_votes else 0}
                for v, c in ranked
            ]
        }

    # Semifinalistas: aggregate all 4 slots into one combined pool
    semi_counts = {}
    total_semi_voters = 0
    semi_voter_ids = set()
    for p in preds:
        if p.categoria.startswith("semifinalista_"):
            val = p.valor_pronosticado.strip()
            semi_counts[val] = semi_counts.get(val, 0) + 1
            semi_voter_ids.add(p.usuario_id)
    total_semi_voters = len(semi_voter_ids)
    ranked_semis = sorted(semi_counts.items(), key=lambda x: x[1], reverse=True)
    stats["semifinalistas"] = {
        "total_votos": sum(semi_counts.values()),
        "total_votantes": total_semi_voters,
        "ranking": [
            {"valor": v, "votos": c, "porcentaje": round(c / (total_semi_voters * 4) * 100, 1) if total_semi_voters else 0}
            for v, c in ranked_semis
        ]
    }

    return jsonify({
        "jugadores": jugadores,
        "estadisticas": stats,
        "total_participantes": len(jugadores),
    }), 200
