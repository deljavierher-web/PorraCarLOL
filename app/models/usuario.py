"""
PorraCarLOL — Modelo Usuario
"""
from datetime import datetime, timezone
from app.extensions import db, bcrypt


class Usuario(db.Model):
    """Modelo de usuario del sistema."""

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    es_administrador = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relación con predicciones
    predicciones = db.relationship(
        "Prediccion", backref="usuario", lazy="dynamic", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        """Hashea y almacena la contraseña con bcrypt."""
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Verifica la contraseña contra el hash almacenado."""
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        """Serializa el usuario (sin password_hash)."""
        return {
            "id": self.id,
            "username": self.username,
            "es_administrador": self.es_administrador,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Usuario {self.username}>"
