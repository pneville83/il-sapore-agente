# app/tools/payphone_procesador.py
"""
Procesador de pagos Payphone con conciliación activa.

FASE 1 (conciliar): busca filas PAYPHONE_PENDING con más de 2 minutos y le
pregunta a Payphone el estado real:
    GET {PAYPHONE_CHECK_STATUS_URL}/{clientTransactionId}

Payphone responde con una LISTA de transacciones (normalmente 1 elemento):
    [{"statusCode": 3, "transactionStatus": "Approved", "transactionId": ...}]

    statusCode 3 / "Approved"  -> PAYPHONE_CONFIRMED
    cancelada o rechazada      -> PAYPHONE_REJECTED (+ aviso al cliente)
    pendiente o sin datos      -> se queda PAYPHONE_PENDING (se reintenta)

FASE 2 (procesar): procesa las PAYPHONE_CONFIRMED:
    - registra el pago (idempotente: no duplica si ya hay transacción)
    - notifica al admin para que prepare el pedido
    - avisa al cliente de que el pago se recibió
    - guarda el payload de Payphone y marca PAYPHONE_ORDER_CREATED

Se invoca desde POST /payphone/procesar_pendientes (cron-job.org cada 2-3 min).
"""
import psycopg2
import psycopg2.extras
import requests

from app.core.config import DATABASE_URL, PAYPHONE_API_KEY, PAYPHONE_CHECK_STATUS_URL
from app.tools.pagos import registrar_pago
from app.tools.pedidos import obtener_admin_pedido, notificar_admin_pedido


# Códigos internos de este módulo
APROBADA = 3
RECHAZADA = 2
PENDIENTE = 1

_TEXTOS_APROBADOS = ("approved", "aprobado", "aprobada", "aceptado", "aceptada")
_TEXTOS_RECHAZADOS = (
    "canceled", "cancelled", "rejected", "denied",
    "cancelado", "cancelada", "rechazado", "rechazada",
)
_TEXTOS_PENDIENTES = ("pending", "pendiente", "processing", "in process", "en proceso")


def _normalizar_estado(item):
    """
    Traduce la respuesta de Payphone a 3 (aprobada), 2 (rechazada),
    1 (pendiente) o None (no reconocido).
    """
    if not isinstance(item, dict):
        return None

    # 1) El campo numérico manda
    raw = item.get("statusCode")
    if raw is not None:
        try:
            codigo = int(raw)
            if codigo in (APROBADA, RECHAZADA, PENDIENTE):
                return codigo
        except (TypeError, ValueError):
            pass

    # 2) Si no, por texto
    texto = str(
        item.get("transactionStatus") or item.get("status") or ""
    ).strip().lower()

    if texto in _TEXTOS_APROBADOS:
        return APROBADA
    if texto in _TEXTOS_RECHAZADOS:
        return RECHAZADA
    if texto in _TEXTOS_PENDIENTES:
        return PENDIENTE
    return None


def _consultar_estado_payphone(client_transaction_id):
    """
    Consulta el estado real de una transacción en Payphone.

    Devuelve (codigo, datos):
      codigo -> 3 aprobada, 2 rechazada, 1 pendiente, None error
      datos  -> dict con la transacción de Payphone (o None)
    """
    if not PAYPHONE_CHECK_STATUS_URL:
        print("ERROR: PAYPHONE_CHECK_STATUS_URL no configurado en el entorno.")
        return None, None

    try:
        headers = {
            "Authorization": f"Bearer {PAYPHONE_API_KEY}",
            "Content-Type": "application/json",
        }
        url = f"{PAYPHONE_CHECK_STATUS_URL.rstrip('/')}/{client_transaction_id}"

        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            print(
                f"ERROR Payphone status {client_transaction_id}: "
                f"HTTP {response.status_code} - {response.text[:200]}"
            )
            return None, None

        data = response.json()

        # Payphone devuelve una LISTA de transacciones para ese clientTransactionId
        if isinstance(data, list):
            if not data:
                print(
                    f"INFO Payphone status {client_transaction_id}: "
                    f"lista vacía (Payphone aún no registra ese pago)."
                )
                return PENDIENTE, None
            aprobadas = [x for x in data if _normalizar_estado(x) == APROBADA]
            item = aprobadas[0] if aprobadas else (data[0] if isinstance(data[0], dict) else None)
        elif isinstance(data, dict):
            item = data
        else:
            item = None

        if item is None:
            print(
                f"WARN Payphone status {client_transaction_id}: "
                f"respuesta no reconocida: {str(data)[:200]}"
            )
            return None, None

        codigo = _normalizar_estado(item)
        print(
            f"INFO Payphone status {client_transaction_id}: codigo={codigo} "
            f"estado={item.get('transactionStatus')} "
            f"txId={item.get('transactionId')} "
            f"monto={item.get('amount')}"
        )
        return codigo, item

    except Exception as e:
        print(
            f"ERROR consultando estado Payphone {client_transaction_id}: "
            f"{type(e).__name__}: {e}"
        )
        return None, None


