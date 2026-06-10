"""
PorraCarLOL — Servicio de Notificaciones
Recordatorio por Telegram a quienes no han enviado sus pronósticos
cuando se acerca el cierre de una fase.
"""
import json
import logging
import os
from datetime import datetime, timezone

import requests
from flask import current_app

from app.extensions import db
from app.models.partido import Partido
from app.models.prediccion import Prediccion
from app.models.usuario import Usuario

logger = logging.getLogger(__name__)

# Horas antes del primer partido de la fase a partir de las cuales se avisa
REMINDER_WINDOW_HOURS = 24


def _sent_file_path() -> str:
    """Archivo donde se registran los recordatorios ya enviados (evita duplicados)."""
    return os.path.join(current_app.instance_path, "reminders_sent.json")


def _load_sent() -> dict:
    try:
        with open(_sent_file_path()) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_sent(sent: dict) -> None:
    os.makedirs(current_app.instance_path, exist_ok=True)
    with open(_sent_file_path(), "w") as f:
        json.dump(sent, f)


def send_telegram_message(text: str) -> bool:
    """Envía un mensaje al grupo de Telegram configurado."""
    token = current_app.config.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = current_app.config.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False

    try:
        res = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if res.status_code != 200:
            logger.error(f"Telegram respondió {res.status_code}: {res.text}")
            return False
        return True
    except requests.RequestException as e:
        logger.error(f"Error enviando mensaje de Telegram: {e}")
        return False


def check_and_send_deadline_reminders() -> None:
    """
    Busca la próxima fase cuyo primer partido empieza en menos de 24h
    y avisa por Telegram a quienes aún no hayan enviado sus pronósticos.
    Se envía como máximo un recordatorio por fase.
    """
    if not current_app.config.get("TELEGRAM_BOT_TOKEN"):
        return

    now = datetime.now(timezone.utc)

    # Primer partido futuro de cada jornada
    proximos = (
        db.session.query(Partido.jornada, db.func.min(Partido.fecha_partido).label("inicio"))
        .filter(Partido.finalizado == False)  # noqa: E712
        .group_by(Partido.jornada)
        .all()
    )

    for jornada, inicio in proximos:
        if inicio is None:
            continue
        inicio_utc = inicio if inicio.tzinfo else inicio.replace(tzinfo=timezone.utc)
        diff_horas = (inicio_utc - now).total_seconds() / 3600

        # Solo fases que cierran dentro de la ventana y aún no han empezado
        if not (0 < diff_horas <= REMINDER_WINDOW_HOURS):
            continue

        sent = _load_sent()
        if str(jornada) in sent:
            continue

        # Usuarios sin pronósticos enviados para esta fase
        jugadores = Usuario.query.filter_by(es_administrador=False).all()
        jugadores = [u for u in jugadores if u.username != "invitado"]

        rezagados = []
        for u in jugadores:
            enviados = (
                db.session.query(Prediccion)
                .join(Partido, Prediccion.partido_id == Partido.id)
                .filter(
                    Prediccion.usuario_id == u.id,
                    Partido.jornada == jornada,
                    Prediccion.enviado == True,  # noqa: E712
                )
                .count()
            )
            if enviados == 0:
                rezagados.append(u.username)

        horas = int(diff_horas)
        if rezagados:
            nombres = ", ".join(f"<b>{n}</b>" for n in rezagados)
            texto = (
                f"⏳ <b>¡La Fase {jornada} cierra en ~{horas}h!</b>\n\n"
                f"Aún no han enviado sus pronósticos: {nombres}\n\n"
                f"👉 https://porra.esaria.es"
            )
        else:
            texto = (
                f"✅ <b>Fase {jornada}</b>: todos habéis enviado vuestros pronósticos. "
                f"¡El primer partido empieza en ~{horas}h! ⚽"
            )

        if send_telegram_message(texto):
            sent[str(jornada)] = now.isoformat()
            _save_sent(sent)
            logger.info(f"Recordatorio de Telegram enviado para la Fase {jornada}.")
