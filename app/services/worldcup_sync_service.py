"""
PorraCarLOL — Servicio de Sincronización del Mundial 2026 (Keyless API)
Sincroniza todos los partidos, fechas, resultados y genera cuotas realistas automáticamente.
"""
import logging
from datetime import datetime, timedelta, timezone
import requests
from app.extensions import db
from app.models.partido import Partido
from app.services.scoring_service import calculate_points

logger = logging.getLogger(__name__)

WORLDCUP_API_GAMES = "https://worldcup26.ir/get/games"

TEAM_RATINGS = {
    "Argentina": 88, "France": 87, "England": 86, "Brazil": 86, "Spain": 85,
    "Portugal": 84, "Netherlands": 83, "Italy": 82, "Germany": 83, "Belgium": 81,
    "Croatia": 80, "Uruguay": 81, "Morocco": 80, "USA": 78, "United States": 78,
    "Mexico": 77, "México": 77, "Japan": 78, "Japón": 78, "South Korea": 76, 
    "Corea del Sur": 76, "Switzerland": 77, "Suiza": 77, "Austria": 76, "Norway": 77,
    "Noruega": 77, "Sweden": 76, "Suecia": 76, "Turkey": 76, "Turquía": 76, 
    "Senegal": 75, "Ecuador": 75, "Ivory Coast": 75, "Costa de Marfil": 75,
    "Australia": 73, "Czech Republic": 74, "República Checa": 74, "Czechia": 74,
    "Bosnia and Herzegovina": 72, "Bosnia y Herzegovina": 72, "Paraguay": 73,
    "Egypt": 73, "Egipto": 73, "Saudi Arabia": 70, "Arabia Saudí": 70, 
    "Iraq": 68, "Jordan": 67, "Jordania": 67, "Iran": 71, "Irán": 71, 
    "Scotland": 72, "Escocia": 72, "Qatar": 68, "Catar": 68, 
    "Cape Verde": 69, "Cabo Verde": 69, "Tunisia": 70, "Túnez": 70, 
    "Algeria": 73, "Argelia": 73, "Ghana": 72, "Uzbekistan": 66, "Uzbekistán": 66, 
    "Democratic Republic of the Congo": 70, "Congo DR": 70, "RD Congo": 70,
    "Colombia": 78, "Panama": 68, "Panamá": 68, "Haiti": 65, "Haití": 65,
    "Curacao": 63, "Curaçao": 63, "South Africa": 70, "Sudáfrica": 70, 
    "New Zealand": 64, "Nueva Zelanda": 64
}

STADIUM_OFFSETS = {
    # Western (UTC-7 in June)
    "13": -7, "14": -7, "15": -7, "16": -7,
    # Central (UTC-5 in June)
    "1": -5, "2": -5, "3": -5, "4": -5, "5": -5, "6": -5,
    # Eastern (UTC-4 in June)
    "7": -4, "8": -4, "9": -4, "10": -4, "11": -4, "12": -4,
}

TEAM_TRANSLATIONS = {
    "Mexico": "México",
    "South Africa": "Sudáfrica",
    "South Korea": "Corea del Sur",
    "Czech Republic": "República Checa",
    "Czechia": "República Checa",
    "Canada": "Canadá",
    "Bosnia and Herzegovina": "Bosnia y Herzegovina",
    "United States": "Estados Unidos",
    "Haiti": "Haití",
    "Scotland": "Escocia",
    "Turkey": "Turquía",
    "Brazil": "Brasil",
    "Morocco": "Marruecos",
    "Qatar": "Catar",
    "Switzerland": "Suiza",
    "Ivory Coast": "Costa de Marfil",
    "Germany": "Alemania",
    "Curaçao": "Curazao",
    "Curacao": "Curazao",
    "Netherlands": "Países Bajos",
    "Japan": "Japón",
    "Sweden": "Suecia",
    "Tunisia": "Túnez",
    "Iran": "Irán",
    "New Zealand": "Nueva Zelanda",
    "Spain": "España",
    "Cape Verde": "Cabo Verde",
    "Belgium": "Bélgica",
    "Egypt": "Egipto",
    "Saudi Arabia": "Arabia Saudí",
    "Uruguay": "Uruguay",
    "France": "Francia",
    "Senegal": "Senegal",
    "Iraq": "Irak",
    "Norway": "Noruega",
    "Argentina": "Argentina",
    "Algeria": "Argelia",
    "Austria": "Austria",
    "Jordan": "Jordania",
    "Portugal": "Portugal",
    "Democratic Republic of the Congo": "Rep. Dem. Congo",
    "Congo DR": "Rep. Dem. Congo",
    "DR Congo": "Rep. Dem. Congo",
    "England": "Inglaterra",
    "Croatia": "Croacia",
    "Uzbekistan": "Uzbekistán",
    "Colombia": "Colombia",
    "Ghana": "Ghana",
    "Panama": "Panamá",
    "USA": "Estados Unidos",
    "Bosnia & Herzegovina": "Bosnia y Herzegovina",
}

def translate_team(name: str) -> str:
    return TEAM_TRANSLATIONS.get(name, name)

def calculate_realistic_odds(home: str, away: str) -> tuple[float, float, float]:
    home_rating = TEAM_RATINGS.get(home, 70)
    away_rating = TEAM_RATINGS.get(away, 70)
    diff = home_rating - away_rating
    
    # Base odds
    c1, cx, c2 = 2.50, 3.10, 2.70
    
    if diff > 0:
        c1 = max(1.15, 2.50 - (diff * 0.12))
        cx = min(12.00, 3.10 + (diff * 0.15))
        c2 = min(30.00, 2.70 + (diff * 0.60))
    elif diff < 0:
        abs_diff = abs(diff)
        c2 = max(1.15, 2.70 - (abs_diff * 0.12))
        cx = min(12.00, 3.10 + (abs_diff * 0.15))
        c1 = min(30.00, 2.50 + (abs_diff * 0.60))
        
    return round(c1, 2), round(cx, 2), round(c2, 2)

def sync_worldcup_data() -> dict:
    """
    Sincroniza partidos y resultados desde la API pública de worldcup26.ir.
    Registra automáticamente los resultados y recalcula los puntos.
    """
    logger.info("Iniciando sincronización de datos de World Cup 2026...")
    try:
        res = requests.get(WORLDCUP_API_GAMES, timeout=30)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        logger.error(f"Error al conectar con la API de worldcup26.ir: {e}")
        return {"created": 0, "updated": 0, "scored": 0, "error": str(e)}

    games = data.get("games", [])
    if not games:
        return {"created": 0, "updated": 0, "scored": 0}

    created = 0
    updated = 0
    scored = 0

    for game in games:
        try:
            matchday_val = game.get("matchday")
            if not matchday_val:
                continue
                
            try:
                jornada = int(matchday_val)
            except ValueError:
                type_val = game.get("type", "")
                if type_val == "r32":
                    jornada = 4
                elif type_val == "r16":
                    jornada = 5
                elif type_val == "qf":
                    jornada = 6
                elif type_val == "sf":
                    jornada = 7
                elif type_val == "third":
                    jornada = 8
                elif type_val == "final":
                    jornada = 9
                else:
                    jornada = 10

            home_en = game.get("home_team_name_en", "")
            away_en = game.get("away_team_name_en", "")
            
            if not home_en or not away_en:
                home_en = game.get("home_team_label", "Pendiente")
                away_en = game.get("away_team_label", "Pendiente")

            home_es = translate_team(home_en)
            away_es = translate_team(away_en)

            stadium_id = game.get("stadium_id", "1")
            offset = STADIUM_OFFSETS.get(stadium_id, -5)

            # Parsear fecha local (formato: "MM/DD/YYYY HH:MM")
            local_date_str = game.get("local_date", "")
            if local_date_str:
                local_dt = datetime.strptime(local_date_str, "%m/%d/%Y %H:%M")
                # Convertir a UTC restando el offset (local_time - offset)
                fecha_utc = local_dt - timedelta(hours=offset)
                fecha_utc = fecha_utc.replace(tzinfo=timezone.utc)
            else:
                fecha_utc = datetime.now(timezone.utc)

            api_match_id = game.get("_id") or f"wc26_{game.get('id')}"

            # Calcular cuotas realistas
            cuota_1, cuota_x, cuota_2 = calculate_realistic_odds(home_en, away_en)

            # Buscar si el partido ya existe
            partido = Partido.query.filter_by(api_match_id=api_match_id).first()

            if not partido:
                partido = Partido(
                    jornada=jornada,
                    equipo_local=home_es,
                    equipo_visitante=away_es,
                    cuota_1=cuota_1,
                    cuota_x=cuota_x,
                    cuota_2=cuota_2,
                    fecha_partido=fecha_utc,
                    api_match_id=api_match_id
                )
                db.session.add(partido)
                created += 1
            else:
                # Si existe, actualizar fecha y equipos
                if not partido.ha_comenzado:
                    partido.fecha_partido = fecha_utc
                    partido.equipo_local = home_es
                    partido.equipo_visitante = away_es
                    # Solo actualizamos cuotas si siguen siendo las por defecto (para no sobreescribir edición manual)
                    if partido.cuota_1 == 1.0 or partido.cuota_1 == cuota_1:
                        partido.cuota_1 = cuota_1
                        partido.cuota_x = cuota_x
                        partido.cuota_2 = cuota_2
                    updated += 1

            # Marcador si ha finalizado
            finished_api = str(game.get("finished", "FALSE")).upper() == "TRUE"
            
            if finished_api and not partido.finalizado:
                try:
                    home_score = int(game.get("home_score", 0) or 0)
                    away_score = int(game.get("away_score", 0) or 0)
                    
                    if home_score > away_score:
                        resultado = "1"
                    elif home_score == away_score:
                        resultado = "X"
                    else:
                        resultado = "2"
                    
                    partido.resultado_real = resultado
                    partido.finalizado = True
                    db.session.flush()

                    n_scored = calculate_points(partido.id)
                    scored += n_scored
                except Exception as inner_e:
                    logger.error(f"Error procesando resultado para juego {game.get('id')}: {inner_e}")

        except Exception as ex:
            logger.error(f"Error procesando juego {game.get('id')}: {ex}")

    db.session.commit()
    logger.info(f"Sincronización finalizada: {created} creados, {updated} actualizados, {scored} predicciones puntuadas.")
    return {"created": created, "updated": updated, "scored": scored}
