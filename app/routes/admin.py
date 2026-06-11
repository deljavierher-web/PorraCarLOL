"""
PorraCarLOL — Rutas de Administración
CRUD de partidos, sync manual de APIs, y gestión de usuarios.
"""
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt

from app.extensions import db
from app.models.partido import Partido
from app.models.prediccion import Prediccion
from app.models.usuario import Usuario
from app.services.scoring_service import calculate_points
from app.services.odds_service import fetch_upcoming_odds
from app.services.results_service import check_finished_matches

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def admin_required(fn):
    """Decorador que verifica que el usuario sea administrador."""
    from functools import wraps

    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt()
        if not claims.get("es_admin", False):
            return jsonify({"error": "Acceso denegado. Se requieren permisos de administrador."}), 403
        return fn(*args, **kwargs)

    return wrapper


# ──────────────────────────────────────────────
# CRUD Partidos
# ──────────────────────────────────────────────


@admin_bp.route("/partidos", methods=["GET"])
@admin_required
def listar_partidos():
    """Lista todos los partidos (admin view con más detalle)."""
    partidos = Partido.query.order_by(Partido.jornada.desc(), Partido.fecha_partido.asc()).all()
    result = []
    for p in partidos:
        data = p.to_dict()
        data["num_predicciones"] = Prediccion.query.filter_by(partido_id=p.id).count()
        result.append(data)
    return jsonify({"partidos": result}), 200


