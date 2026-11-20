from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from typing import Optional, List
from app.agent.executor import agente
from app.core.limiter import limiter
import psycopg2
import uuid
from app.core.config import DATABASE_URL

router = APIRouter()


# ============================================================
# MODELOS
# ============================================================

class MensajeHistorial(BaseModel):
    role: str
    content: str

class Pregunta(BaseModel):
    texto: str = Field(..., max_length=2000)
    whatsapp_usuario: Optional[str] = Field(None, max_length=20)
    usuario_id: Optional[int] = None
    historial: Optional[List[MensajeHistorial]] = None

class LoginRequest(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=100)

class MensajeWhatsApp(BaseModel):
    texto: str
    whatsapp_usuario: str
    whatsapp_real: Optional[str] = None
    whatsapp_lid: Optional[str] = None
    ubicacion_id: int = 1

class Comprobante(BaseModel):
    pedido_id: int
    cliente_whatsapp: str
    cliente_nombre: Optional[str] = None
    media_base64: str
    monto: float
    ubicacion_id: int = 1

class MarcarPendientes(BaseModel):
    ids: List[int]

class BotEstado(BaseModel):
    ubicacion_id: int
    activo: bool
    whatsapp_usuario: str


# ============================================================
# ENDPOINTS EXISTENTES
# ============================================================

@router.post("/preguntar")
@limiter.limit("20/minute")
async def preguntar(request: Request, response: Response, pregunta: Pregunta):
    resultado = agente(
        pregunta=pregunta.texto,
        whatsapp_usuario=pregunta.whatsapp_usuario,
        usuario_id=pregunta.usuario_id,
        historial_previo=pregunta.historial
    )
    return resultado

@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, response: Response, credenciales: LoginRequest):
    from app.core.auth import autenticar_usuario
    usuario = autenticar_usuario(credenciales.username, credenciales.password)
    if usuario and "error" not in usuario:
        return usuario
    else:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

@router.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok", "mensaje": "Agente de Il Sapore funcionando"}

@router.post("/whatsapp")
async def whatsapp(mensaje: MensajeWhatsApp):
    resultado = agente(
        pregunta=mensaje.texto,
        whatsapp_usuario=mensaje.whatsapp_usuario,
        whatsapp_real=mensaje.whatsapp_real,
        whatsapp_lid=mensaje.whatsapp_lid,
        usuario_id=None,
        historial_previo=None
    )
    return resultado


# ============================================================
# NUEVOS ENDPOINTS
# ============================================================

@router.post("/whatsapp/comprobante")
async def whatsapp_comprobante(comprobante: Comprobante):
    """
    El bot lo llama cuando un cliente manda una imagen de comprobante.
    Guarda en pending_transfers con status='ESPERANDO_AUTORIZACION'.
    Devuelve el temp_id y el mensaje para reenviar al superadmin.
    """
    conexion = None
    cursor = None
    try:
        # Generar temp_id único
        temp_id = f"TRF-{comprobante.pedido_id}-{uuid.uuid4().hex[:6].upper()}"

        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # Verificar que el pedido existe y obtener el total real
        cursor.execute(
            "SELECT id, total, ubicacion_id FROM pedidos WHERE id = %s",
            (comprobante.pedido_id,)
        )
        fila = cursor.fetchone()
        if not fila:
            raise HTTPException(status_code=404, detail=f"Pedido #{comprobante.pedido_id} no existe.")

        pedido_id, total_pedido, ubicacion_id = fila

        # Insertar en pending_transfers
        cursor.execute("""
            INSERT INTO pending_transfers
                (id, customer_whatsapp, customer_name, media_data,
                 convo_state_snapshot, order_details_snapshot, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'ESPERANDO_AUTORIZACION')
        """, (
            temp_id,
            comprobante.cliente_whatsapp,
            comprobante.cliente_nombre or "",
            comprobante.media_base64,
            None,
            psycopg2.extras.Json({
                "pedido_id": pedido_id,
                "monto": float(comprobante.monto),
                "ubicacion_id": ubicacion_id,
            }),
        ))
        conexion.commit()

        # Obtener whatsapp del superadmin para el mensaje
        cursor.execute("""
            SELECT whatsapp FROM usuarios
            WHERE rol = 'superadmin' AND whatsapp IS NOT NULL
            LIMIT 1
        """)
        fila_super = cursor.fetchone()
        superadmin_whatsapp = fila_super[0] if fila_super else None

        mensaje_superadmin = (
            f"Transferencia pendiente - Pedido #{pedido_id} - "
            f"Cliente: {comprobante.cliente_nombre or comprobante.cliente_whatsapp} - "
            f"Total: ${float(comprobante.monto):.2f}. "
            f"¿La autorizas? (temp_id: {temp_id})"
        )

        return {
            "estado": "ok",
            "temp_id": temp_id,
            "pedido_id": pedido_id,
            "superadmin_whatsapp": superadmin_whatsapp,
            "mensaje_superadmin": mensaje_superadmin,
        }

    except HTTPException:
        raise
    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        raise HTTPException(status_code=500, detail=f"Error al guardar comprobante: {str(e)}")
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass


