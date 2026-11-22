# app/tools/pedidos.py
import psycopg2
from app.core.config import DATABASE_URL
from app.tools.clientes import buscar_o_crear_cliente


# ============================================================
# ADMIN A NOTIFICAR
# ============================================================

def obtener_admin_pedido(ubicacion_id: int):
    """
    Devuelve el whatsapp del admin a notificar un pedido normal
    en esa ubicación. Excluye el número del bot (ubicaciones.whatsapp_bot).
    Si no hay admin con número personal, cae al superadmin.
    Devuelve str (whatsapp) o None si no hay ninguno.
    """
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT u.whatsapp
            FROM usuarios u
            JOIN ubicaciones ub ON ub.id = u.ubicacion_id
            WHERE u.ubicacion_id = %s
              AND u.rol = 'admin'
              AND u.whatsapp IS NOT NULL
              AND u.whatsapp != COALESCE(ub.whatsapp_bot, '')
            LIMIT 1
        """, (ubicacion_id,))
        fila = cursor.fetchone()
        if fila and fila[0]:
            return fila[0]

        cursor.execute("""
            SELECT whatsapp FROM usuarios
            WHERE rol = 'superadmin' AND whatsapp IS NOT NULL
            LIMIT 1
        """)
        fila = cursor.fetchone()
        if fila and fila[0]:
            return fila[0]

        return None
    except Exception as e:
        return f"Error al obtener admin de pedido: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception:
            pass


def obtener_admin_transferencia():
    """
    SIEMPRE devuelve el whatsapp del superadmin.
    Devuelve str o None.
    """
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        cursor.execute("""
            SELECT whatsapp FROM usuarios
            WHERE rol = 'superadmin' AND whatsapp IS NOT NULL
            LIMIT 1
        """)
        fila = cursor.fetchone()
        return fila[0] if fila and fila[0] else None
    except Exception as e:
        return f"Error al obtener admin de transferencia: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception:
            pass


# ============================================================
# ETAPAS DESHABILITADAS
# ============================================================

def deshabilitar_etapa(etapa: str, ubicacion_id: int):
    """Añade una etapa a la lista negra de esa ubicación."""
    if not etapa:
        return "Error: falta el nombre de la etapa."
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO etapas_deshabilitadas (ubicacion_id, nombre)
            VALUES (%s, %s)
            ON CONFLICT (ubicacion_id, nombre) DO NOTHING
            RETURNING id
        """, (ubicacion_id, etapa.strip()))
        fila = cursor.fetchone()
        conexion.commit()
        if fila:
            return {"estado": "ok", "mensaje": f"Etapa '{etapa}' deshabilitada para ubicación {ubicacion_id}."}
        return {"estado": "ok", "mensaje": f"La etapa '{etapa}' ya estaba deshabilitada."}
    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return f"Error al deshabilitar etapa: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass


def habilitar_etapa(etapa: str, ubicacion_id: int):
    """Quita una etapa de la lista negra de esa ubicación."""
    if not etapa:
        return "Error: falta el nombre de la etapa."
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        cursor.execute("""
            DELETE FROM etapas_deshabilitadas
            WHERE ubicacion_id = %s AND LOWER(nombre) = LOWER(%s)
            RETURNING id
        """, (ubicacion_id, etapa.strip()))
        fila = cursor.fetchone()
        conexion.commit()
        if fila:
            return {"estado": "ok", "mensaje": f"Etapa '{etapa}' habilitada para ubicación {ubicacion_id}."}
        return {"estado": "ok", "mensaje": f"La etapa '{etapa}' no estaba deshabilitada."}
    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return f"Error al habilitar etapa: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass


def _etapa_deshabilitada(etapa: str, ubicacion_id: int, cursor):
    """Helper interno: True si la etapa está en la lista negra."""
    if not etapa:
        return False
    cursor.execute("""
        SELECT 1 FROM etapas_deshabilitadas
        WHERE ubicacion_id = %s AND LOWER(nombre) = LOWER(%s)
        LIMIT 1
    """, (ubicacion_id, etapa.strip()))
    return cursor.fetchone() is not None


# ============================================================
# CREAR PEDIDO
# ============================================================

