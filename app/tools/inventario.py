import psycopg2
from app.core.config import DATABASE_URL


def consultar_inventario(ubicacion_id=1):
    """
    Devuelve la lista de productos disponibles en esa ubicación,
    con sus variaciones, precios, costos y descripción.
    Filtra por precios_ubicacion.disponible = true (disponibilidad por sucursal).
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
                p.disponible AS disponible_global,
                pu.id AS precio_id,
                pu.variacion_id,
                v.nombre_variacion,
                pu.precio,
                pu.costo,
                pu.ubicacion_id,
                pu.disponible AS disponible_ubicacion
            FROM productos p
            JOIN precios_ubicacion pu ON pu.producto_id = p.id AND pu.ubicacion_id = %s
            LEFT JOIN variaciones_producto v ON v.id = pu.variacion_id
            WHERE p.disponible = true
              AND pu.disponible = true
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
    Nota: no filtra por ubicación (no la recibe). El agente debe usar
    consultar_inventario para verificar disponibilidad en una sucursal.
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


def cambiar_disponibilidad_producto(
    producto_id: int,
    disponible: bool,
    ubicacion_id: int = None,
    todas: bool = False,
    rol: str = "cliente",
    ubicacion_usuario: int = None,
):
    """
    Cambia la disponibilidad de un producto en precios_ubicacion.
    - superadmin: puede cambiar en una ubicación (ubicacion_id) o en todas (todas=True).
    - admin: solo en su ubicación (ubicacion_id debe coincidir con ubicacion_usuario).
    - empleado/cliente: sin permiso.
    """
    # 1. Validar permisos por rol
    if rol not in ("superadmin", "admin"):
        return f"Error: el rol '{rol}' no puede cambiar disponibilidad de productos."

    if rol == "superadmin":
        if not todas and ubicacion_id is None:
            return "Error: indica ubicacion_id o todas=True."
    elif rol == "admin":
        if todas:
            return "Error: un admin no puede cambiar la disponibilidad en todas las ubicaciones."
        if ubicacion_id is None:
            return "Error: indica ubicacion_id (la tuya)."
        if ubicacion_usuario is not None and ubicacion_id != ubicacion_usuario:
            return f"Error: un admin solo puede cambiar su ubicación ({ubicacion_usuario})."

    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # 2. Verificar que el producto existe
        cursor.execute("SELECT nombre FROM productos WHERE id = %s", (producto_id,))
        fila_prod = cursor.fetchone()
        if not fila_prod:
            return f"Error: el producto {producto_id} no existe."
        nombre_producto = fila_prod[0]

        # 3. Actualizar
        if todas and rol == "superadmin":
            cursor.execute("""
                UPDATE precios_ubicacion
                SET disponible = %s
                WHERE producto_id = %s
                RETURNING ubicacion_id
            """, (disponible, producto_id))
        else:
            cursor.execute("""
                UPDATE precios_ubicacion
                SET disponible = %s
                WHERE producto_id = %s AND ubicacion_id = %s
                RETURNING ubicacion_id
            """, (disponible, producto_id, ubicacion_id))

        ubicaciones_afectadas = [f[0] for f in cursor.fetchall()]
        conexion.commit()

        if not ubicaciones_afectadas:
            return f"Error: no hay precios configurados para '{nombre_producto}' en la ubicación indicada."

        estado_txt = "disponible" if disponible else "no disponible"
        return {
            "estado": "ok",
            "producto_id": producto_id,
            "producto_nombre": nombre_producto,
            "disponible": disponible,
            "ubicaciones_afectadas": ubicaciones_afectadas,
            "mensaje": (
                f"'{nombre_producto}' ahora está {estado_txt} en "
                f"{len(ubicaciones_afectadas)} ubicación(es): {ubicaciones_afectadas}."
            ),
        }

    except Exception as e:
        if conexion:
            try: conexion.rollback()
            except Exception: pass
        return f"Error al cambiar disponibilidad: {str(e)}"
    finally:
        try:
            if cursor: cursor.close()
            if conexion: conexion.close()
        except Exception: pass