@router.get("/whatsapp/pendientes")
async def whatsapp_pendientes(ubicacion_id: int = 1):
    """
    Devuelve las notificaciones_pendientes no enviadas para esa ubicación.
    Incluye las que van al admin de esa ubicación y al superadmin.
    NO las marca como enviadas (el bot lo hará con POST /whatsapp/pendientes/marcar).
    """
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # Números relevantes: admin de la ubicación + superadmin
        cursor.execute("""
            SELECT whatsapp FROM usuarios
            WHERE whatsapp IS NOT NULL
              AND (
                (rol = 'admin' AND ubicacion_id = %s)
                OR rol = 'superadmin'
              )
        """, (ubicacion_id,))
        numeros = [f[0] for f in cursor.fetchall()]

        if not numeros:
            return {"pendientes": []}

        cursor.execute("""
            SELECT id, destinatario_whatsapp, mensaje, created_at
            FROM notificaciones_pendientes
            WHERE enviado = FALSE
              AND destinatario_whatsapp = ANY(%s)
            ORDER BY created_at ASC
        """, (numeros,))
        filas = cursor.fetchall()

        pendientes = [
            {
                "id": f[0],
                "destinatario_whatsapp": f[1],
                "mensaje": f[2],
                "created_at": f[3].isoformat() if f[3] else None,
            }
            for f in filas
        ]

        return {"pendientes": pendientes}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar pendientes: {str(e)}")
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass


@router.post("/whatsapp/pendientes/marcar")
async def whatsapp_pendientes_marcar(body: MarcarPendientes):
    """
    Marca notificaciones_pendientes como enviadas. El bot llama esto después
    de enviar los mensajes con éxito.
    """
    if not body.ids:
        return {"estado": "ok", "marcadas": 0}

    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        cursor.execute("""
            UPDATE notificaciones_pendientes
            SET enviado = TRUE
            WHERE id = ANY(%s)
        """, (body.ids,))
        marcadas = cursor.rowcount
        conexion.commit()

        return {"estado": "ok", "marcadas": marcadas}

    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        raise HTTPException(status_code=500, detail=f"Error al marcar pendientes: {str(e)}")
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass


@router.post("/bot/estado")
async def bot_estado_post(body: BotEstado):
    """
    Cambia el estado del bot (abrir/cerrar) para una ubicación.
    Solo admin de esa ubicación o superadmin.
    """
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # Verificar rol
        cursor.execute("""
            SELECT rol, ubicacion_id FROM usuarios
            WHERE whatsapp = %s
            LIMIT 1
        """, (body.whatsapp_usuario,))
        fila = cursor.fetchone()
        if not fila:
            raise HTTPException(status_code=403, detail="Usuario no autorizado.")

        rol, ubicacion_usuario = fila
        autorizado = (
            rol == "superadmin"
            or (rol == "admin" and ubicacion_usuario == body.ubicacion_id)
        )
        if not autorizado:
            raise HTTPException(status_code=403, detail="No autorizado para esta ubicación.")

        # Actualizar
        cursor.execute("""
            UPDATE ubicaciones SET bot_activo = %s WHERE id = %s
            RETURNING bot_activo
        """, (body.activo, body.ubicacion_id))
        fila_ub = cursor.fetchone()
        if not fila_ub:
            raise HTTPException(status_code=404, detail=f"Ubicación {body.ubicacion_id} no existe.")
        conexion.commit()

        return {
            "estado": "ok",
            "bot_activo": fila_ub[0],
            "mensaje": "✅ Bot abierto." if body.activo else "🔒 Bot cerrado.",
        }

    except HTTPException:
        raise
    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        raise HTTPException(status_code=500, detail=f"Error al cambiar estado: {str(e)}")
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass


@router.get("/bot/estado")
async def bot_estado_get(ubicacion_id: int = 1):
    """
    Devuelve el estado del bot para una ubicación.
    """
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        cursor.execute(
            "SELECT bot_activo FROM ubicaciones WHERE id = %s",
            (ubicacion_id,)
        )
        fila = cursor.fetchone()
        if not fila:
            raise HTTPException(status_code=404, detail=f"Ubicación {ubicacion_id} no existe.")

        return {"ubicacion_id": ubicacion_id, "bot_activo": fila[0]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar estado: {str(e)}")
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass

@router.get("/whatsapp/pedido_pendiente")
async def whatsapp_pedido_pendiente(whatsapp: str):
    """
    Busca el pedido pendiente más reciente de un cliente con metodo_pago='transferencia'
    y estado='Recibido'. Lo usa el bot para saber a qué pedido asociar el comprobante.
    """
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT p.id, p.total, p.ubicacion_id, c.id
            FROM pedidos p
            JOIN clientes c ON c.id = p.cliente_id
            WHERE (c.whatsapp = %s OR c.whatsapp_lid = %s)
              AND p.metodo_pago = 'transferencia'
              AND p.estado = 'Recibido'
            ORDER BY p.fecha DESC
            LIMIT 1
        """, (whatsapp, whatsapp))
        fila = cursor.fetchone()

        if not fila:
            return {"tiene_pedido": False, "pedido": None}

        return {
            "tiene_pedido": True,
            "pedido": {
                "pedido_id": fila[0],
                "total": float(fila[1]),
                "ubicacion_id": fila[2],
                "cliente_id": fila[3],
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar pedido pendiente: {str(e)}")
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass        