import psycopg2
from app.core.config import DATABASE_URL

def consultar_ventas_dia(ubicacion_id=1, fecha=None):
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        cursor.execute("""
            SELECT 
                u.nombre AS ubicacion_nombre,
                COUNT(DISTINCT p.id) AS num_pedidos,
                COALESCE(SUM(d.cantidad * d.precio_unitario), 0) AS total_vendido,
                COALESCE(SUM(d.cantidad * pu.costo), 0) AS costo_total,
                COALESCE(SUM(d.cantidad * d.precio_unitario) - SUM(d.cantidad * pu.costo), 0) AS ganancia_bruta
            FROM pedidos p
            JOIN detalles_pedido d ON d.pedido_id = p.id
            JOIN precios_ubicacion pu ON pu.producto_id = d.producto_id 
                AND pu.ubicacion_id = p.ubicacion_id
                AND (
                    (pu.variacion_id IS NULL AND d.variacion_id IS NULL)
                    OR
                    (pu.variacion_id = d.variacion_id)
                )
            JOIN ubicaciones u ON u.id = p.ubicacion_id
            WHERE p.ubicacion_id = %s
              AND (p.fecha AT TIME ZONE 'America/Guayaquil')::date = COALESCE(%s, (CURRENT_TIMESTAMP AT TIME ZONE 'America/Guayaquil')::date)
            GROUP BY u.nombre
        """, (ubicacion_id, fecha))
        
        fila = cursor.fetchone()
        if fila:
            return {
                "ubicacion_nombre": fila[0],
                "num_pedidos": fila[1],
                "total_vendido": fila[2],
                "costo_total": fila[3],
                "ganancia_bruta": fila[4]
            }
        else:
            # No hay ventas, pero igual devolvemos el nombre de la ubicación
            cursor.execute("SELECT nombre FROM ubicaciones WHERE id = %s", (ubicacion_id,))
            nombre = cursor.fetchone()
            conexion.close()
            return {
                "ubicacion_nombre": nombre[0] if nombre else f"Ubicación {ubicacion_id}",
                "num_pedidos": 0,
                "total_vendido": 0,
                "costo_total": 0,
                "ganancia_bruta": 0
            }
    except Exception as e:
        return f"Error al consultar ventas: {str(e)}"


def consultar_flujo_dinero(ubicacion_id=1, fecha_inicio=None, fecha_fin=None):
    """
    Devuelve el flujo de dinero: ventas, gastos y saldo por método de pago.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        
        # Ventas por método (desde transacciones)
        cursor.execute("""
            SELECT 
                t.tipo AS metodo,
                COALESCE(SUM(t.monto), 0) AS total
            FROM transacciones t
            JOIN pedidos p ON p.id = t.pedido_id
            WHERE p.ubicacion_id = %s
              AND (p.fecha AT TIME ZONE 'America/Guayaquil')::date BETWEEN COALESCE(%s, CURRENT_DATE - 365) AND COALESCE(%s, CURRENT_DATE)
            GROUP BY t.tipo
        """, (ubicacion_id, fecha_inicio, fecha_fin))
        ventas = dict(cursor.fetchall())
        
        # Gastos por método
        cursor.execute("""
            SELECT 
                metodo_pago AS metodo,
                COALESCE(SUM(monto), 0) AS total
            FROM gastos
            WHERE ubicacion_id = %s
              AND (fecha AT TIME ZONE 'America/Guayaquil')::date BETWEEN COALESCE(%s, CURRENT_DATE - 365) AND COALESCE(%s, CURRENT_DATE)
            GROUP BY metodo_pago
        """, (ubicacion_id, fecha_inicio, fecha_fin))
        gastos = dict(cursor.fetchall())
        
        # Compras por método
        cursor.execute("""
            SELECT 
                metodo_pago AS metodo,
                COALESCE(SUM(monto), 0) AS total
            FROM compras
            WHERE ubicacion_id = %s
              AND (fecha AT TIME ZONE 'America/Guayaquil')::date BETWEEN COALESCE(%s, CURRENT_DATE - 365) AND COALESCE(%s, CURRENT_DATE)
            GROUP BY metodo_pago
        """, (ubicacion_id, fecha_inicio, fecha_fin))
        compras = dict(cursor.fetchall())
        
        conexion.close()
        
        # Calcular saldo por método
        metodos = ["efectivo", "transferencia", "tarjeta"]
        saldo_por_metodo = {}
        for m in metodos:
            v = float(ventas.get(m, 0))
            g = float(gastos.get(m, 0))
            c = float(compras.get(m, 0))
            saldo_por_metodo[m] = {
                "ventas": v,
                "gastos": g,
                "compras": c,
                "saldo": v - g - c
            }
        
        return {
            "ventas_por_metodo": {m: float(ventas.get(m, 0)) for m in metodos},
            "gastos_por_metodo": {m: float(gastos.get(m, 0)) for m in metodos},
            "compras_por_metodo": {m: float(compras.get(m, 0)) for m in metodos},
            "saldo_por_metodo": saldo_por_metodo,
            "saldo_total": sum(s["saldo"] for s in saldo_por_metodo.values())
        }
    except Exception as e:
        return f"Error al consultar flujo de dinero: {str(e)}"    