def crear_pedido(
    whatsapp_cliente: str,
    ubicacion_id: int,
    metodo_pago: str,
    items: list,
    whatsapp_lid: str | None = None,
    nombre_cliente: str | None = None,
    direccion_mz: str | None = None,
    direccion_villa: str | None = None,
    etapa: str | None = None,
    observaciones: str = "",
):
    """
    Crea pedido + detalles_pedido de forma transaccional.
    NO notifica. NO genera link de pago. Eso lo hace el orquestador.
    """

    # 1. Validar método de pago
    if metodo_pago not in ("efectivo", "transferencia", "tarjeta"):
        return f"Error: metodo_pago inválido ('{metodo_pago}'). Debe ser efectivo, transferencia o tarjeta."

    # 2. Validar items
    if not items or not isinstance(items, list):
        return "Error: el pedido no tiene items."

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            return f"Error: item {idx} no es un diccionario."
        if item.get("cantidad") is None or int(item.get("cantidad", 0)) <= 0:
            return f"Error: item {idx} tiene cantidad inválida."
        if item.get("variacion_id") is None and item.get("producto_id") is None:
            return f"Error: item {idx} no tiene ni producto_id ni variacion_id."

    # 3. Buscar/crear cliente
    resultado_cliente = buscar_o_crear_cliente(
        whatsapp=whatsapp_cliente,
        whatsapp_lid=whatsapp_lid,
        nombre=nombre_cliente,
        direccion_mz=direccion_mz,
        direccion_villa=direccion_villa,
        etapa=etapa,
    )

    if isinstance(resultado_cliente, str):
        return resultado_cliente

    if resultado_cliente.get("estado") == "faltan_datos":
        return {
            "estado": "faltan_datos_cliente",
            "pedido_id": None,
            "total": None,
            "cliente_id": None,
            "confiable": None,
            "campos_faltantes": resultado_cliente.get("campos_faltantes", []),
            "mensaje": resultado_cliente.get("mensaje", ""),
        }

    cliente_id = resultado_cliente["cliente_id"]
    confiable = resultado_cliente["confiable"]

    # Snapshot de dirección y etapa: prioriza parámetros, luego los del cliente
    dir_mz_final = direccion_mz or resultado_cliente.get("direccion_mz")
    dir_villa_final = direccion_villa or resultado_cliente.get("direccion_villa")
    etapa_final = etapa or resultado_cliente.get("etapa")

    # 4. Resolver items y precios
    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # 4-pre. Validar etapa habilitada
        if _etapa_deshabilitada(etapa_final, ubicacion_id, cursor):
            conexion.rollback()
            return {
                "estado": "etapa_no_habilitada",
                "pedido_id": None, "total": None,
                "cliente_id": cliente_id, "confiable": confiable,
                "mensaje": f"Hoy no hay despacho a la etapa '{etapa_final}'.",
            }

        items_resueltos = []
        total = 0.0

        for idx, item in enumerate(items):
            variacion_id = item.get("variacion_id")
            producto_id = item.get("producto_id")
            cantidad = int(item["cantidad"])

            nombre_variacion = None
            if variacion_id is not None:
                cursor.execute("""
                    SELECT v.producto_id, v.nombre_variacion, p.disponible, p.nombre
                    FROM variaciones_producto v
                    JOIN productos p ON p.id = v.producto_id
                    WHERE v.id = %s
                """, (variacion_id,))
                fila_var = cursor.fetchone()
                if not fila_var:
                    conexion.rollback()
                    return {
                        "estado": "producto_no_existe",
                        "pedido_id": None, "total": None,
                        "cliente_id": cliente_id, "confiable": confiable,
                        "mensaje": f"La variante {variacion_id} no existe.",
                    }
                producto_id = fila_var[0]
                nombre_variacion = fila_var[1]
                disponible = fila_var[2]
                nombre_producto = fila_var[3]
            else:
                cursor.execute("""
                    SELECT disponible, nombre FROM productos WHERE id = %s
                """, (producto_id,))
                fila_prod = cursor.fetchone()
                if not fila_prod:
                    conexion.rollback()
                    return {
                        "estado": "producto_no_existe",
                        "pedido_id": None, "total": None,
                        "cliente_id": cliente_id, "confiable": confiable,
                        "mensaje": f"El producto {producto_id} no existe.",
                    }
                disponible = fila_prod[0]
                nombre_producto = fila_prod[1]

            if not disponible:
                conexion.rollback()
                return {
                    "estado": "producto_no_existe",
                    "pedido_id": None, "total": None,
                    "cliente_id": cliente_id, "confiable": confiable,
                    "mensaje": f"{nombre_producto} no está disponible hoy.",
                }

            if variacion_id is not None:
                cursor.execute("""
                    SELECT precio FROM precios_ubicacion
                    WHERE variacion_id = %s AND ubicacion_id = %s
                    LIMIT 1
                """, (variacion_id, ubicacion_id))
            else:
                cursor.execute("""
                    SELECT precio FROM precios_ubicacion
                    WHERE producto_id = %s
                      AND variacion_id IS NULL
                      AND ubicacion_id = %s
                    LIMIT 1
                """, (producto_id, ubicacion_id))

            fila_precio = cursor.fetchone()
            if not fila_precio:
                conexion.rollback()
                return {
                    "estado": "precio_no_disponible",
                    "pedido_id": None, "total": None,
                    "cliente_id": cliente_id, "confiable": confiable,
                    "mensaje": f"No hay precio configurado para {nombre_producto}"
                               + (f" ({nombre_variacion})" if nombre_variacion else "")
                               + " en esta sucursal.",
                }

            precio_unitario = float(fila_precio[0])
            subtotal = precio_unitario * cantidad
            total += subtotal

            items_resueltos.append({
                "producto_id": producto_id,
                "variacion_id": variacion_id,
                "nombre_variacion": nombre_variacion,
                "cantidad": cantidad,
                "precio_unitario": precio_unitario,
                "subtotal": subtotal,
            })

        # 5. INSERT pedido (con snapshot de etapa y dirección)
        cursor.execute("""
            INSERT INTO pedidos
                (cliente_id, ubicacion_id, metodo_pago, total, estado,
                 observaciones, direccion_mz, direccion_villa, etapa)
            VALUES (%s, %s, %s, %s, 'Recibido', %s, %s, %s, %s)
            RETURNING id
        """, (
            cliente_id, ubicacion_id, metodo_pago, total,
            observaciones or "",
            dir_mz_final, dir_villa_final, etapa_final,
        ))
        pedido_id = cursor.fetchone()[0]

        # 6. INSERT detalles
        for it in items_resueltos:
            cursor.execute("""
                INSERT INTO detalles_pedido
                    (pedido_id, producto_id, variacion_id, cantidad,
                     precio_unitario, nombre_variacion)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                pedido_id, it["producto_id"], it["variacion_id"],
                it["cantidad"], it["precio_unitario"], it["nombre_variacion"],
            ))

        conexion.commit()

        return {
            "estado": "ok",
            "pedido_id": pedido_id,
            "total": total,
            "cliente_id": cliente_id,
            "confiable": confiable,
            "mensaje": f"Pedido #{pedido_id} creado. Total: ${total:.2f}.",
        }

    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return f"Error al crear pedido: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception:
            pass

# ============================================================
# ORQUESTAR PEDIDO (decide a quién notificar según método de pago)
# ============================================================

def orquestar_pedido(pedido_id: int, metodo_pago: str, confiable: bool, ubicacion_id: int):
    """
    Después de crear_pedido exitoso, decide si notificar al admin ahora o esperar.
    - Efectivo: notifica ya.
    - Tarjeta: NO notifica (espera webhook Payphone).
    - Transferencia confiable: notifica ya (admin prepara, espera OK del superadmin para despachar).
    - Transferencia no confiable: NO notifica (espera autorización del superadmin).
    Devuelve dict con la acción tomada.
    """
    if metodo_pago == "efectivo":
        admin = obtener_admin_pedido(ubicacion_id)
        if isinstance(admin, str) and admin.startswith("Error"):
            return {"estado": "error", "mensaje": admin}
        resultado = notificar_admin_pedido(pedido_id, admin)
        print(f"DEBUG orquestar_pedido: efectivo -> notificado a {admin}")
        return {
            "accion": "notificado_efectivo",
            "admin": admin,
            "detalle": resultado,
        }

    elif metodo_pago == "tarjeta":
        # No notificar todavía. El webhook de Payphone lo hará.
        print(f"DEBUG orquestar_pedido: tarjeta -> esperando webhook Payphone")
        return {
            "accion": "esperando_payphone",
            "mensaje": "Pedido creado. Esperando confirmación de Payphone.",
        }

    elif metodo_pago == "transferencia":
        if confiable:
            admin = obtener_admin_pedido(ubicacion_id)
            if isinstance(admin, str) and admin.startswith("Error"):
                return {"estado": "error", "mensaje": admin}
            resultado = notificar_admin_pedido(pedido_id, admin)
            print(f"DEBUG orquestar_pedido: transferencia confiable -> notificado a {admin}")
            return {
                "accion": "notificado_transferencia_confiable",
                "admin": admin,
                "detalle": resultado,
                "mensaje": "Pedido creado. Admin notificado. Esperando comprobante y autorización del superadmin.",
            }
        else:
            # No notificar. Esperar autorización del superadmin.
            print(f"DEBUG orquestar_pedido: transferencia NO confiable -> esperando autorización del superadmin")
            return {
                "accion": "esperando_autorizacion",
                "mensaje": "Pedido creado. NO notificado al admin. Esperando comprobante y autorización del superadmin.",
            }

    else:
        return {"estado": "error", "mensaje": f"metodo_pago inválido: {metodo_pago}"} 
    
# ============================================================
# NOTIFICAR ADMIN
# ============================================================

def notificar_admin_pedido(pedido_id: int, admin_whatsapp: str):
    """
    Encola en notificaciones_pendientes un mensaje para el admin.
    El bot lo leerá y enviará.
    """
    if not admin_whatsapp:
        return "Error: no hay admin_whatsapp para notificar."

    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT p.id, p.total, p.metodo_pago, p.observaciones,
                   p.direccion_mz, p.direccion_villa, p.etapa,
                   c.nombre
            FROM pedidos p
            LEFT JOIN clientes c ON c.id = p.cliente_id
            WHERE p.id = %s
        """, (pedido_id,))
        fila = cursor.fetchone()
        if not fila:
            return f"Error: pedido #{pedido_id} no existe."

        pid, total, metodo, obs, mz, villa, etapa_ped, cliente_nombre = fila

        mensaje = (
            f"Nuevo pedido #{pid} - Cliente: {cliente_nombre or 'sin nombre'} - "
            f"Total: ${float(total):.2f} - Pago: {metodo} - "
            f"Dir: Mz {mz or '?'} Villa {villa or '?'}"
        )
        if etapa_ped:
            mensaje += f" - Etapa: {etapa_ped}"
        if obs:
            mensaje += f" - Obs: {obs}"

        cursor.execute("""
            INSERT INTO notificaciones_pendientes
                (destinatario_whatsapp, mensaje, enviado)
            VALUES (%s, %s, FALSE)
            RETURNING id
        """, (admin_whatsapp, mensaje))
        notif_id = cursor.fetchone()[0]
        conexion.commit()

        return {
            "estado": "ok",
            "notificacion_id": notif_id,
            "mensaje": f"Notificación encolada para {admin_whatsapp}.",
        }

    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return f"Error al notificar admin: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception:
            pass


