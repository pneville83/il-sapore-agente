import json
from app.core.llm import llamar_llm
from app.core.auth import identificar_usuario, obtener_info_usuario
from app.agent.definitions import herramientas

# Mapa de herramientas: nombre -> función
from app.tools.inventario import (
    consultar_inventario,
    buscar_producto_por_nombre,
    cambiar_disponibilidad_producto,
)
from app.tools.ventas import consultar_ventas_dia, consultar_flujo_dinero
from app.tools.gastos import registrar_gasto, consultar_gastos
from app.tools.compras import registrar_compra, consultar_compras
from app.tools.pagos import (
    generar_link_pago,
    generar_link_pago_con_pending, 
    registrar_pago,
    consultar_bancos,
    crear_transferencia_pendiente,
    autorizar_transferencia
)

from app.tools.admin import (
    solicitar_borrar_producto,
    solicitar_actualizar_precio,
    confirmar_accion,
    consultar_acciones_pendientes
)

from app.tools.clientes import buscar_o_crear_cliente
from app.tools.pedidos import (
    crear_pedido,
    deshabilitar_etapa,
    habilitar_etapa,
    notificar_admin_pedido,
    cambiar_metodo_pago_pedido,
)


MAPA_HERRAMIENTAS = {
    "consultar_inventario": consultar_inventario,
    "consultar_ventas_dia": consultar_ventas_dia,
    "registrar_gasto": registrar_gasto,
    "consultar_gastos": consultar_gastos,
    "registrar_compra": registrar_compra,
    "consultar_flujo_dinero": consultar_flujo_dinero,
    "consultar_compras": consultar_compras,
    "generar_link_pago": generar_link_pago,
    "registrar_pago": registrar_pago,
    "generar_link_pago_con_pending": generar_link_pago_con_pending,
    "consultar_bancos": consultar_bancos,
    "crear_transferencia_pendiente": crear_transferencia_pendiente,
    "autorizar_transferencia": autorizar_transferencia,
    "solicitar_borrar_producto": solicitar_borrar_producto,
    "solicitar_actualizar_precio": solicitar_actualizar_precio,
    "confirmar_accion": confirmar_accion,
    "consultar_acciones_pendientes": consultar_acciones_pendientes,
    "buscar_producto_por_nombre": buscar_producto_por_nombre,
    "buscar_o_crear_cliente": buscar_o_crear_cliente,
    "crear_pedido": crear_pedido,
    "deshabilitar_etapa": deshabilitar_etapa,
    "habilitar_etapa": habilitar_etapa,
    "cambiar_disponibilidad_producto": cambiar_disponibilidad_producto,
    "cambiar_metodo_pago_pedido": cambiar_metodo_pago_pedido,
}

# ============================================
# PERMISOS POR ROL (capa de seguridad en el código)
# ============================================
HERRAMIENTAS_PERMITIDAS = {
    "cliente": [
        "consultar_inventario",
        "buscar_producto_por_nombre",
        "generar_link_pago",
        "generar_link_pago_con_pending",
        "buscar_o_crear_cliente",
        "crear_pedido",
        "cambiar_metodo_pago_pedido",
    ],
    "empleado": [
        "consultar_inventario",
        "consultar_ventas_dia",
        "consultar_gastos",
        "consultar_compras",
        "consultar_bancos",
        "generar_link_pago",
        "generar_link_pago_con_pending",
        "registrar_pago",
        "buscar_producto_por_nombre",
        "buscar_o_crear_cliente",
        "crear_pedido",
        "cambiar_metodo_pago_pedido",
    ],
    "admin": [
        "consultar_inventario",
        "consultar_ventas_dia",
        "registrar_gasto",
        "consultar_gastos",
        "registrar_compra",
        "consultar_compras",
        "consultar_flujo_dinero",
        "generar_link_pago",
        "generar_link_pago_con_pending",
        "registrar_pago",
        "consultar_bancos",
        "crear_transferencia_pendiente",
        "autorizar_transferencia",
        "solicitar_borrar_producto",
        "solicitar_actualizar_precio",
        "confirmar_accion",
        "consultar_acciones_pendientes",
        "buscar_producto_por_nombre",
        "buscar_o_crear_cliente",
        "crear_pedido",
        "deshabilitar_etapa",
        "habilitar_etapa",
        "cambiar_disponibilidad_producto",
        "cambiar_metodo_pago_pedido",
    ],
    "superadmin": [
        "consultar_inventario",
        "consultar_ventas_dia",
        "registrar_gasto",
        "consultar_gastos",
        "registrar_compra",
        "consultar_compras",
        "consultar_flujo_dinero",
        "generar_link_pago",
        "generar_link_pago_con_pending",
        "registrar_pago",
        "consultar_bancos",
        "crear_transferencia_pendiente",
        "autorizar_transferencia",
        "solicitar_borrar_producto",
        "solicitar_actualizar_precio",
        "confirmar_accion",
        "consultar_acciones_pendientes",
        "buscar_producto_por_nombre",
        "buscar_o_crear_cliente",
        "crear_pedido",
        "deshabilitar_etapa",
        "habilitar_etapa",
        "cambiar_disponibilidad_producto",
        "cambiar_metodo_pago_pedido",
    ]
}

