"""
PorraCarLOL — Servicio de notificaciones WhatsApp
Llama al bridge local (whatsapp-mcp) en localhost:8080
"""
import requests
import logging
from flask import current_app

logger = logging.getLogger(__name__)

BRIDGE_URL = "http://localhost:8080/api/send"
BRIDGE_TIMEOUT = 10  # segundos


def send_whatsapp(message: str, group_jid: str | None = None) -> bool:
    """
    Envía un mensaje de texto al grupo de WhatsApp de la porra.
    Devuelve True si se envió correctamente.
    """
    jid = group_jid or current_app.config.get("WHATSAPP_GROUP_JID", "")
    if not jid:
        logger.warning("WHATSAPP_GROUP_JID no configurado — mensaje no enviado.")
        return False

    try:
        res = requests.post(
            BRIDGE_URL,
            json={"recipient": jid, "message": message},
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

def notify_recordatorio_jornada(jornada: int, pendientes: list[str], minutos: int):
    """Avisa a los jugadores que aún no han entregado sus pronósticos."""
    if not pendientes:
        return
    nombres = ", ".join(pendientes)
    emoji_tiempo = "🚨" if minutos <= 60 else "⏳"
    horas = minutos // 60
    tiempo_str = f"{horas}h" if horas else f"{minutos} min"
    msg = (
        f"{emoji_tiempo} *PorraCarLOL — Jornada {jornada}*\n\n"
        f"¡Quedan *{tiempo_str}* para que cierren los pronósticos!\n\n"
        f"Aún no han entregado:\n"
        + "\n".join(f"  • {n}" for n in pendientes)
        + f"\n\n🔗 porra.esaria.es/pronosticos"
    )
    send_whatsapp(msg)


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
    """Avisa que los pronósticos especiales van a cerrarse."""
    if not pendientes:
        return
    nombres = ", ".join(pendientes)
    msg = (
        f"⚠️ *Pronósticos Especiales — ¡Quedan {horas}h!*\n\n"
        f"Aún no han enviado sus especiales:\n"
        + "\n".join(f"  • {n}" for n in pendientes)
        + f"\n\nSe cierran cuando empiece la Jornada 2.\n"
        f"🔗 porra.esaria.es/especiales"
    )
    send_whatsapp(msg)