def _whatsapp_cliente(cursor, pedido_id, customer_whatsapp=None, datos_payphone=None):
    """
    Decide a qué número avisar al cliente. Prioridad:
      1. clientes.whatsapp del pedido (es el número desde el que escribe)
      2. customer_whatsapp guardado en pending_transfers
      3. phoneNumber que devuelve Payphone
    """
    if pedido_id:
        try:
            cursor.execute("""
                SELECT c.whatsapp
                FROM pedidos p
                LEFT JOIN clientes c ON c.id = p.cliente_id
                WHERE p.id = %s
            """, (int(pedido_id),))
            fila = cursor.fetchone()
            if fila and fila[0]:
                return fila[0]
        except Exception:
            pass

    if customer_whatsapp:
        return customer_whatsapp

    if isinstance(datos_payphone, dict) and datos_payphone.get("phoneNumber"):
        return str(datos_payphone["phoneNumber"])

    return None


def _conciliar_pendientes(cursor, conexion):
    """
    FASE 1: consulta a Payphone el estado de las filas PAYPHONE_PENDING
    con más de 2 minutos y actualiza según la respuesta.
    Devuelve (conciliadas, rechazadas, errores).
    """
    conciliadas = 0
    rechazadas = 0
    errores = 0

    cursor.execute("""
        SELECT id FROM pending_transfers
        WHERE status = 'PAYPHONE_PENDING'
          AND created_at < NOW() - INTERVAL '2 minutes'
        ORDER BY created_at ASC
        LIMIT 20
    """)
    filas = cursor.fetchall()

    for fila in filas:
        temp_id = fila[0]
        codigo, datos = _consultar_estado_payphone(temp_id)
        payload = psycopg2.extras.Json(datos) if datos else None

        if codigo == APROBADA:
            cursor.execute("""
                UPDATE pending_transfers
                SET status = 'PAYPHONE_CONFIRMED',
                    payphone_webhook_payload = %s,
                    updated_at = NOW()
                WHERE id = %s AND status = 'PAYPHONE_PENDING'
            """, (payload, temp_id))
            conexion.commit()
            conciliadas += 1
            print(f"CONCILIADO: {temp_id} -> PAYPHONE_CONFIRMED")

        elif codigo == RECHAZADA:
            cursor.execute("""
                UPDATE pending_transfers
                SET status = 'PAYPHONE_REJECTED',
                    payphone_webhook_payload = %s,
                    updated_at = NOW()
                WHERE id = %s AND status = 'PAYPHONE_PENDING'
            """, (payload, temp_id))
            conexion.commit()
            rechazadas += 1
            print(f"RECHAZADO: {temp_id} -> PAYPHONE_REJECTED")

            # Avisar al cliente de que el pago no pasó
            cursor.execute("""
                SELECT customer_whatsapp, order_details_snapshot
                FROM pending_transfers WHERE id = %s
            """, (temp_id,))
            info = cursor.fetchone()
            if info:
                customer_whatsapp, snapshot = info[0], (info[1] or {})
                pedido_id = snapshot.get("pedido_id")
                destino = _whatsapp_cliente(cursor, pedido_id, customer_whatsapp, datos)
                if destino:
                    cursor.execute("""
                        INSERT INTO notificaciones_pendientes
                            (destinatario_whatsapp, mensaje, enviado)
                        VALUES (%s, %s, FALSE)
                    """, (
                        destino,
                        f"❌ El pago de tu pedido #{pedido_id} no se pudo procesar. "
                        f"Puedes intentar con otro método de pago o escribirnos. ¡Gracias!",
                    ))
                    conexion.commit()

        elif codigo == PENDIENTE:
            print(f"PENDIENTE: {temp_id} (Payphone todavía no lo confirma; se reintenta)")

        else:
            errores += 1
            print(f"ERROR conciliación {temp_id}: Payphone no devolvió un estado utilizable.")

    return conciliadas, rechazadas, errores


