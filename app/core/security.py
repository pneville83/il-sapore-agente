# app/core/security.py
"""
Autenticación mínima de la API.

- Tokens firmados (HMAC-SHA256) para el panel de Streamlit: el servidor decide
  quién eres, no el navegador.
- Secreto compartido para los endpoints del bot de WhatsApp: solo el bot puede
  llamarlos.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from fastapi import Header, HTTPException

SESSION_SECRET = os.getenv("SESSION_SECRET", "")
BOT_SECRET = os.getenv("BOT_SECRET", "")

DURACION_TOKEN_SEGUNDOS = 12 * 60 * 60  # 12 horas


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _de_b64url(texto: str) -> bytes:
    padding = "=" * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + padding)


def crear_token(usuario_id: int) -> str:
    """Crea un token firmado con el id del usuario y su caducidad."""
    if not SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET no configurado en el servidor.")
    payload = {
        "uid": int(usuario_id),
        "exp": int(time.time()) + DURACION_TOKEN_SEGUNDOS,
    }
    cuerpo = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    firma = hmac.new(SESSION_SECRET.encode(), cuerpo.encode(), hashlib.sha256).digest()
    return f"{cuerpo}.{_b64url(firma)}"


def verificar_token(token: str) -> Optional[int]:
    """Devuelve el usuario_id si la firma es válida y no expiró. Si no, None."""
    if not SESSION_SECRET or not token or "." not in token:
        return None
    try:
        cuerpo, firma_b64 = token.split(".", 1)
        esperada = hmac.new(SESSION_SECRET.encode(), cuerpo.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_de_b64url(firma_b64), esperada):
            return None
        payload = json.loads(_de_b64url(cuerpo))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return int(payload["uid"])
    except Exception:
        return None


def exigir_bot(x_bot_secret: str = Header(None)) -> None:
    """
    Dependencia de FastAPI para los endpoints que usa el bot de WhatsApp.

    Modo permissivo mientras BOT_SECRET esté vacío: permite desplegar el código
    antes de actualizar el bot. En cuanto defines BOT_SECRET en Render, la
    protección se activa sin tocar código.
    """
    if not BOT_SECRET:
        return
    if not x_bot_secret or not hmac.compare_digest(x_bot_secret, BOT_SECRET):
        raise HTTPException(status_code=403, detail="No autorizado.")