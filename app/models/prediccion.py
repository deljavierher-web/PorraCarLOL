"""
PorraCarLOL — Modelo Predicción
"""
from datetime import datetime, timezone
from app.extensions import db


class Prediccion(db.Model):
    """Modelo de pronóstico de un usuario sobre un partido."""

    __tablename__ = "predicciones"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    partido_id = db.Column(
        db.Integer, db.ForeignKey("partidos.id"), nullable=False, index=True
    )
    pronostico = db.Column(db.String(1), nullable=False)  # "1", "X", "2"
    es_comodin = db.Column(db.Boolean, default=False, nullable=False)
    # "Doble o mitad": acierto x2; fallo resta base/(cuota-1) (penalización EV-neutra).
    # Excluyente con el comodín en el mismo partido; 1 por jornada.
    es_doble_mitad = db.Column(db.Boolean, default=False, nullable=False)
    puntos_ganados = db.Column(db.Float, default=0.0, nullable=False)
    enviado = db.Column(db.Boolean, default=False, nullable=False)
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Constraint: un usuario solo puede tener un pronóstico por partido
    __table_args__ = (
        db.UniqueConstraint("usuario_id", "partido_id", name="uq_usuario_partido"),
    )

    def to_dict(self) -> dict:
        """Serializa la predicción."""
        return {
            "id": self.id,
            "usuario_id": self.usuario_id,
            "partido_id": self.partido_id,
            "pronostico": self.pronostico,
            "es_comodin": self.es_comodin,
            "es_doble_mitad": self.es_doble_mitad,
            "puntos_ganados": self.puntos_ganados,
            "enviado": self.enviado,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self) -> str:
        comodin = " 🃏" if self.es_comodin else ""
        return f"<Prediccion U{self.usuario_id} P{self.partido_id}: {self.pronostico}{comodin}>"
