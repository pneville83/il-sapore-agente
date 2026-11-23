import os
import requests
import psycopg2
import psycopg2.extras
import uuid
from app.core.config import DATABASE_URL, PAYPHONE_API_KEY, PAYPHONE_STORE_ID, PAYPHONE_GENERATE_LINK_URL

def generar_link_pago(monto, client_transaction_id, referencia):
    """
    Genera un link de pago con Payphone.
    
    monto: cantidad en dólares (ej: 25.50)
    client_transaction_id: ID único (máx 15 caracteres)
    referencia: descripción del pedido
    """
    try:
        monto_centavos = int(round(monto * 100))
        
        payload = {
            "amount": monto_centavos,
            "amountWithoutTax": monto_centavos,
            "amountWithTax": 0,
            "tax": 0,
            "service": 0,
            "tip": 0,
            "currency": "USD",
            "reference": referencia,
            "clientTransactionId": client_transaction_id,
            "storeId": PAYPHONE_STORE_ID
        }
        
        headers = {
            "Authorization": f"Bearer {PAYPHONE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(PAYPHONE_GENERATE_LINK_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            link = response.text.strip()
            if link.startswith("https://"):
                return {"link": link, "mensaje": "Link generado correctamente"}
            else:
                return f"Error: respuesta inesperada de Payphone: {link}"
        else:
            return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error al generar link de pago: {str(e)}"


# ============================================================
# NUEVA: genera link + inserta pending_transfers en una transacción
# ============================================================

def generar_link_pago_con_pending(pedido_id, ubicacion_id=None):
    """
    Genera un link de Payphone para un pedido existente y registra la
    transacción pendiente en pending_transfers con status='PAYPHONE_PENDING'.
    
    - Lee el total y la ubicación del pedido en la BD (no confía en el LLM).
    - Genera client_transaction_id desde Python (no lo inventa el LLM).
    - Inserta en pending_transfers ANTES de generar el link, para que si el
      link falla, la fila quede en PAYPHONE_PENDING y se pueda reintentar.
    - Devuelve {estado, link, client_transaction_id, pedido_id, monto}.
    """
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # 1. Leer pedido (no confiar en el LLM para el monto)
        cursor.execute("""
            SELECT p.id, p.total, p.ubicacion_id, p.metodo_pago, p.estado,
                   c.whatsapp
            FROM pedidos p
            LEFT JOIN clientes c ON c.id = p.cliente_id
            WHERE p.id = %s
        """, (pedido_id,))
        fila = cursor.fetchone()
        if not fila:
            return f"Error: pedido #{pedido_id} no existe."

        pid, total, ubicacion_pedido, metodo_actual, estado, cliente_whatsapp = fila

        if metodo_actual != "tarjeta":
            return f"Error: el pedido #{pedido_id} tiene metodo_pago='{metodo_actual}', no 'tarjeta'."
        if estado != "Recibido":
            return f"Error: el pedido #{pedido_id} está en estado '{estado}', no se puede pagar con tarjeta."

        ubicacion_final = ubicacion_id or ubicacion_pedido

        # 2. Generar client_transaction_id único (15 chars)
        # Formato: PH + 13 hex chars (uuid4). Ej: PH3A4B5C6D7E8F9
        client_transaction_id = f"PH{uuid.uuid4().hex[:13].upper()}"

        # 3. Insertar en pending_transfers ANTES de generar el link
        snapshot = {
            "pedido_id": int(pid),
            "monto": float(total),
            "ubicacion_id": int(ubicacion_final),
        }
        cursor.execute("""
            INSERT INTO pending_transfers
                (id, customer_whatsapp, customer_name, media_data,
                 convo_state_snapshot, order_details_snapshot, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'PAYPHONE_PENDING')
        """, (
            client_transaction_id,
            cliente_whatsapp or "",
            "",
            None,
            None,
            psycopg2.extras.Json(snapshot),
        ))
                
        conexion.commit()

        # 4. Generar el link con Payphone
        referencia = f"Pedido #{pid}"
        resultado_link = generar_link_pago(
            monto=float(total),
            client_transaction_id=client_transaction_id,
            referencia=referencia,
        )

        if isinstance(resultado_link, dict) and resultado_link.get("link"):
            return {
                "estado": "ok",
                "pedido_id": int(pid),
                "monto": float(total),
                "ubicacion_id": int(ubicacion_final),
                "client_transaction_id": client_transaction_id,
                "link": resultado_link["link"],
                "mensaje": f"Link generado para pedido #{pid}. Total: ${float(total):.2f}.",
            }
        else:
            # El link falló: dejamos la fila en PAYPHONE_PENDING y reportamos.
            # Se puede reintentar borrando la fila o esperando a que el link se regenere.
            return {
                "estado": "error_link",
                "pedido_id": int(pid),
                "client_transaction_id": client_transaction_id,
                "detalle": resultado_link,
                "mensaje": f"Se registró la transacción {client_transaction_id} pero falló la generación del link. Detalle: {resultado_link}",
            }

    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return f"Error al generar link con pending: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass


def registrar_pago(pedido_id, metodo, monto, banco_id=None, autorizacion=None, ubicacion_id=1):
    """
    Registra un pago.
    
    metodo: "efectivo", "transferencia", "tarjeta"
    banco_id: solo si es transferencia
    autorizacion: código de autorización (para transferencias, tú lo das)
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        descripcion = f"Pago de pedido #{pedido_id} - {metodo}"
        cuenta = autorizacion or "N/A"
        
        cursor.execute("""
            INSERT INTO transacciones (pedido_id, tipo, monto, banco_id, descripcion, cuenta, ubicacion_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, fecha
        """, (pedido_id, metodo, monto, banco_id, descripcion, cuenta, ubicacion_id))
        
        fila = cursor.fetchone()
        conexion.commit()
        conexion.close()
        
        return {
            "id": fila[0],
            "fecha": fila[1],
            "pedido_id": pedido_id,
            "metodo": metodo,
            "monto": monto,
            "banco_id": banco_id,
            "autorizacion": autorizacion,
            "mensaje": "Pago registrado correctamente"
        }
    except Exception as e:
        return f"Error al registrar pago: {str(e)}"


def consultar_bancos():
    """
    Devuelve la lista de bancos disponibles.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        cursor.execute("SELECT id, nombre FROM bancos ORDER BY nombre")
        filas = cursor.fetchall()
        columnas = [desc[0] for desc in cursor.description]
        resultado = [dict(zip(columnas, fila)) for fila in filas]
        conexion.close()
        return resultado
    except Exception as e:
        return f"Error al consultar bancos: {str(e)}"
    
def crear_transferencia_pendiente(pedido_id, cliente_whatsapp, cliente_nombre, media_base64, monto, banco_id=None, ubicacion_id=1):
    """
    Guarda una transferencia pendiente de autorización.
    El admin (tú) recibirá la foto y decidirá si autoriza.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        # Generar un ID corto (4 caracteres)
        import uuid
        temp_id = str(uuid.uuid4())[:4].upper()
        
        cursor.execute("""
            INSERT INTO pending_transfers 
            (id, customer_whatsapp, customer_name, media_data, order_details_snapshot, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            temp_id,
            cliente_whatsapp,
            cliente_nombre,
            media_base64,
            f'{{"pedido_id": {pedido_id}, "monto": {monto}, "banco_id": {banco_id}, "ubicacion_id": {ubicacion_id}}}',
            "ESPERANDO_AUTORIZACION"
        ))
        
        fila = cursor.fetchone()
        conexion.commit()
        conexion.close()
        
        return {
            "id": fila[0],
            "pedido_id": pedido_id,
            "cliente": cliente_nombre,
            "monto": monto,
            "estado": "ESPERANDO_AUTORIZACION",
            "mensaje": f"Transferencia pendiente creada. ID: {fila[0]}. El admin debe autorizar."
        }
    except Exception as e:
        return f"Error al crear transferencia pendiente: {str(e)}"


def autorizar_transferencia(temp_id, autorizado, autorizacion=None):
    """
    Autoriza o rechaza una transferencia pendiente.
    - Si temp_id es None o "ultima", busca la más reciente con status='ESPERANDO_AUTORIZACION'.
    - Si autoriza: registra pago, actualiza status a CONFIRMED, y notifica al admin
      si el cliente era confiable=False (porque no se notificó al crear el pedido).
    - Si rechaza: actualiza status a REJECTED. No notifica.
    """
    from app.tools.pedidos import obtener_admin_pedido, notificar_admin_pedido

    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # 1. Resolver temp_id si viene None o "ultima"
        if not temp_id or str(temp_id).lower() == "ultima":
            cursor.execute("""
                SELECT id FROM pending_transfers
                WHERE status = 'ESPERANDO_AUTORIZACION'
                ORDER BY created_at DESC
                LIMIT 1
            """)
            fila_ultima = cursor.fetchone()
            if not fila_ultima:
                return "Error: No hay transferencias pendientes de autorización."
            temp_id = fila_ultima[0]

        # 2. Buscar la transferencia
        cursor.execute("""
            SELECT order_details_snapshot, customer_whatsapp, customer_name
            FROM pending_transfers
            WHERE id = %s AND status = 'ESPERANDO_AUTORIZACION'
        """, (temp_id,))
        fila = cursor.fetchone()

        if not fila:
            return f"Error: No se encontró la transferencia {temp_id} o ya fue procesada."

        detalles = fila[0]
        cliente_whatsapp = fila[1]
        cliente_nombre = fila[2]
        pedido_id = detalles["pedido_id"]
        monto = detalles["monto"]
        banco_id = detalles.get("banco_id")
        ubicacion_id = detalles.get("ubicacion_id", 1)

        if autorizado:
            # 3. Registrar pago
            resultado_pago = registrar_pago(
                pedido_id=pedido_id,
                metodo="transferencia",
                monto=monto,
                banco_id=banco_id,
                autorizacion=autorizacion or f"AUT-{temp_id}",
                ubicacion_id=ubicacion_id
            )

            # 4. Actualizar estado a CONFIRMED
            cursor.execute("""
                UPDATE pending_transfers
                SET status = 'CONFIRMED', updated_at = NOW()
                WHERE id = %s
            """, (temp_id,))
            conexion.commit()

            # 5. Notificar al admin SI el cliente era no confiable
            admin_notificado = False
            admin_whatsapp = None
            try:
                cursor.execute("""
                    SELECT c.confiable FROM pedidos p
                    JOIN clientes c ON c.id = p.cliente_id
                    WHERE p.id = %s
                """, (pedido_id,))
                fila_conf = cursor.fetchone()
                confiable = fila_conf[0] if fila_conf else True

                if not confiable:
                    admin_whatsapp = obtener_admin_pedido(ubicacion_id)
                    if admin_whatsapp and not (isinstance(admin_whatsapp, str) and admin_whatsapp.startswith("Error")):
                        notificar_admin_pedido(pedido_id, admin_whatsapp)
                        admin_notificado = True
                        print(f"DEBUG autorizar: cliente no confiable -> admin {admin_whatsapp} notificado del pedido #{pedido_id}")
            except Exception as e:
                print(f"DEBUG autorizar: error al notificar admin: {e}")

            return {
                "estado": "CONFIRMED",
                "temp_id": temp_id,
                "pedido_id": pedido_id,
                "pago": resultado_pago,
                "admin_notificado": admin_notificado,
                "admin_whatsapp": admin_whatsapp,
                "mensaje": (
                    f"Transferencia {temp_id} autorizada. Pago registrado."
                    + (f" Admin notificado del pedido #{pedido_id}." if admin_notificado else "")
                ),
            }
        else:
            # 6. Rechazar
            cursor.execute("""
                UPDATE pending_transfers
                SET status = 'REJECTED', updated_at = NOW()
                WHERE id = %s
            """, (temp_id,))
            conexion.commit()

            return {
                "estado": "REJECTED",
                "temp_id": temp_id,
                "pedido_id": pedido_id,
                "mensaje": f"Transferencia {temp_id} rechazada. El pedido #{pedido_id} no se preparará.",
            }
    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return f"Error al autorizar transferencia: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass