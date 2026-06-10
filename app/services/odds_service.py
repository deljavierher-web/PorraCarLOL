"""
PorraCarLOL — Servicio de Cuotas (The Odds API)
Obtiene cuotas 1X2 de partidos próximos y los sincroniza con la BD.
"""
import logging
from datetime import datetime, timezone

import requests

from app.extensions import db
from app.models.partido import Partido

logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"


def fetch_upcoming_odds(api_key: str, sport_key: str, jornada: int | None = None) -> dict:
    """
    Obtiene cuotas de próximos partidos desde The Odds API.

    Args:
        api_key: API key de The Odds API.
        sport_key: Clave del deporte (ej: soccer_spain_la_liga).
        jornada: Número de jornada a asignar. Si None, auto-calcula.

    Returns:
        dict con 'created', 'updated', 'errors' y 'remaining_credits'.
    """
    if not api_key:
        logger.warning("ODDS_API_KEY no configurada. Saltando sync de cuotas.")
        return {"created": 0, "updated": 0, "errors": [], "remaining_credits": None}

    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error al obtener cuotas: {e}")
        return {"created": 0, "updated": 0, "errors": [str(e)], "remaining_credits": None}

    # Créditos restantes en headers
    remaining = response.headers.get("x-requests-remaining")
    events = response.json()

    # Auto-calcular jornada si no se especifica
    if jornada is None:
        last = db.session.query(db.func.max(Partido.jornada)).scalar()
        jornada = (last or 0) + 1

    created = 0
    updated = 0
    errors = []

    for event in events:
        try:
            match_id = event.get("id", "")
            home_team = event.get("home_team", "Desconocido")
            away_team = event.get("away_team", "Desconocido")
            commence = event.get("commence_time", "")

            # Parsear fecha
            fecha = datetime.fromisoformat(commence.replace("Z", "+00:00"))

            # Extraer cuotas del primer bookmaker
            cuota_1, cuota_x, cuota_2 = 1.0, 1.0, 1.0
            bookmakers = event.get("bookmakers", [])
            if bookmakers:
                markets = bookmakers[0].get("markets", [])
                for market in markets:
                    if market.get("key") == "h2h":
                        outcomes = market.get("outcomes", [])
                        for outcome in outcomes:
                            name = outcome.get("name", "")
                            price = float(outcome.get("price", 1.0))
                            if name == home_team:
                                cuota_1 = price
                            elif name == away_team:
                                cuota_2 = price
                            elif name.lower() == "draw":
                                cuota_x = price

            # Buscar si ya existe
            existing = Partido.query.filter_by(api_match_id=match_id).first()
            if existing:
                # Actualizar cuotas si el partido no ha empezado
                if not existing.ha_comenzado:
                    existing.cuota_1 = cuota_1
                    existing.cuota_x = cuota_x
                    existing.cuota_2 = cuota_2
                    updated += 1
            else:
                # Crear nuevo partido
                partido = Partido(
                    jornada=jornada,
                    equipo_local=home_team,
                    equipo_visitante=away_team,
                    cuota_1=cuota_1,
                    cuota_x=cuota_x,
                    cuota_2=cuota_2,
                    fecha_partido=fecha,
                    api_match_id=match_id,
                )
                db.session.add(partido)
                created += 1

        except Exception as e:
            errors.append(f"Error procesando evento: {e}")
            logger.error(f"Error procesando evento {event.get('id', '?')}: {e}")

    db.session.commit()
    logger.info(
        f"Sync cuotas completado: {created} creados, {updated} actualizados, "
        f"{len(errors)} errores. Créditos restantes: {remaining}"
    )

    return {
        "created": created,
        "updated": updated,
        "errors": errors,
        "remaining_credits": remaining,
    }
