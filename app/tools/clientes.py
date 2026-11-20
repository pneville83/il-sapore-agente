# app/tools/clientes.py
import psycopg2
from app.core.config import DATABASE_URL


def buscar_o_crear_cliente(
    whatsapp: str | None = None,
    whatsapp_lid: str | None = None,
    nombre: str | None = None,
    direccion_mz: str | None = None,
    direccion_villa: str | None = None,
    etapa: str | None = None,
):
    """
    Busca un cliente por whatsapp o whatsapp_lid.
    - Si existe: devuelve dict con estado="encontrado" y campos_faltantes.
    - Si no existe y vienen todos los datos: lo crea con confiable=True.
    - Si no existe y faltan datos: devuelve estado="faltan_datos" (no inserta).
    En error de BD o falta de identificador: devuelve string.
    """
    # 1. Validar identificador
    if not whatsapp and not whatsapp_lid:
        return "Error al buscar/crear cliente: falta identificador (whatsapp o whatsapp_lid)."

    conexion = None
    cursor = None
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()

        # 2. Query dinámica: solo incluye en el WHERE los campos no-null
        condiciones = []
        params = []
        if whatsapp:
            condiciones.append("whatsapp = %s")
            params.append(whatsapp)
        if whatsapp_lid:
            condiciones.append("whatsapp_lid = %s")
            params.append(whatsapp_lid)
        where_clause = " OR ".join(condiciones)

        cursor.execute(
            f"""
            SELECT id, nombre, confiable, direccion_mz, direccion_villa, etapa
            FROM clientes
            WHERE {where_clause}
            LIMIT 1
            """,
            tuple(params),
        )
        fila = cursor.fetchone()

        # 3. Cliente existe
        if fila:
            cliente_id, nombre_bd, confiable, mz, villa, etapa_bd = fila
            campos_faltantes = []
            if nombre_bd is None:
                campos_faltantes.append("nombre")
            if mz is None:
                campos_faltantes.append("direccion_mz")
            if villa is None:
                campos_faltantes.append("direccion_villa")
            if etapa_bd is None:
                campos_faltantes.append("etapa")

            if campos_faltantes:
                mensaje = (
                    f"Cliente encontrado: {nombre_bd or 'sin nombre'}. "
                    f"Falta: {', '.join(campos_faltantes)}."
                )
            else:
                mensaje = f"Cliente encontrado: {nombre_bd}. Datos completos."

            return {
                "estado": "encontrado",
                "cliente_id": cliente_id,
                "confiable": confiable,
                "nombre": nombre_bd,
                "campos_faltantes": campos_faltantes,
                "mensaje": mensaje,
            }

        # 4. Cliente no existe: validar datos para crear
        campos_faltantes_nuevo = []
        if not nombre:
            campos_faltantes_nuevo.append("nombre")
        if not direccion_mz:
            campos_faltantes_nuevo.append("direccion_mz")
        if not direccion_villa:
            campos_faltantes_nuevo.append("direccion_villa")
        if not etapa:
            campos_faltantes_nuevo.append("etapa")

        if campos_faltantes_nuevo:
            return {
                "estado": "faltan_datos",
                "cliente_id": None,
                "confiable": None,
                "nombre": None,
                "campos_faltantes": campos_faltantes_nuevo,
                "mensaje": (
                    "Cliente nuevo. Necesito: "
                    f"{', '.join(campos_faltantes_nuevo)}."
                ),
            }

        # 4b. Crear cliente con confiable=TRUE
        cursor.execute(
            """
            INSERT INTO clientes
                (whatsapp, whatsapp_lid, nombre, direccion_mz,
                 direccion_villa, etapa, confiable)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id, confiable
            """,
            (whatsapp, whatsapp_lid, nombre, direccion_mz, direccion_villa, etapa),
        )
        nuevo_id, nuevo_confiable = cursor.fetchone()
        conexion.commit()

        return {
            "estado": "creado",
            "cliente_id": nuevo_id,
            "confiable": nuevo_confiable,
            "nombre": nombre,
            "campos_faltantes": [],
            "mensaje": f"Cliente creado: {nombre}.",
        }

    except Exception as e:
        return f"Error al buscar/crear cliente: {str(e)}"

    finally:
        try:
            if cursor:
                cursor.close()
            if conexion:
                conexion.close()
        except Exception:
            pass