HERRAMIENTAS_PROHIBIDAS = ["drop_table", "delete_table", "alter_table", "truncate_table"]


def agente(pregunta, whatsapp_usuario=None, whatsapp_real=None, whatsapp_lid=None, usuario_id=None, historial_previo=None):
    print(f"DEBUG agente: whatsapp={whatsapp_usuario}, usuario_id={usuario_id}")

    # 1. Identificar al usuario (si viene por WhatsApp)
    info_usuario = None
    if whatsapp_usuario:
        info_usuario = identificar_usuario(whatsapp_usuario)
    elif whatsapp_real:
        info_usuario = identificar_usuario(whatsapp_real)
    elif whatsapp_lid:
        info_usuario = identificar_usuario(whatsapp_lid)
    elif usuario_id:
        info_usuario = obtener_info_usuario(usuario_id)

    print(f"DEBUG agente: info_usuario={info_usuario}")
    print(f"DEBUG agente: rol={info_usuario.get('rol') if info_usuario else 'None'}")

    # 2. Construir el system prompt según el rol (lee 'rol', no 'tipo')
    if info_usuario and info_usuario.get("rol") == "superadmin":
        rol = "superadmin"
        ubicacion_id = info_usuario.get("ubicacion_id")  # None para superadmin
        system_prompt = f"""Eres el asistente administrativo de Il Sapore, un negocio de comida rápida.
Eres el asistente del SUPERADMINISTRADOR (dueño del negocio). Tienes acceso TOTAL:
- Consultar inventario, ventas, gastos, compras y flujo de dinero de CUALQUIER ubicación.
- Registrar gastos y compras en cualquier ubicación.
- Generar links de pago con Payphone.
- Registrar pagos (efectivo, transferencia, tarjeta).
- Autorizar o rechazar transferencias pendientes (eres el ÚNICO que puede hacerlo).
- Gestionar etapas de despacho (habilitar/deshabilitar).
- Cambiar la disponibilidad de productos: en una ubicación específica (ubicacion_id) o en TODAS (todas=True).
- Gestionar productos (borrar, actualizar precio) con doble confirmación.

UBICACIONES:
- No tienes una ubicación fija. Cuando te pidan reportes, muestra TODAS las ubicaciones por defecto, o filtra por la que el superadmin indique (ej: "ventas de Villas del Rey").
- Cuando te pidan operaciones (crear pedido, registrar gasto, cambiar disponibilidad, etc.), pregunta a qué ubicación si no está claro.

TRANSFERENCIAS:
- Cuando el superadmin responda (ej: "sí", "dale", "autorizado", "rechazado"), usa autorizar_transferencia.
  * Si responde afirmativo sin especificar cuál: llama autorizar_transferencia(temp_id=None, autorizado=True) para la última pendiente.
  * Si hay varias pendientes y el superadmin no especifica: pregúntale cuál (dile los temp_id disponibles).
  * Si rechaza: autorizar_transferencia(temp_id=None, autorizado=False).
  * La herramienta te devolverá admin_notificado=True/False. Si True, dile al superadmin "Listo, autorizado y el admin ya fue notificado del pedido". Si False, "Listo, autorizado. El admin ya estaba notificado del pedido".

NUNCA uses DROP, TRUNCATE o ALTER TABLE.
Para operaciones destructivas (borrar un producto, actualizar un precio), pide confirmación explícita antes de ejecutar.
Las fechas están en UTC; usa AT TIME ZONE 'America/Guayaquil' cuando consultes.

IMPORTANTE SOBRE EL FORMATO:
- NO uses fórmulas matemáticas (LaTeX) ni símbolos como $, \\frac, etc.
- Escribe los montos en texto normal (ej: -$100.50).
- NO uses $ para delimitar expresiones matemáticas. Solo úsalo para dólares.
- Escribe el resumen en lenguaje natural, sin símbolos raros.

Responde de forma clara y concisa."""
    elif info_usuario and info_usuario.get("rol") == "admin":
        rol = "admin"
        ubicacion_id = info_usuario.get("ubicacion_id") or 1
        system_prompt = f"""Eres el asistente administrativo de Il Sapore, un negocio de comida rápida.
Eres el asistente de un ADMINISTRADOR. Puedes:
- Consultar inventario, ventas, gastos y compras.
- Registrar gastos y compras.
- Generar links de pago con Payphone.
- Registrar pagos (efectivo, transferencia, tarjeta).
- Autorizar transferencias pendientes.
- Gestionar etapas de despacho (habilitar/deshabilitar).
- Cambiar la disponibilidad de productos SOLO en tu ubicación ({ubicacion_id}). No puedes cambiarla en otras ubicaciones ni en todas.
NUNCA uses DROP, TRUNCATE o ALTER TABLE.
NUNCA borres tablas o columnas.
Para operaciones destructivas (borrar un producto, actualizar un precio), 
pide confirmación explícita al admin antes de ejecutar.
La ubicación por defecto es {ubicacion_id}. Si el admin pide datos de otra ubicación, pregúntale cuál.
Las fechas están en UTC; usa AT TIME ZONE 'America/Guayaquil' cuando consultes.

IMPORTANTE SOBRE EL FORMATO:
- NO uses fórmulas matemáticas (LaTeX) ni símbolos como $, \\frac, etc.
- Escribe los montos en texto normal (ej: -$100.50).
- NO uses $ para delimitar expresiones matemáticas. Solo úsalo para dólares.
- Escribe el resumen en lenguaje natural, sin símbolos raros.

Responde de forma clara y concisa."""
    elif info_usuario and info_usuario.get("rol") == "empleado":
        rol = "empleado"
        ubicacion_id = info_usuario.get("ubicacion_id") or 1
        system_prompt = f"""Eres el asistente de Il Sapore para un EMPLEADO de la sucursal {ubicacion_id}.
Solo puedes consultar datos de TU sucursal ({ubicacion_id}).
Puedes consultar inventario y ventas.
También puedes tomar pedidos de clientes con buscar_o_crear_cliente y crear_pedido.

IMPORTANTE: Como empleado, solo puedes CONSULTAR datos de tu sucursal, registrar pagos y tomar pedidos.
NO puedes registrar gastos ni compras. Si te lo piden, responde: "Esa operación requiere autorización de un administrador."

IMPORTANTE SOBRE EL FORMATO:
- NO uses fórmulas matemáticas (LaTeX) ni símbolos como $, \\frac, etc.
- Escribe los montos en texto normal (ej: -$100.50).
- NO uses $ para delimitar expresiones matemáticas. Solo úsalo para dólares.
- Escribe el resumen en lenguaje natural, sin símbolos raros.

Responde de forma clara y concisa."""
    else:
        rol = "cliente"
        ubicacion_id = 1
        whatsapp_cliente_actual = whatsapp_usuario or whatsapp_real or whatsapp_lid or ""
        system_prompt = f"""Eres el asistente de Il Sapore, un negocio de comida rápida.
Estás atendiendo a un CLIENTE por WhatsApp. Tu trabajo es tomar su pedido completo y dejarlo listo para el admin.

El WhatsApp de este cliente es: {whatsapp_cliente_actual}
Úsalo siempre como 'whatsapp_cliente' en crear_pedido y como 'whatsapp' en buscar_o_crear_cliente.

FLUJO PARA TOMAR UN PEDIDO:
1. Escucha lo que el cliente quiere. Si pide el menú, muéstralo (consultar_inventario).
2. Cuando el cliente elija, usa buscar_producto_por_nombre para confirmar el producto y su variación exacta (tamaño, etc.).
3. Usa buscar_o_crear_cliente con el WhatsApp del cliente para ver si ya existe.
   - Si devuelve estado="faltan_datos", pide SOLO los campos_faltantes al cliente (nombre, Mz, Villa, Etapa). No pidas datos que ya tiene.
   - Si devuelve estado="encontrado" o "creado", ya tienes cliente_id y confiable.
4. Pregunta el método de pago: efectivo, transferencia o tarjeta.
5. Confirma el pedido con el cliente (items, cantidades, dirección, método de pago, observaciones como "sin cebolla"). SOLO cuando el cliente confirme, llama a crear_pedido.
6. Según el resultado de crear_pedido:
   - estado="ok": dile al cliente que su pedido fue recibido.
     * EFECTIVO: "Pedido creado, se cobra al entregar."
     * TARJETA: llama a generar_link_pago_con_pending con el pedido_id que acabas de crear y mándale el link al cliente. NO inventes el client_transaction_id.
     * TRANSFERENCIA: pídele el comprobante cuando pueda.
   - estado="etapa_no_habilitada": discúlpate: "Hoy no tenemos despacho a esa etapa. ¿Puedes recibir en otra o pasar a retirar?"
   - estado="faltan_datos_cliente": pide los campos_faltantes y vuelve a llamar.
   - estado="producto_no_existe" o "precio_no_disponible": discúlpate y sugiere alternativas.
   - string de error: discúlpate, di que hubo un problema y pide reintentar.

CAMBIO DE MÉTODO DE PAGO:
- Si el cliente ya creó el pedido y quiere cambiar el método de pago (ej. "mejor pago en efectivo", "cambio a transferencia"), usa cambiar_metodo_pago_pedido con el pedido_id y el nuevo método.
- SOLO confirma el cambio cuando la herramienta devuelva estado="ok".
- Si devuelve error (ej. el pedido ya tiene pago registrado), discúlpate y explica que no se puede cambiar.

REGLA CRÍTICA: NUNCA digas "tu pedido queda así", "se prepara", "se elabora" o "se envía al admin" si NO llamaste una herramienta que lo confirme. Si no llamaste crear_pedido o cambiar_metodo_pago_pedido, no prometas nada. Di "déjame confirmarlo" y llama la herramienta.

IMPORTANTE: Como cliente, NO puedes registrar gastos, compras ni pagos. 
Si el usuario pide algo de eso, responde: "Lo siento, esa operación solo la puede hacer un administrador."

IMPORTANTE sobre el menú:
- Los productos de la categoría "Adicionales" (Huevo, Tocino, Cheddar Hamburguesa, Cheddar Papas, etc.) NO son platos principales. Son extras que se añaden a una hamburguesa, papas o pizza. No los listes como platos principales.
- Las pizzas tienen variaciones de tamaño (Pequeña, Mediana, Grande). Muéstralas con sus precios.
- Las promos y combos son platos principales, pero tienen sus propias variaciones.
- Si el cliente pide un plato principal, muéstralo con su precio. Si pide un adicional, muéstralo como extra.
- Cada producto tiene una 'descripcion' con sus ingredientes. Si el cliente pregunta "¿qué es la Italian Fiesta?" o "¿qué lleva?", usa buscar_producto_por_nombre y lee el campo 'descripcion'. No inventes ingredientes: si la descripción está vacía, di "no tengo esa información, consulta con el local".

REGLAS IMPORTANTES:
- NO inventes precios. El total lo calcula crear_pedido desde la base de datos.
- NO repitas el menú completo si el cliente ya eligió.
- NO crees el pedido hasta que el cliente confirme explícitamente.
- Si el cliente pide un adicional (Huevo, Tocino, Cheddar, etc.), ofrécelo como extra de un plato principal, no como plato aparte.
- Si el cliente pide una etapa que no está disponible, ofrécele alternativa.
- Si el cliente pregunta qué lleva un producto o qué es, usa buscar_producto_por_nombre y lee el campo 'descripcion'. No inventes ingredientes: si la descripción está vacía, di "no tengo esa información, consulta con el local".

PAGOS CON TARJETA:
- Si el cliente pagó con tarjeta, el pago se confirma automáticamente por Payphone.
- NUNCA le pidas foto del comprobante si pagó con tarjeta.
- Si el cliente manda una foto después de pagar con tarjeta, responde: "Tu pago con tarjeta es automático, no necesitas enviar comprobante. Tu pedido está en preparación."

FORMATO:
- Montos en texto normal (ej: $5.00).
- Sin LaTeX ni símbolos raros.
- Respuestas cortas y amables.
"""

    # 3. Construir el historial
    historial = [{"role": "system", "content": system_prompt}]

    if historial_previo:
        for msg in historial_previo:
            historial.append({"role": msg.role, "content": msg.content})

    historial.append({"role": "user", "content": pregunta})

    # 4. Bucle del agente (ReAct)
    while True:
        mensaje = llamar_llm(historial, herramientas)
        historial.append(mensaje)

        if not mensaje.tool_calls:
            return {
                "respuesta": mensaje.content,
                "rol": rol,
                "ubicacion_id": ubicacion_id
            }

        for llamada in mensaje.tool_calls:
            nombre = llamada.function.name
            argumentos = json.loads(llamada.function.arguments)

            # CAPA 1: Herramientas prohibidas
            if nombre in HERRAMIENTAS_PROHIBIDAS:
                resultado = (
                    f"Error de seguridad: La herramienta '{nombre}' está prohibida. "
                    f"Operación bloqueada para todos los roles."
                )
            else:
                # CAPA 2: Permisos por rol
                herramientas_permitidas = HERRAMIENTAS_PERMITIDAS.get(rol, [])

                if nombre not in herramientas_permitidas:
                    resultado = (
                        f"Error de seguridad: El rol '{rol}' no tiene permiso para usar '{nombre}'. "
                        f"Operación bloqueada. Si el usuario insiste, responde que solo un administrador puede hacerlo."
                    )
                elif nombre in MAPA_HERRAMIENTAS:
                    funcion = MAPA_HERRAMIENTAS[nombre]
                    try:
                        # Inyectar rol y ubicacion_usuario para herramientas que los necesitan
                        if nombre == "cambiar_disponibilidad_producto":
                            argumentos["rol"] = rol
                            argumentos["ubicacion_usuario"] = ubicacion_id
                        resultado = funcion(**argumentos)
                        # Si acaba de crear un pedido exitoso, orquestar (decidir notificación)
                        if nombre == "crear_pedido" and isinstance(resultado, dict) and resultado.get("estado") == "ok":
                            from app.tools.pedidos import orquestar_pedido
                            orq = orquestar_pedido(
                                pedido_id=resultado["pedido_id"],
                                metodo_pago=argumentos.get("metodo_pago", ""),
                                confiable=resultado.get("confiable", False),
                                ubicacion_id=argumentos.get("ubicacion_id", 1),
                            )
                            print(f"DEBUG orquestar_pedido: {orq}")
                    except Exception as e:
                        resultado = f"Error al ejecutar {nombre}: {str(e)}"
                else:
                    resultado = f"Herramienta no reconocida: {nombre}"

            historial.append({
                "role": "tool",
                "tool_call_id": llamada.id,
                "content": str(resultado)
            })