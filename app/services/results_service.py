"""
PorraCarLOL — Servicio de Resultados (API-Football via RapidAPI)
Verifica partidos finalizados y registra resultados automáticamente.
"""
import logging

import requests

from app.extensions import db
from app.models.partido import Partido
from app.services.scoring_service import calculate_points

logger = logging.getLogger(__name__)

FOOTBALL_API_BASE = "https://v3.football.api-sports.io"


def check_finished_matches(api_key: str, league_id: int, season: int) -> dict:
    """
    Consulta API-Football para detectar partidos finalizados y registrar resultados.

    Args:
        api_key: API key de RapidAPI para API-Football.
        league_id: ID de la liga (ej: 140 para La Liga).
        season: Temporada (ej: 2025).

    Returns:
        dict con 'updated', 'scored' y 'errors'.
    """
    if not api_key:
        logger.warning("FOOTBALL_API_KEY no configurada. Saltando sync de resultados.")
        return {"updated": 0, "scored": 0, "errors": []}

    # Obtener partidos no finalizados de la BD que ya han comenzado
    partidos_pendientes = Partido.query.filter(
        Partido.finalizado == False,  # noqa: E712
        Partido.resultado_real.is_(None),
    ).all()

    if not partidos_pendientes:
        logger.info("No hay partidos pendientes de resultado.")
        return {"updated": 0, "scored": 0, "errors": []}

    # Consultar API-Football por partidos finalizados
    headers = {
        "x-apisports-key": api_key,
    }
    params = {
        "league": league_id,
        "season": season,
        "status": "FT",  # Full Time
    }

    try:
        response = requests.get(
            f"{FOOTBALL_API_BASE}/fixtures", headers=headers, params=params, timeout=30
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        logger.error(f"Error al consultar API-Football: {e}")
        return {"updated": 0, "scored": 0, "errors": [str(e)]}

    fixtures = data.get("response", [])
    updated = 0
    scored = 0
    errors = []

    # Crear mapa de partidos pendientes por nombre de equipos (normalizado)
    pendientes_map = {}
    for p in partidos_pendientes:
        key = _normalize_teams(p.equipo_local, p.equipo_visitante)
        pendientes_map[key] = p
        # También mapear por api_match_id si existe
        if p.api_match_id:
            pendientes_map[f"id:{p.api_match_id}"] = p

    for fixture in fixtures:
        try:
            teams = fixture.get("teams", {})
            goals = fixture.get("goals", {})
            fixture_id = str(fixture.get("fixture", {}).get("id", ""))

            home_name = teams.get("home", {}).get("name", "")
            away_name = teams.get("away", {}).get("name", "")
            home_goals = goals.get("home", 0) or 0
            away_goals = goals.get("away", 0) or 0

            # Determinar resultado 1X2
            if home_goals > away_goals:
                resultado = "1"
            elif home_goals == away_goals:
                resultado = "X"
            else:
                resultado = "2"

            # Buscar partido en nuestra BD
            key = _normalize_teams(home_name, away_name)
            partido = pendientes_map.get(key) or pendientes_map.get(f"id:{fixture_id}")

            if partido:
                partido.resultado_real = resultado
                partido.finalizado = True
                db.session.flush()

                # Calcular puntos inmediatamente
                n = calculate_points(partido.id)
                updated += 1
                scored += n
                logger.info(
                    f"Partido finalizado: {partido.equipo_local} vs "
                    f"{partido.equipo_visitante} → {resultado} "
                    f"({n} predicciones evaluadas)"
                )

        except Exception as e:
            errors.append(str(e))
            logger.error(f"Error procesando fixture: {e}")

    db.session.commit()
    logger.info(
        f"Sync resultados: {updated} partidos actualizados, "
        f"{scored} predicciones evaluadas, {len(errors)} errores."
    )

    return {"updated": updated, "scored": scored, "errors": errors}


def _normalize_teams(home: str, away: str) -> str:
    """Normaliza nombres de equipos para matching flexible."""
    return f"{home.strip().lower()}|{away.strip().lower()}"