def _procesar_confirmadas(cursor, conexion):
    """
    FASE 2: procesa las filas PAYPHONE_CONFIRMED.
    Devuelve (procesadas, errores, detalle).
    """
    procesadas = 0
    errores = 0
    detalle = []

    cursor.execute("""
        SELECT id, customer_whatsapp, order_details_snapshot, payphone_webhook_payload
        FROM pending_transfers
        WHERE status = 'PAYPHONE_CONFIRMED'
        ORDER BY updated_at ASC
        LIMIT 50
    """)
    filas = cursor.fetchall()

    for fila in filas:
        temp_id = fila[0]
        customer_whatsapp = fila[1] or ""
        snapshot = fila[2] or {}
        datos_payphone = fila[3] if isinstance(fila[3], dict) else None

        pedido_id = snapshot.get("pedido_id")
        monto = snapshot.get("monto")
        ubicacion_id = snapshot.get("ubicacion_id", 1)

        if not pedido_id or monto is None:
            errores += 1
            detalle.append({"temp_id": temp_id, "error": "snapshot incompleto"})
            cursor.execute("""
                UPDATE pending_transfers
                SET status = 'PAYPHONE_ORDER_ERROR', updated_at = NOW()
                WHERE id = %s
            """, (temp_id,))
            conexion.commit()
            continue

        autorizacion = None
        if datos_payphone:
            autorizacion = (
                datos_payphone.get("authorizationCode")
                or datos_payphone.get("transactionId")
            )
        autorizacion = autorizacion or f"PAYPHONE-{temp_id}"

        try:
            # --- IDEMPOTENCIA: si el pedido ya tiene pago, no se duplica ---
            cursor.execute(
                "SELECT id FROM transacciones WHERE pedido_id = %s LIMIT 1",
                (int(pedido_id),)
            )
            ya_registrado = cursor.fetchone()

            if ya_registrado:
                print(
                    f"INFO {temp_id}: el pedido #{pedido_id} ya tenía pago "
                    f"registrado (transacción {ya_registrado[0]}). No se duplica."
                )
            else:
                resultado_pago = registrar_pago(
                    pedido_id=int(pedido_id),
                    metodo="tarjeta",
                    monto=float(monto),
                    banco_id=None,
                    autorizacion=str(autorizacion),
                    ubicacion_id=int(ubicacion_id),
                )
                if isinstance(resultado_pago, str) and resultado_pago.startswith("Error"):
                    raise Exception(f"registrar_pago falló: {resultado_pago}")

            # --- Avisar al admin: prepáralo ---
            admin_whatsapp = obtener_admin_pedido(int(ubicacion_id))
            if admin_whatsapp and not (
                isinstance(admin_whatsapp, str) and admin_whatsapp.startswith("Error")
            ):
                notificar_admin_pedido(int(pedido_id), admin_whatsapp)

            # --- Avisar al cliente: pago recibido ---
            destino_cliente = _whatsapp_cliente(
                cursor, pedido_id, customer_whatsapp, datos_payphone
            )
            if destino_cliente:
                cursor.execute("""
                    INSERT INTO notificaciones_pendientes
                        (destinatario_whatsapp, mensaje, enviado)
                    VALUES (%s, %s, FALSE)
                """, (
                    destino_cliente,
                    f"✅ Pago con tarjeta confirmado. Tu pedido #{pedido_id} está en "
                    f"preparación y ya no necesitas enviar comprobante: el pago es "
                    f"automático. ¡Gracias!",
                ))
            else:
                print(
                    f"WARN {temp_id}: pedido #{pedido_id} sin número de cliente. "
                    f"El admin se notificó, pero el cliente no."
                )

            cursor.execute("""
                UPDATE pending_transfers
                SET status = 'PAYPHONE_ORDER_CREATED', updated_at = NOW()
                WHERE id = %s
            """, (temp_id,))
            conexion.commit()

            procesadas += 1
            detalle.append({
                "temp_id": temp_id,
                "pedido_id": pedido_id,
                "autorizacion": str(autorizacion),
                "estado": "ok",
            })

        except Exception as e:
            errores += 1
            detalle.append({
                "temp_id": temp_id,
                "pedido_id": pedido_id,
                "error": f"{type(e).__name__}: {e}",
            })
            try:
                conexion.rollback()
            except Exception:
                pass
            # OJO: la fila se queda en PAYPHONE_CONFIRMED a propósito.
            # Así el siguiente cron reintenta y no se pierde el pedido.
            # Gracias a la idempotencia, reintentar no duplica el pago.
            print(f"ERROR procesando {temp_id}: {type(e).__name__}: {e}")

    return procesadas, errores, detalle


def procesar_pendientes_payphone():
    """
    Punto de entrada. Hace FASE 1 (conciliar) y FASE 2 (procesar).
    Devuelve {conciliadas, rechazadas, procesadas, errores, detalle}.
    """
    conexion = None
    cursor = None
    conciliadas = 0
    rechazadas = 0
    procesadas = 0
    errores_conc = 0
    errores_proc = 0
    detalle = []

    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        conciliadas, rechazadas, errores_conc = _conciliar_pendientes(cursor, conexion)
        procesadas, errores_proc, detalle = _procesar_confirmadas(cursor, conexion)

        return {
            "conciliadas": conciliadas,
            "rechazadas": rechazadas,
            "procesadas": procesadas,
            "errores": errores_conc + errores_proc,
            "detalle": detalle,
        }

    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return {
            "conciliadas": conciliadas,
            "rechazadas": rechazadas,
            "procesadas": procesadas,
            "errores": errores_conc + errores_proc + 1,
            "detalle": detalle + [{"error_global": f"{type(e).__name__}: {e}"}],
        }
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass