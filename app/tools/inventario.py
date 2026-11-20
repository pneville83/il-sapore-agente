import psycopg2
from app.core.config import DATABASE_URL


def consultar_inventario(ubicacion_id=1):
    """
    Devuelve la lista de productos disponibles con sus variaciones, precios,
    costos y descripción para una ubicación específica (sucursal).
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT
                p.id AS producto_id,
                p.nombre AS producto_nombre,
                p.categoria,
                p.descripcion,
                p.disponible,
                pu.id AS precio_id,
                pu.variacion_id,
                v.nombre_variacion,
                pu.precio,
                pu.costo,
                pu.ubicacion_id
            FROM productos p
            JOIN precios_ubicacion pu ON pu.producto_id = p.id AND pu.ubicacion_id = %s
            LEFT JOIN variaciones_producto v ON v.id = pu.variacion_id
            WHERE p.disponible = true
            ORDER BY p.categoria, p.nombre, v.nombre_variacion
        """, (ubicacion_id,))

        filas = cursor.fetchall()
        columnas = [desc[0] for desc in cursor.description]
        resultado = [dict(zip(columnas, fila)) for fila in filas]

        conexion.close()
        return resultado
    except Exception as e:
        return f"Error al consultar inventario: {str(e)}"


def buscar_producto_por_nombre(nombre):
    """
    Busca un producto por su nombre (coincidencia parcial).
    Devuelve la lista de productos que coinciden, con su descripción.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT id, nombre, categoria, descripcion, disponible
            FROM productos
            WHERE LOWER(nombre) LIKE LOWER(%s)
            ORDER BY nombre
        """, (f"%{nombre}%",))

        filas = cursor.fetchall()
        columnas = [desc[0] for desc in cursor.description]
        resultado = [dict(zip(columnas, fila)) for fila in filas]

        conexion.close()
        return resultado
    except Exception as e:
        return f"Error al buscar producto: {str(e)}"