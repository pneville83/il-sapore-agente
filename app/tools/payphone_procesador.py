# app/tools/payphone_procesador.py
"""
Procesador de pagos Payphone confirmados.

Busca filas en pending_transfers con status='PAYPHONE_CONFIRMED' (que deja
el servicio externo ilsapore-pos-backend cuando Payphone confirma el pago)
y las convierte en:
  - transacciones (registrar_pago)
  - notificaciones_pendientes (admin + cliente)
  - status='PAYPHONE_ORDER_CREATED' (idempotente)

Se invoca desde POST /payphone/procesar_pendientes (UptimeRobot cada 2-3 min).
"""
import psycopg2
from app.core.config import DATABASE_URL
from app.tools.pagos import registrar_pago
from app.tools.pedidos import obtener_admin_pedido, notificar_admin_pedido


def procesar_pendientes_payphone():
    """
    Procesa todas las filas PAYPHONE_CONFIRMED pendientes.
    Devuelve {procesadas, errores, detalle: [...]}.
    Idempotente: si una fila ya está en PAYPHONE_ORDER_CREATED, no se toca.
    """
    conexion = None
    cursor = None
    procesadas = 0
    errores = 0
    detalle = []

    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # 1. Buscar pendientes confirmadas por Payphone
        cursor.execute("""
            SELECT id, customer_whatsapp, order_details_snapshot, status
            FROM pending_transfers
            WHERE status = 'PAYPHONE_CONFIRMED'
            ORDER BY updated_at ASC
            LIMIT 50
        """)
        filas = cursor.fetchall()

        if not filas:
            return {"procesadas": 0, "errores": 0, "detalle": []}

        for fila in filas:
            temp_id = fila[0]
            customer_whatsapp = fila[1] or ""
            snapshot = fila[2] or {}

            pedido_id = snapshot.get("pedido_id")
            monto = snapshot.get("monto")
            ubicacion_id = snapshot.get("ubicacion_id", 1)

            if not pedido_id or monto is None:
                errores += 1
                detalle.append({
                    "temp_id": temp_id,
                    "error": f"snapshot incompleto: pedido_id={pedido_id}, monto={monto}",
                })
                # Marcar como error para no reintentar indefinidamente
                cursor.execute("""
                    UPDATE pending_transfers
                    SET status = 'PAYPHONE_ORDER_ERROR', updated_at = NOW()
                    WHERE id = %s
                """, (temp_id,))
                conexion.commit()
                continue

            try:
                # 2. Registrar pago
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

                # 3. Notificar al admin
                admin_whatsapp = obtener_admin_pedido(int(ubicacion_id))
                if admin_whatsapp and not (isinstance(admin_whatsapp, str) and admin_whatsapp.startswith("Error")):
                    notificar_admin_pedido(int(pedido_id), admin_whatsapp)

                # 4. Notificar al cliente (si tenemos su whatsapp)
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

                # 5. Marcar como procesada (idempotencia)
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
                    "estado": "ok",
                })

            except Exception as e:
                errores += 1
                detalle.append({
                    "temp_id": temp_id,
                    "pedido_id": pedido_id,
                    "error": str(e),
                })
                try:
                    conexion.rollback()
                except Exception:
                    pass
                # Marcar como error para no reintentar indefinidamente
                cursor.execute("""
                    UPDATE pending_transfers
                    SET status = 'PAYPHONE_ORDER_ERROR', updated_at = NOW()
                    WHERE id = %s
                """, (temp_id,))
                conexion.commit()

        return {"procesadas": procesadas, "errores": errores, "detalle": detalle}

    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return {"procesadas": procesadas, "errores": errores + 1, "detalle": detalle + [{"error_global": str(e)}]}
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass