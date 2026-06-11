"""
PorraCarLOL — Rutas de Autenticación
Login, Registro, Logout y perfil del usuario actual.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)

from app.extensions import db, bcrypt
from app.models.usuario import Usuario

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Blocklist en memoria para tokens invalidados (en producción usar Redis)
BLOCKLIST = set()


@auth_bp.route("/register", methods=["POST"])
@jwt_required()
def register():
    """Registrar un nuevo usuario (Solo para Administrador)."""
    # Verificar permisos de administrador
    claims = get_jwt()
    if not claims.get("es_admin", False):
        return jsonify({"error": "Acceso denegado. Solo el administrador puede crear usuarios."}), 403

    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    # Validaciones
    if not username or not password:
        return jsonify({"error": "Username y password son obligatorios."}), 400

    if len(username) < 3 or len(username) > 30:
        return jsonify({"error": "Username debe tener entre 3 y 30 caracteres."}), 400

    if len(password) < 4:
        return jsonify({"error": "Password debe tener al menos 4 caracteres."}), 400

    if Usuario.query.filter_by(username=username).first():
        return jsonify({"error": "Ese username ya está en uso."}), 409

    # Crear usuario (creado por admin -> aprobado por defecto)
    usuario = Usuario(username=username, aprobado=True)
    usuario.set_password(password)
    db.session.add(usuario)
    db.session.commit()

    return jsonify({
        "message": f"Usuario '{username}' creado correctamente por el administrador.",
        "user": usuario.to_dict(),
    }), 201


@auth_bp.route("/signup", methods=["POST"])
def signup():
    """Permite que un nuevo jugador solicite registro público (pendiente de aprobación)."""
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    # Validaciones
    if not username or not password:
        return jsonify({"error": "Username y password son obligatorios."}), 400

    if len(username) < 3 or len(username) > 30:
        return jsonify({"error": "El nombre de usuario debe tener entre 3 y 30 caracteres."}), 400

    if len(password) < 4:
        return jsonify({"error": "La contraseña debe tener al menos 4 caracteres."}), 400

    if Usuario.query.filter_by(username=username).first():
        return jsonify({"error": "Ese nombre de usuario ya está registrado."}), 409

    # Crear usuario pendiente de aprobación (aprobado=False)
    usuario = Usuario(username=username, aprobado=False)
    usuario.set_password(password)
    db.session.add(usuario)
    db.session.commit()

    return jsonify({
        "message": "Solicitud de registro enviada. Tu cuenta debe ser aprobada por el administrador.",
        "user": usuario.to_dict(),
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Iniciar sesión y obtener JWT."""
    data = request.get_json() or {}

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username y password son obligatorios."}), 400

    usuario = Usuario.query.filter_by(username=username).first()
    if not usuario or not usuario.check_password(password):
        return jsonify({"error": "Credenciales incorrectas."}), 401

    # Verificar si el usuario está aprobado
    if not usuario.aprobado and not usuario.es_administrador:
        return jsonify({"error": "Tu cuenta está pendiente de aprobación por el administrador."}), 403

    token = create_access_token(
        identity=str(usuario.id),
        additional_claims={
            "username": usuario.username,
            "es_admin": usuario.es_administrador,
        },
    )

    return jsonify({
        "message": f"Bienvenido, {username}!",
        "token": token,
        "user": usuario.to_dict(),
    }), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """Invalidar el token actual."""
    jti = get_jwt()["jti"]
    BLOCKLIST.add(jti)
    return jsonify({"message": "Sesión cerrada correctamente."}), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """Obtener información del usuario autenticado."""
    user_id = int(get_jwt_identity())
    usuario = Usuario.query.get(user_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado."}), 404
    return jsonify({"user": usuario.to_dict()}), 200