@admin_bp.route("/partidos", methods=["POST"])
@admin_required
def crear_partido():
    """Crear un partido manualmente."""
    data = request.get_json() or {}

    required = ["jornada", "equipo_local", "equipo_visitante", "fecha_partido"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Campo '{field}' es obligatorio."}), 400

    try:
        fecha = datetime.fromisoformat(data["fecha_partido"])
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Usa ISO 8601."}), 400

    partido = Partido(
        jornada=int(data["jornada"]),
        equipo_local=data["equipo_local"].strip(),
        equipo_visitante=data["equipo_visitante"].strip(),
        cuota_1=float(data.get("cuota_1", 2.0)),
        cuota_x=float(data.get("cuota_x", 3.0)),
        cuota_2=float(data.get("cuota_2", 2.5)),
        fecha_partido=fecha,
    )
    db.session.add(partido)
    db.session.commit()

    return jsonify({"message": "Partido creado.", "partido": partido.to_dict()}), 201


@admin_bp.route("/partidos/<int:partido_id>", methods=["PUT"])
@admin_required
def editar_partido(partido_id: int):
    """Editar un partido existente."""
    partido = Partido.query.get(partido_id)
    if not partido:
        return jsonify({"error": "Partido no encontrado."}), 404

    data = request.get_json() or {}

    if "jornada" in data:
        partido.jornada = int(data["jornada"])
    if "equipo_local" in data:
        partido.equipo_local = data["equipo_local"].strip()
    if "equipo_visitante" in data:
        partido.equipo_visitante = data["equipo_visitante"].strip()
    if "cuota_1" in data:
        partido.cuota_1 = float(data["cuota_1"])
    if "cuota_x" in data:
        partido.cuota_x = float(data["cuota_x"])
    if "cuota_2" in data:
        partido.cuota_2 = float(data["cuota_2"])
    if "fecha_partido" in data:
        try:
            fecha = datetime.fromisoformat(data["fecha_partido"])
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            partido.fecha_partido = fecha
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido."}), 400
    if "resultado_real" in data:
        val = data["resultado_real"]
        if val and val not in ("1", "X", "2"):
            return jsonify({"error": "resultado_real debe ser '1', 'X' o '2'."}), 400
        partido.resultado_real = val

    db.session.commit()
    return jsonify({"message": "Partido actualizado.", "partido": partido.to_dict()}), 200


@admin_bp.route("/partidos/<int:partido_id>", methods=["DELETE"])
@admin_required
def eliminar_partido(partido_id: int):
    """Eliminar un partido y sus predicciones asociadas."""
    partido = Partido.query.get(partido_id)
    if not partido:
        return jsonify({"error": "Partido no encontrado."}), 404

    db.session.delete(partido)
    db.session.commit()
    return jsonify({"message": "Partido eliminado."}), 200


@admin_bp.route("/partidos/<int:partido_id>/finalizar", methods=["POST"])
@admin_required
def finalizar_partido(partido_id: int):
    """Forzar la finalización de un partido y calcular puntos."""
    partido = Partido.query.get(partido_id)
    if not partido:
        return jsonify({"error": "Partido no encontrado."}), 404

    data = request.get_json() or {}
    resultado = data.get("resultado_real", partido.resultado_real)

    if not resultado or resultado not in ("1", "X", "2"):
        return jsonify({"error": "Debes indicar resultado_real ('1', 'X' o '2')."}), 400

    partido.resultado_real = resultado
    partido.finalizado = True
    db.session.flush()

    n = calculate_points(partido.id)

    return jsonify({
        "message": f"Partido finalizado. {n} predicciones evaluadas.",
        "partido": partido.to_dict(),
    }), 200


# ──────────────────────────────────────────────
# Sync Manual con APIs
# ──────────────────────────────────────────────


@admin_bp.route("/sync-cuotas", methods=["POST"])
@admin_required
def sync_cuotas():
    """Trigger manual de sincronización de cuotas."""
    data = request.get_json() or {}
    jornada = data.get("jornada")

    api_key = current_app.config.get("ODDS_API_KEY")
    if not api_key:
        # Fallback al sync gratuito del Mundial
        from app.services.worldcup_sync_service import sync_worldcup_data
        res = sync_worldcup_data()
        return jsonify({
            "created": res.get("created", 0),
            "updated": res.get("updated", 0),
            "remaining_credits": "N/A (Keyless)",
            "message": "Sincronizado vía API pública del Mundial."
        }), 200

    result = fetch_upcoming_odds(
        api_key=api_key,
        sport_key=current_app.config["SPORT_KEY"],
        jornada=jornada,
    )
    return jsonify(result), 200


@admin_bp.route("/sync-resultados", methods=["POST"])
@admin_required
def sync_resultados():
    """Trigger manual de sincronización de resultados."""
    api_key = current_app.config.get("FOOTBALL_API_KEY")
    if not api_key:
        # Fallback al sync gratuito del Mundial
        from app.services.worldcup_sync_service import sync_worldcup_data
        res = sync_worldcup_data()
        return jsonify({
            "updated": res.get("updated", 0),
            "scored": res.get("scored", 0),
            "message": "Resultados y puntuaciones actualizados vía API pública."
        }), 200

    result = check_finished_matches(
        api_key=api_key,
        league_id=current_app.config["FOOTBALL_LEAGUE_ID"],
        season=current_app.config["FOOTBALL_SEASON"],
    )
    return jsonify(result), 200


# ──────────────────────────────────────────────
# Gestión de Usuarios
# ──────────────────────────────────────────────


@admin_bp.route("/usuarios", methods=["GET"])
@admin_required
def listar_usuarios():
    """Lista todos los usuarios registrados."""
    usuarios = Usuario.query.order_by(Usuario.created_at.desc()).all()
    return jsonify({"usuarios": [u.to_dict() for u in usuarios]}), 200


@admin_bp.route("/usuarios/<int:usuario_id>", methods=["DELETE"])
@admin_required
def eliminar_usuario(usuario_id: int):
    """Eliminar un usuario y todas sus predicciones."""
    usuario = Usuario.query.get(usuario_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado."}), 404

    if usuario.es_administrador:
        return jsonify({"error": "No puedes eliminar al administrador."}), 403

    username = usuario.username
    db.session.delete(usuario)
    db.session.commit()
    return jsonify({"message": f"Usuario '{username}' eliminado correctamente."}), 200
@admin_bp.route("/usuarios/<int:usuario_id>/aprobar", methods=["POST"])
@admin_required
def aprobar_usuario(usuario_id: int):
    """Aprobar un usuario registrado."""
    usuario = Usuario.query.get(usuario_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado."}), 404

    usuario.aprobado = True
    db.session.commit()
    return jsonify({"message": f"Usuario '{usuario.username}' aprobado correctamente."}), 200


@admin_bp.route("/evaluar-especiales", methods=["POST"])
@admin_required
def evaluar_especiales():
    """Evalúa todos los pronósticos especiales guardados en el sistema."""
    data = request.get_json() or {}
    
    campeon = data.get("campeon", "").strip()
    subcampeon = data.get("subcampeon", "").strip()
    semifinalistas = [s.strip() for s in data.get("semifinalistas", []) if s.strip()]
    maximo_goleador = data.get("maximo_goleador", "").strip().lower()
    equipo_mas_goleador = data.get("equipo_mas_goleador", "").strip()

    if not campeon or not subcampeon:
        return jsonify({"error": "Debes especificar el campeón y el subcampeón."}), 400
    if campeon == subcampeon:
        return jsonify({"error": "El campeón y el subcampeón no pueden ser el mismo equipo."}), 400
    if len(semifinalistas) != 4:
        return jsonify({"error": "Debes proporcionar exactamente 4 semifinalistas."}), 400
    if semifinalistas[0] != campeon:
        return jsonify({"error": "El primer semifinalista debe ser el campeón."}), 400
    if semifinalistas[1] != subcampeon:
        return jsonify({"error": "El segundo semifinalista debe ser el subcampeón."}), 400
    if len(set(semifinalistas)) != 4:
        return jsonify({"error": "No puede haber equipos duplicados entre los semifinalistas."}), 400

    from app.models.prediccion_especial import PrediccionEspecial
    preds = PrediccionEspecial.query.all()

    evaluated_count = 0
    for p in preds:
        points = 0.0
        val = p.valor_pronosticado.strip()
        
        if p.categoria == "campeon":
            if val == campeon:
                points = 450.0
        elif p.categoria == "subcampeon":
            if val == subcampeon:
                points = 300.0
        elif p.categoria in ("semifinalista_1", "semifinalista_2", "semifinalista_3", "semifinalista_4"):
            if val in semifinalistas:
                points = 150.0
        elif p.categoria == "maximo_goleador":
            if val.lower() == maximo_goleador:
                points = 300.0
        elif p.categoria == "equipo_mas_goleador":
            if val == equipo_mas_goleador:
                points = 300.0
        
        p.puntos_ganados = points
        p.evaluado = True
        evaluated_count += 1

    db.session.commit()
    return jsonify({
        "message": f"Evaluación completada. {evaluated_count} pronósticos especiales procesados.",
        "evaluated_count": evaluated_count
    }), 200
