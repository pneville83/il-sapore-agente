import psycopg2
from app.core.config import DATABASE_URL

def registrar_gasto(descripcion, monto, tipo, metodo_pago, ubicacion_id=1):
    """
    Registra un gasto.
    tipo: "negocio" o "personal"
    metodo_pago: "efectivo", "transferencia" o "tarjeta"
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        cursor.execute("""
            INSERT INTO gastos (descripcion, monto, tipo, metodo_pago, ubicacion_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, fecha
        """, (descripcion, monto, tipo, metodo_pago, ubicacion_id))
        
        fila = cursor.fetchone()
        conexion.commit()
        conexion.close()
        
        return {
            "id": fila[0],
            "fecha": fila[1],
            "descripcion": descripcion,
            "monto": monto,
            "tipo": tipo,
            "metodo_pago": metodo_pago,
            "mensaje": "Gasto registrado correctamente"
        }
    except Exception as e:
        return f"Error al registrar gasto: {str(e)}"


def consultar_gastos(ubicacion_id=1, tipo=None, fecha_inicio=None, fecha_fin=None):
    """
    Consulta los gastos de una ubicación.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        query = """
            SELECT id, fecha, descripcion, monto, tipo, metodo_pago
            FROM gastos
            WHERE ubicacion_id = %s
        """
        params = [ubicacion_id]
        
        if tipo:
            query += " AND tipo = %s"
            params.append(tipo)
        
        if fecha_inicio and fecha_fin:
            query += " AND (fecha AT TIME ZONE 'America/Guayaquil')::date BETWEEN %s AND %s"
            params.extend([fecha_inicio, fecha_fin])
        elif fecha_inicio:
            query += " AND (fecha AT TIME ZONE 'America/Guayaquil')::date >= %s"
            params.append(fecha_inicio)
        elif fecha_fin:
            query += " AND (fecha AT TIME ZONE 'America/Guayaquil')::date <= %s"
            params.append(fecha_fin)
        
        query += " ORDER BY fecha DESC"
        
        cursor.execute(query, params)
        filas = cursor.fetchall()
        columnas = [desc[0] for desc in cursor.description]
        resultado = [dict(zip(columnas, fila)) for fila in filas]
        
        conexion.close()
        return resultado
    except Exception as e:
        return f"Error al consultar gastos: {str(e)}"