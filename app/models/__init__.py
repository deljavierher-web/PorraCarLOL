"""
PorraCarLOL — Modelos
Exporta todos los modelos para facilitar el import.
"""
from app.models.usuario import Usuario
from app.models.partido import Partido
from app.models.prediccion import Prediccion
from app.models.prediccion_especial import PrediccionEspecial

__all__ = ["Usuario", "Partido", "Prediccion", "PrediccionEspecial"]
