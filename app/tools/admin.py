import json
import psycopg2
from app.core.config import DATABASE_URL

def solicitar_borrar_producto(producto_id, ubicacion_id=1):
    """
    Solicita borrar un producto. No lo borra directamente.
    Crea una acción pendiente que el admin debe confirmar.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        cursor.execute("""
            INSERT INTO pending_actions (accion, parametros, estado)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (
            "borrar_producto",
            json.dumps({"producto_id": producto_id, "ubicacion_id": ubicacion_id}),
            "ESPERANDO_CONFIRMACION"
        ))
        
        fila = cursor.fetchone()
        conexion.commit()
        conexion.close()
        
        return {
            "id": fila[0],
            "accion": "borrar_producto",
            "producto_id": producto_id,
            "estado": "ESPERANDO_CONFIRMACION",
            "mensaje": f"Se solicita borrar el producto {producto_id}. El admin debe confirmar."
        }
    except Exception as e:
        return f"Error al solicitar borrar producto: {str(e)}"


def solicitar_actualizar_precio(producto_id, nuevo_precio, ubicacion_id=1):
    """
    Solicita actualizar el precio de un producto.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        cursor.execute("""
            INSERT INTO pending_actions (accion, parametros, estado)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (
            "actualizar_precio",
            json.dumps({"producto_id": producto_id, "nuevo_precio": nuevo_precio, "ubicacion_id": ubicacion_id}),
            "ESPERANDO_CONFIRMACION"
        ))
        
        fila = cursor.fetchone()
        conexion.commit()
        conexion.close()
        
        return {
            "id": fila[0],
            "accion": "actualizar_precio",
            "producto_id": producto_id,
            "nuevo_precio": nuevo_precio,
            "estado": "ESPERANDO_CONFIRMACION",
            "mensaje": f"Se solicita actualizar el precio del producto {producto_id} a ${nuevo_precio}. El admin debe confirmar."
        }
    except Exception as e:
        return f"Error al solicitar actualizar precio: {str(e)}"


def confirmar_accion(accion_id, confirmado):
    """
    Confirma o cancela una acción pendiente.
    Si se confirma, ejecuta la acción.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        # Buscar la acción
        cursor.execute("""
            SELECT accion, parametros, estado
            FROM pending_actions
            WHERE id = %s AND estado = 'ESPERANDO_CONFIRMACION'
        """, (accion_id,))
        fila = cursor.fetchone()
        
        if not fila:
            conexion.close()
            return f"Error: No se encontró la acción {accion_id} o ya fue procesada."
        
        accion = fila[0]
        parametros = fila[1]  # JSONB ya es dict
        
        if not confirmado:
            # Cancelar
            cursor.execute("""
                UPDATE pending_actions SET estado = 'CANCELADO', confirmado_en = NOW()
                WHERE id = %s
            """, (accion_id,))
            conexion.commit()
            conexion.close()
            return {"estado": "CANCELADO", "mensaje": "Acción cancelada."}
        
        # Confirmar: ejecutar la acción
        if accion == "borrar_producto":
            producto_id = parametros["producto_id"]
            cursor.execute("DELETE FROM productos WHERE id = %s", (producto_id,))
            resultado = f"Producto {producto_id} borrado."
        elif accion == "actualizar_precio":
            producto_id = parametros["producto_id"]
            nuevo_precio = parametros["nuevo_precio"]
            ubicacion_id = parametros.get("ubicacion_id", 1)
            cursor.execute("""
                UPDATE precios_ubicacion 
                SET precio = %s 
                WHERE producto_id = %s AND ubicacion_id = %s
            """, (nuevo_precio, producto_id, ubicacion_id))
            resultado = f"Precio del producto {producto_id} actualizado a ${nuevo_precio}."
        else:
            resultado = f"Acción '{accion}' no reconocida."
        
        cursor.execute("""
            UPDATE pending_actions SET estado = 'CONFIRMADO', confirmado_en = NOW()
            WHERE id = %s
        """, (accion_id,))
        conexion.commit()
        conexion.close()
        
        return {"estado": "CONFIRMADO", "resultado": resultado}
    except Exception as e:
        return f"Error al confirmar acción: {str(e)}"


def consultar_acciones_pendientes():
    """
    Devuelve la lista de acciones pendientes de confirmación.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        cursor.execute("""
            SELECT id, accion, parametros, creado_en
            FROM pending_actions
            WHERE estado = 'ESPERANDO_CONFIRMACION'
            ORDER BY creado_en DESC
        """)
        filas = cursor.fetchall()
        columnas = [desc[0] for desc in cursor.description]
        resultado = [dict(zip(columnas, fila)) for fila in filas]
        
        conexion.close()
        return resultado
    except Exception as e:
        return f"Error al consultar acciones pendientes: {str(e)}"