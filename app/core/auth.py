import psycopg2
from app.core.config import DATABASE_URL
import bcrypt

def identificar_usuario(whatsapp):
    """
    Busca un usuario por su número de WhatsApp.
    Devuelve el usuario (id, username, rol, ubicacion_id) o None si no existe.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        cursor.execute("""
            SELECT id, username, rol, ubicacion_id, whatsapp
            FROM usuarios
            WHERE whatsapp = %s
        """, (whatsapp,))
        fila = cursor.fetchone()
        conexion.close()
        
        if fila:
            return {
                "id": fila[0],
                "username": fila[1],
                "rol": fila[2],
                "ubicacion_id": fila[3],
                "whatsapp": fila[4],
                "tipo": "admin" if fila[2] in ("admin", "superadmin") else "empleado"
            }
        return None
    except Exception as e:
        return {"error": str(e)}


def obtener_info_usuario(usuario_id):
    """
    Devuelve el rol y la ubicación de un usuario (buscando por ID).
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        cursor.execute("""
            SELECT id, username, rol, ubicacion_id
            FROM usuarios
            WHERE id = %s
        """, (usuario_id,))
        fila = cursor.fetchone()
        conexion.close()
        
        if fila:
            return {
                "id": fila[0],
                "username": fila[1],
                "rol": fila[2],
                "ubicacion_id": fila[3],
                "tipo": "admin" if fila[2] in ("admin", "superadmin") else "empleado"
            }
        return None
    except Exception as e:
        return {"error": str(e)}

def autenticar_usuario(username, password):
    """
    Verifica las credenciales de un usuario.
    Devuelve el usuario (id, username, rol, ubicacion_id) o None si falla.
    """
    try:
        conexion = psycopg2.connect(DATABASE_URL)
        cursor = conexion.cursor()
        cursor.execute("""
            SELECT id, username, password_hash, rol, ubicacion_id
            FROM usuarios
            WHERE username = %s
        """, (username,))
        fila = cursor.fetchone()
        conexion.close()
        
        if not fila:
            return None  # Usuario no existe
        
        password_hash = fila[2]
        
        # Verificar contraseña con bcrypt
        if bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
            return {
                "id": fila[0],
                "username": fila[1],
                "rol": fila[3],
                "ubicacion_id": fila[4]
            }
        return None  # Contraseña incorrecta
    except Exception as e:
        return {"error": str(e)}    