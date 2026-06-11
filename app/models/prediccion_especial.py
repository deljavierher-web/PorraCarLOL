"""
PorraCarLOL — Modelo Predicción Especial (Largo Plazo)
"""
from datetime import datetime, timezone
from app.extensions import db


class PrediccionEspecial(db.Model):
    """Modelo de pronóstico a largo plazo del torneo (ganador, goleador, etc.)."""

    __tablename__ = "predicciones_especiales"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    categoria = db.Column(
        db.String(50), nullable=False
    )  # campeon, subcampeon, semifinalista_1, semifinalista_2, etc.
    valor_pronosticado = db.Column(
        db.String(100), nullable=False
    )  # Nombre del equipo o jugador
    puntos_ganados = db.Column(db.Float, default=0.0, nullable=False)
    evaluado = db.Column(db.Boolean, default=False, nullable=False)
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Constraint: un usuario solo puede tener un pronóstico por categoría especial
    __table_args__ = (
        db.UniqueConstraint("usuario_id", "categoria", name="uq_usuario_categoria"),
    )

    def to_dict(self) -> dict:
        """Serializa la predicción especial."""
        return {
            "id": self.id,
            "usuario_id": self.usuario_id,
            "categoria": self.categoria,
            "valor_pronosticado": self.valor_pronosticado,
            "puntos_ganados": self.puntos_ganados,
            "evaluado": self.evaluado,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self) -> str:
        return f"<PrediccionEspecial U{self.usuario_id} {self.categoria}: {self.valor_pronosticado}>"