# ============================================================
# CAMBIAR MÉTODO DE PAGO DE UN PEDIDO EXISTENTE
# ============================================================

def cambiar_metodo_pago_pedido(pedido_id: int, nuevo_metodo: str):
    """
    Cambia el método de pago de un pedido existente (solo si estado='Recibido'
    y no tiene transacción registrada). Luego re-orquesta para notificar
    al admin según el nuevo método.
    """
    if nuevo_metodo not in ("efectivo", "transferencia", "tarjeta"):
        return f"Error: metodo_pago inválido ('{nuevo_metodo}'). Debe ser efectivo, transferencia o tarjeta."

    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # 1. Verificar pedido
        cursor.execute("""
            SELECT p.id, p.metodo_pago, p.estado, p.ubicacion_id, p.cliente_id,
                   c.confiable
            FROM pedidos p
            LEFT JOIN clientes c ON c.id = p.cliente_id
            WHERE p.id = %s
        """, (pedido_id,))
        fila = cursor.fetchone()
        if not fila:
            return f"Error: pedido #{pedido_id} no existe."

        pid, metodo_actual, estado, ubicacion_id, cliente_id, confiable = fila

        if estado != "Recibido":
            return f"Error: el pedido #{pedido_id} ya está en estado '{estado}'. No se puede cambiar el método de pago."

        if metodo_actual == nuevo_metodo:
            return {
                "estado": "sin_cambio",
                "pedido_id": pedido_id,
                "metodo_pago": nuevo_metodo,
                "mensaje": f"El pedido #{pedido_id} ya estaba en '{nuevo_metodo}'.",
            }

        # 2. Verificar que no tenga transacción
        cursor.execute("SELECT COUNT(*) FROM transacciones WHERE pedido_id = %s", (pedido_id,))
        if cursor.fetchone()[0] > 0:
            return f"Error: el pedido #{pedido_id} ya tiene un pago registrado. No se puede cambiar el método."

        # 3. Actualizar
        cursor.execute("""
            UPDATE pedidos SET metodo_pago = %s WHERE id = %s
        """, (nuevo_metodo, pedido_id))
        conexion.commit()

        print(f"DEBUG cambiar_metodo_pago: pedido #{pedido_id} {metodo_actual} -> {nuevo_metodo}")

        # 4. Re-orquestar
        orq = orquestar_pedido(
            pedido_id=pedido_id,
            metodo_pago=nuevo_metodo,
            confiable=confiable if confiable is not None else True,
            ubicacion_id=ubicacion_id,
        )
        print(f"DEBUG cambiar_metodo_pago: re-orquestado -> {orq}")

        return {
            "estado": "ok",
            "pedido_id": pedido_id,
            "metodo_anterior": metodo_actual,
            "metodo_pago": nuevo_metodo,
            "orquestacion": orq,
            "mensaje": f"Pedido #{pedido_id} actualizado a '{nuevo_metodo}'. {orq.get('mensaje', '')}",
        }

    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return f"Error al cambiar método de pago: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass