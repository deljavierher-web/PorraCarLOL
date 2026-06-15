"""
PorraCarLOL — Servicio de notificaciones WhatsApp
Llama al bridge local (whatsapp-mcp) en localhost:8080
"""
import os
import json
import requests
import logging
from flask import current_app

logger = logging.getLogger(__name__)

BRIDGE_URL = "http://localhost:8080/api/send"
BRIDGE_TIMEOUT = 10  # segundos

# Ruta del mapa username -> teléfono (en la raíz del proyecto, fuera de git)
_TELEFONOS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "telefonos.json"
)


def load_telefonos() -> dict[str, str]:
    """Carga el mapa {username: telefono}. Ignora claves vacías y comentarios."""
    try:
        with open(_TELEFONOS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_") and v}
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"No se pudo cargar telefonos.json: {e}")
        return {}


def telefonos_de(usernames: list[str]) -> list[str]:
    """Devuelve los teléfonos de los usuarios dados que estén en el mapa."""
    mapa = load_telefonos()
    return [mapa[u] for u in usernames if u in mapa]


def send_whatsapp(message: str, group_jid: str | None = None,
                  mentions: list[str] | None = None) -> bool:
    """
    Envía un mensaje de texto al grupo de WhatsApp de la porra.
    `mentions`: lista de teléfonos (ej. "34600111222") a mencionar de verdad.
    Devuelve True si se envió correctamente.
    """
    jid = group_jid or current_app.config.get("WHATSAPP_GROUP_JID", "")
    if not jid:
        logger.warning("WHATSAPP_GROUP_JID no configurado — mensaje no enviado.")
        return False

    payload = {"recipient": jid, "message": message}
    if mentions:
        payload["mentions"] = mentions

    try:
        res = requests.post(
            BRIDGE_URL,
            json=payload,
            timeout=BRIDGE_TIMEOUT,
        )
        data = res.json()
        if data.get("success"):
            logger.info(f"WhatsApp enviado OK: {message[:60]}...")
            return True
        else:
            logger.error(f"Bridge error: {data.get('message')}")
            return False
    except requests.exceptions.ConnectionError:
        logger.warning("Bridge WhatsApp no disponible (¿está corriendo el bridge?)")
        return False
    except Exception as e:
        logger.error(f"Error enviando WhatsApp: {e}")
        return False


# ── Mensajes predefinidos ──────────────────────────────────────────────────────

def _lineas_pendientes(pendientes: list[str]) -> tuple[list[str], list[str]]:
    """
    Construye las líneas de la lista de pendientes mencionando a quien tenga
    teléfono (@número) y devuelve también la lista de teléfonos para `mentions`.
    """
    mapa = load_telefonos()
    lineas, mentions = [], []
    for n in pendientes:
        telefono = mapa.get(n)
        if telefono:
            lineas.append(f"  • @{telefono}")
            mentions.append(telefono)
        else:
            lineas.append(f"  • {n}")
    return lineas, mentions


def notify_recordatorio_jornada(jornada: int, pendientes: list[str], minutos: int):
    """Avisa (mencionando) a los jugadores que aún no han entregado sus pronósticos."""
    if not pendientes:
        return
    emoji_tiempo = "🚨" if minutos <= 60 else "⏳"
    horas = minutos // 60
    tiempo_str = f"{horas}h" if horas else f"{minutos} min"
    lineas, mentions = _lineas_pendientes(pendientes)
    msg = (
        f"{emoji_tiempo} *PorraCarLOL — Jornada {jornada}*\n\n"
        f"¡Quedan *{tiempo_str}* para que cierren los pronósticos!\n\n"
        f"Aún no han entregado:\n"
        + "\n".join(lineas)
        + f"\n\n🔗 porra.esaria.es/pronosticos"
    )
    send_whatsapp(msg, mentions=mentions)


def notify_partido_empieza(equipo_local: str, equipo_visitante: str, minutos: int = 30):
    """Avisa que un partido empieza pronto (pronósticos cerrados ya)."""
    msg = (
        f"🔔 *¡Empieza en {minutos} min!*\n\n"
        f"⚽ {equipo_local} vs {equipo_visitante}\n\n"
        f"Los pronósticos están cerrados. ¡A sufrir! 😅"
    )
    send_whatsapp(msg)


def notify_resultado(equipo_local: str, equipo_visitante: str, resultado: str,
                     acertaron: list[str], fallaron: list[str],
                     rachas: list[tuple[str, int]] | None = None) -> bool:
    """Notifica el resultado de un partido, quién acertó y quién está en racha."""
    res_label = {
        "1": f"Gana *{equipo_local}*",
        "2": f"Gana *{equipo_visitante}*",
        "X": "Empate",
    }.get(resultado, resultado)

    lineas = [f"📊 *{equipo_local} vs {equipo_visitante}*", f"Resultado: {res_label}", ""]
    if acertaron:
        lineas.append("✅ Aciertan: " + ", ".join(acertaron))
    if fallaron:
        lineas.append("❌ Fallan: " + ", ".join(fallaron))

    if rachas:
        lineas.append("")
        lineas.append("🔥 *En racha:*")
        for username, n in rachas:
            lineas.append(f"  • {username} — {n} aciertos seguidos")

    return send_whatsapp("\n".join(lineas))


def notify_ranking_diario(ranking: list[dict]):
    """Envía el ranking diario por la mañana."""
    medallas = ["🥇", "🥈", "🥉"]
    lineas = ["🏆 *Ranking PorraCarLOL*\n"]
    for i, entry in enumerate(ranking[:10]):
        medalla = medallas[i] if i < 3 else f"{i+1}."
        lineas.append(f"{medalla} {entry['username']} — {entry['puntos_totales']:.1f} pts")
    lineas.append(f"\n🔗 porra.esaria.es/dashboard")
    send_whatsapp("\n".join(lineas))


def notify_especiales_cerrando(pendientes: list[str], horas: int):
    """Avisa (mencionando) que los pronósticos especiales van a cerrarse."""
    if not pendientes:
        return
    lineas, mentions = _lineas_pendientes(pendientes)
    msg = (
        f"⚠️ *Pronósticos Especiales — ¡Quedan {horas}h!*\n\n"
        f"Aún no han enviado sus especiales:\n"
        + "\n".join(lineas)
        + f"\n\n🔗 porra.esaria.es/especiales"
    )
    send_whatsapp(msg, mentions=mentions)
