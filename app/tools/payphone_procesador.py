# app/tools/payphone_procesador.py
"""
Procesador de pagos Payphone con conciliación activa.

FASE 1: Busca filas PAYPHONE_PENDING con más de 2 minutos y consulta a
Payphone su estado real (POST /button/V2/Confirm con {"clientTxId": id}).
Si Payphone dice aprobado (StatusCode 3), actualiza a PAYPHONE_CONFIRMED.
Si dice rechazado (StatusCode 2), actualiza a PAYPHONE_REJECTED.

FASE 2: Procesa filas PAYPHONE_CONFIRMED: registra pago, notifica admin
y cliente, marca PAYPHONE_ORDER_CREATED.

Se invoca desde POST /payphone/procesar_pendientes (cron-job.org cada 2-3 min).
"""
import os
import psycopg2
import requests
from app.core.config import DATABASE_URL, PAYPHONE_API_KEY, PAYPHONE_CHECK_STATUS_URL
from app.tools.pagos import registrar_pago
from app.tools.pedidos import obtener_admin_pedido, notificar_admin_pedido


def _consultar_estado_payphone(client_transaction_id: str):
    """
    Consulta a Payphone el estado de una transacción usando el clientTransactionId.
    Endpoint: GET {PAYPHONE_CHECK_STATUS_URL}/{clientTransactionId}
    Devuelve el StatusCode (int) o None si hay error.
    Según Payphone: Aceptado = aprobado, Cancelado = rechazado, Pendiente = esperar.
    """
    if not PAYPHONE_CHECK_STATUS_URL:
        print("ERROR: PAYPHONE_CHECK_STATUS_URL no configurado en el entorno.")
        return None

    try:
        headers = {
            "Authorization": f"Bearer {PAYPHONE_API_KEY}",
            "Content-Type": "application/json",
        }

        # Construir la URL: base + "/" + client_transaction_id
        url = f"{PAYPHONE_CHECK_STATUS_URL.rstrip('/')}/{client_transaction_id}"

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            print(f"ERROR Payphone status {client_transaction_id}: HTTP {response.status_code} - {response.text[:200]}")
            return None

        data = response.json()

        # Payphone devuelve el estado en distintos campos según el flujo.
        # Para API Sale/client, el campo puede ser 'status' o 'transactionStatus'.
        # Los valores posibles: "Aceptado", "Cancelado", "Pendiente".
        status_raw = (
            data.get("status") or
            data.get("transactionStatus") or
            data.get("StatusCode") or
            data.get("statusCode")
        )

        if status_raw is None:
            print(f"WARN Payphone status {client_transaction_id}: respuesta sin estado: {data}")
            return None

        # Normalizar a int para el resto del código:
        # 3 = Aprobado, 2 = Rechazado, 1 = Pendiente
        if isinstance(status_raw, str):
            status_lower = status_raw.lower()
            if "aceptado" in status_lower or "aprobado" in status_lower or "approved" in status_lower:
                return 3
            elif "cancelado" in status_lower or "rechazado" in status_lower or "rejected" in status_lower:
                return 2
            else:
                return 1  # Pendiente o desconocido
        else:
            return int(status_raw)

    except Exception as e:
        print(f"ERROR consultando estado Payphone {client_transaction_id}: {str(e)}")
        return None


def _conciliar_pendientes(cursor, conexion):
    """
    FASE 1: Busca PAYPHONE_PENDING con más de 2 minutos y consulta a Payphone.
    Actualiza el estado según la respuesta.
    Devuelve (conciliadas, rechazadas, errores).
    """
    conciliadas = 0
    rechazadas = 0
    errores = 0

    # Buscar pendientes con más de 2 minutos de antigüedad
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
        status_code = _consultar_estado_payphone(temp_id)

        if status_code == 3:
            # Aprobado
            cursor.execute("""
                UPDATE pending_transfers
                SET status = 'PAYPHONE_CONFIRMED', updated_at = NOW()
                WHERE id = %s AND status = 'PAYPHONE_PENDING'
            """, (temp_id,))
            conexion.commit()
            conciliadas += 1
            print(f"CONCILIADO: {temp_id} -> PAYPHONE_CONFIRMED")

        elif status_code == 2:
            # Rechazado/Cancelado
            cursor.execute("""
                UPDATE pending_transfers
                SET status = 'PAYPHONE_REJECTED', updated_at = NOW()
                WHERE id = %s AND status = 'PAYPHONE_PENDING'
            """, (temp_id,))
            conexion.commit()
            rechazadas += 1
            print(f"RECHAZADO: {temp_id} -> PAYPHONE_REJECTED")

            # Notificar al cliente (si tenemos su whatsapp en el snapshot)
            cursor.execute("""
                SELECT customer_whatsapp, order_details_snapshot
                FROM pending_transfers WHERE id = %s
            """, (temp_id,))
            fila_info = cursor.fetchone()
            if fila_info and fila_info[0]:
                cliente_whatsapp = fila_info[0]
                snapshot = fila_info[1] or {}
                pedido_id = snapshot.get("pedido_id", "?")
                cursor.execute("""
                    INSERT INTO notificaciones_pendientes
                        (destinatario_whatsapp, mensaje, enviado)
                    VALUES (%s, %s, FALSE)
                """, (
                    cliente_whatsapp,
                    f"❌ El pago de tu pedido #{pedido_id} no se pudo procesar. "
                    f"Puedes intentar con otro método de pago o contactarnos.",
                ))
                conexion.commit()

        else:
            # StatusCode desconocido o error: dejar en PAYPHONE_PENDING para reintentar
            errores += 1
            print(f"PENDIENTE (status={status_code}): {temp_id}")

    return conciliadas, rechazadas, errores


