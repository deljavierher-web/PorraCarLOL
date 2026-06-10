"""
PorraCarLOL — Modelo Partido
"""
from datetime import datetime, timezone
from app.extensions import db


class Partido(db.Model):
    """Modelo de partido de fútbol."""

    __tablename__ = "partidos"

    id = db.Column(db.Integer, primary_key=True)
    jornada = db.Column(db.Integer, nullable=False, index=True)
    equipo_local = db.Column(db.String(100), nullable=False)
    equipo_visitante = db.Column(db.String(100), nullable=False)
    cuota_1 = db.Column(db.Float, nullable=False, default=1.0)
    cuota_x = db.Column(db.Float, nullable=False, default=1.0)
    cuota_2 = db.Column(db.Float, nullable=False, default=1.0)
    fecha_partido = db.Column(db.DateTime, nullable=False)
    resultado_real = db.Column(
        db.String(1), nullable=True
    )  # "1", "X", "2" o None
    finalizado = db.Column(db.Boolean, default=False, nullable=False)
    api_match_id = db.Column(
        db.String(100), nullable=True, unique=True, index=True
    )  # ID externo para sincronización

    # Relación con predicciones
    predicciones = db.relationship(
        "Prediccion", backref="partido", lazy="dynamic", cascade="all, delete-orphan"
    )

    @property
    def ha_comenzado(self) -> bool:
        """Devuelve True si la fecha del partido ya ha pasado."""
        return datetime.now(timezone.utc) >= self.fecha_partido.replace(
            tzinfo=timezone.utc
        )

    def to_dict(self) -> dict:
        """Serializa el partido."""
        return {
            "id": self.id,
            "jornada": self.jornada,
            "equipo_local": self.equipo_local,
            "equipo_visitante": self.equipo_visitante,
            "cuota_1": self.cuota_1,
            "cuota_x": self.cuota_x,
            "cuota_2": self.cuota_2,
            "fecha_partido": self.fecha_partido.replace(tzinfo=timezone.utc).isoformat()
            if self.fecha_partido
            else None,
            "resultado_real": self.resultado_real,
            "finalizado": self.finalizado,
            "ha_comenzado": self.ha_comenzado,
            "api_match_id": self.api_match_id,
        }

    def __repr__(self) -> str:
        return f"<Partido J{self.jornada}: {self.equipo_local} vs {self.equipo_visitante}>"