def _procesar_confirmadas(cursor, conexion):
    """
    FASE 2: Procesa filas PAYPHONE_CONFIRMED.
    Devuelve (procesadas, errores, detalle).
    """
    procesadas = 0
    errores = 0
    detalle = []

    cursor.execute("""
        SELECT id, customer_whatsapp, order_details_snapshot
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

        pedido_id = snapshot.get("pedido_id")
        monto = snapshot.get("monto")
        ubicacion_id = snapshot.get("ubicacion_id", 1)

        if not pedido_id or monto is None:
            errores += 1
            detalle.append({"temp_id": temp_id, "error": "snapshot incompleto"})
            cursor.execute("""
                UPDATE pending_transfers SET status = 'PAYPHONE_ORDER_ERROR', updated_at = NOW()
                WHERE id = %s
            """, (temp_id,))
            conexion.commit()
            continue

        try:
            resultado_pago = registrar_pago(
                pedido_id=int(pedido_id),
                metodo="tarjeta",
                monto=float(monto),
                banco_id=None,
                autorizacion=f"PAYPHONE-{temp_id}",
                ubicacion_id=int(ubicacion_id),
            )

            if isinstance(resultado_pago, str) and resultado_pago.startswith("Error"):
                raise Exception(f"registrar_pago falló: {resultado_pago}")

            # Notificar al admin
            admin_whatsapp = obtener_admin_pedido(int(ubicacion_id))
            if admin_whatsapp and not (isinstance(admin_whatsapp, str) and admin_whatsapp.startswith("Error")):
                notificar_admin_pedido(int(pedido_id), admin_whatsapp)

            # Notificar al cliente
            if customer_whatsapp:
                cursor.execute("""
                    INSERT INTO notificaciones_pendientes
                        (destinatario_whatsapp, mensaje, enviado)
                    VALUES (%s, %s, FALSE)
                """, (
                    customer_whatsapp,
                    f"✅ Pago con tarjeta confirmado. Tu pedido #{pedido_id} está en preparación. "
                    f"No necesitas enviar comprobante; el pago es automático. ¡Gracias!",
                ))

            cursor.execute("""
                UPDATE pending_transfers SET status = 'PAYPHONE_ORDER_CREATED', updated_at = NOW()
                WHERE id = %s
            """, (temp_id,))
            conexion.commit()

            procesadas += 1
            detalle.append({"temp_id": temp_id, "pedido_id": pedido_id, "estado": "ok"})

        except Exception as e:
            errores += 1
            detalle.append({"temp_id": temp_id, "pedido_id": pedido_id, "error": str(e)})
            try:
                conexion.rollback()
            except Exception:
                pass
            cursor.execute("""
                UPDATE pending_transfers SET status = 'PAYPHONE_ORDER_ERROR', updated_at = NOW()
                WHERE id = %s
            """, (temp_id,))
            conexion.commit()

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
    errores = 0
    detalle = []

    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # FASE 1
        conciliadas, rechazadas, errores_conc = _conciliar_pendientes(cursor, conexion)

        # FASE 2
        procesadas, errores_proc, detalle_proc = _procesar_confirmadas(cursor, conexion)

        return {
            "conciliadas": conciliadas,
            "rechazadas": rechazadas,
            "procesadas": procesadas,
            "errores": errores_conc + errores_proc,
            "detalle": detalle_proc,
        }

    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return {
            "conciliadas": conciliadas,
            "rechazadas": rechazadas,
            "procesadas": procesadas,
            "errores": errores + 1,
            "detalle": detalle + [{"error_global": str(e)}],
        }
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass